"""Fact extraction from content chunks.

Two extraction modes
--------------------
1. Single-chunk:   extract_chunk()      (was: extract_concept_chunk)
2. Batched:        extract_batch()      (was: extract_concept_batch)

Both modes are now topic-type aware and route to the appropriate extraction
schema (Concept, Command, Tool, Architecture, Process) via get_schema_and_model().

Batching packs up to `batch_size` chunks from the SAME SOURCE into a single
LLM prompt, dramatically cutting API-call count and shared-prompt overhead.

The batched prompt asks the model to return a JSON object keyed by chunk_id::

    {
      "results": {
        "<chunk_id>": { ...SCHEMA fields... },
        "<chunk_id>": { ...SCHEMA fields... }
      }
    }

If the batch LLM call fails or the response cannot be validated, the function
falls back to individual single-chunk calls automatically.

Token logging
-------------
Both functions accept an optional `log_dir` (Path).  When provided, every
successful LLM call appends a record to data/logs/token_usage.jsonl via
token_logger.log_usage().
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from pydantic import ValidationError

from edu_curator.config import Settings
from edu_curator.ids import new_id
from edu_curator.llm import chat_json
from edu_curator.schemas import (
    ArchitectureExtraction,
    CommandExtraction,
    ConceptExtraction,
    ContentChunk,
    ExtractionError,
    FactExtraction,
    ProcessExtraction,
    ProcessingStatus,
    Source,
    SourceToTopicMapping,
    StrictModel,
    SyllabusTopic,
    ToolExtraction,
)

# ---------------------------------------------------------------------------
# Per-topic-type schema dictionaries (used in prompts)
# ---------------------------------------------------------------------------

CONCEPT_SCHEMA: dict[str, Any] = {
    "definition": None,
    "purpose": None,
    "key_properties": [],
    "benefits": [],
    "limitations": [],
    "common_misconceptions": [],
    "related_topics": [],
    "extraction_confidence": None,
}

COMMAND_SCHEMA: dict[str, Any] = {
    "syntax": None,
    "parameters": [],
    "examples": [],
    "expected_output": None,
    "common_errors": [],
    "extraction_confidence": None,
}

TOOL_SCHEMA: dict[str, Any] = {
    "overview": None,
    "features": [],
    "use_cases": [],
    "advantages": [],
    "limitations": [],
    "related_tools": [],
    "extraction_confidence": None,
}

ARCHITECTURE_SCHEMA: dict[str, Any] = {
    "overview": None,
    "components": [],
    "interactions": [],
    "tradeoffs": [],
    "use_cases": [],
    "extraction_confidence": None,
}

PROCESS_SCHEMA: dict[str, Any] = {
    "overview": None,
    "steps": [],
    "inputs": [],
    "outputs": [],
    "benefits": [],
    "limitations": [],
    "extraction_confidence": None,
}

_SCHEMA_MAP: dict[str, tuple[dict[str, Any], type[StrictModel]]] = {
    "concept": (CONCEPT_SCHEMA, ConceptExtraction),
    "command": (COMMAND_SCHEMA, CommandExtraction),
    "tool": (TOOL_SCHEMA, ToolExtraction),
    "architecture": (ARCHITECTURE_SCHEMA, ArchitectureExtraction),
    "process": (PROCESS_SCHEMA, ProcessExtraction),
}


def get_schema_and_model(topic_type: str) -> tuple[dict[str, Any], type[StrictModel]]:
    """Return (schema_dict, PydanticModel) for a given topic type string.

    Falls back to the concept schema for unknown types.
    """
    return _SCHEMA_MAP.get(str(topic_type).lower(), (CONCEPT_SCHEMA, ConceptExtraction))


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------


def parse_json_robust(content: str) -> dict:
    """Parse JSON string, using json-repair fallback if standard parsing fails."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            import json_repair

            return json_repair.loads(content)
        except Exception:
            raise


# ---------------------------------------------------------------------------
# Chunk selection helper
# ---------------------------------------------------------------------------


def selected_chunks(
    chunks: list[ContentChunk],
    mappings: list[SourceToTopicMapping],
    max_chunks_per_source: int,
) -> list[ContentChunk]:
    mapped_ids = {mapping.chunk_id for mapping in mappings if mapping.is_active}
    candidates = [chunk for chunk in chunks if chunk.id in mapped_ids]
    candidates.sort(key=lambda chunk: (chunk.source_id, chunk.chunk_number))

    counts: dict[str, int] = {}
    selected: list[ContentChunk] = []
    for chunk in candidates:
        count = counts.get(chunk.source_id, 0)
        if count < max_chunks_per_source:
            selected.append(chunk)
            counts[chunk.source_id] = count + 1
    return selected


# ---------------------------------------------------------------------------
# Message builders — schema-aware
# ---------------------------------------------------------------------------


def extraction_messages(
    topic: SyllabusTopic,
    source: Source,
    chunk: ContentChunk,
) -> list[dict[str, str]]:
    """Build single-chunk extraction messages using the topic-type-appropriate schema."""
    schema_dict, _ = get_schema_and_model(topic.topic_type)
    return [
        {
            "role": "system",
            "content": (
                "You are an information extraction engine. Extract only information "
                "explicitly stated in the source content. Never infer missing "
                "information. Never use external knowledge. If unsupported, return "
                "null for scalar fields or [] for array fields. "
                "Estimate an extraction confidence score between 0.0 and 1.0 based on how "
                "clearly and directly the chunk supports the extracted facts, and populate the "
                "'extraction_confidence' field. Output valid JSON only.\n\n"
                f"Extraction Schema:\n{json.dumps(schema_dict, indent=2)}\n\n"
                "Extract information according to the schema. Return only the JSON object."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic:\n{topic.topic_name}\n\n"
                f"Topic Type:\n{topic.topic_type}\n\n"
                f"Source:\n{source.title}\n\n"
                f"Chunk:\n{chunk.chunk_text}"
            ),
        },
    ]


# Backward-compat alias used by Cerebras Batch API path in cli.py
concept_messages = extraction_messages


def _batch_messages(
    topic: SyllabusTopic,
    source: Source,
    chunks: list[ContentChunk],
) -> list[dict[str, str]]:
    """Build a single prompt that requests extractions for multiple chunks at once.

    The model must return::

        {
          "results": {
            "<chunk_id>": { ...SCHEMA fields... },
            "<chunk_id>": { ...SCHEMA fields... }
          }
        }
    """
    schema_dict, _ = get_schema_and_model(topic.topic_type)
    chunk_blocks = "\n\n".join(
        f"--- CHUNK {i + 1} (id: {ck.id}) ---\n{ck.chunk_text}" for i, ck in enumerate(chunks)
    )
    schema_str = json.dumps(schema_dict, indent=2)
    output_example = json.dumps(
        {"results": {"chunk_uuid_1": schema_dict, "chunk_uuid_2": schema_dict}},
        indent=2,
    )
    return [
        {
            "role": "system",
            "content": (
                "You are an information extraction engine. "
                "Extract only information explicitly stated in the source content. "
                "Never infer missing information. Never use external knowledge. "
                "If unsupported, return null for scalar fields or [] for array fields. "
                "For EACH chunk, estimate an extraction confidence score between 0.0 and 1.0 "
                "based on how clearly and directly the chunk supports the extracted facts, "
                "and populate the 'extraction_confidence' field. Output valid JSON only.\n\n"
                f"Per-chunk extraction schema:\n{schema_str}\n\n"
                "For EACH chunk, extract information according to the schema.\n"
                "Return a single JSON object with this structure (use the exact chunk ids as keys):\n"
                f"{output_example}\n\n"
                "Return only the JSON object with the 'results' key."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic:\n{topic.topic_name}\n\n"
                f"Topic Type:\n{topic.topic_type}\n\n"
                f"Source:\n{source.title}\n\n"
                f"Chunks to process:\n{chunk_blocks}"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Fact row builder — generic (works for any StrictModel subclass)
# ---------------------------------------------------------------------------


def fact_rows_from_extraction(
    extraction: StrictModel,
    topic: SyllabusTopic,
    chunk: ContentChunk,
    model: str,
) -> list[FactExtraction]:
    """Convert any validated extraction model into FactExtraction DB rows."""
    topic_type = str(topic.topic_type).lower()
    now = datetime.now(UTC)
    ext_confidence = getattr(extraction, "extraction_confidence", None)
    rows: list[FactExtraction] = []
    for field_name, value in extraction.model_dump().items():
        if field_name == "extraction_confidence":
            continue
        rows.append(
            FactExtraction(
                id=new_id(),
                topic_id=topic.id,
                source_id=chunk.source_id,
                chunk_id=chunk.id,
                field_name=field_name,
                field_value={"value": value},
                schema_version="1.0",
                prompt_version=f"eps.{topic_type}.v1",
                extraction_model=model,
                extraction_confidence=ext_confidence,
                status=ProcessingStatus.completed,
                created_at=now,
            )
        )
    return rows


# Backward-compat alias used by Cerebras Batch API path in cli.py
def fact_rows_from_concept(
    extraction: StrictModel,
    topic: SyllabusTopic,
    chunk: ContentChunk,
    model: str,
) -> list[FactExtraction]:
    return fact_rows_from_extraction(extraction, topic, chunk, model)


# ---------------------------------------------------------------------------
# Single-chunk extraction
# ---------------------------------------------------------------------------


def extract_chunk(
    settings: Settings,
    topic: SyllabusTopic,
    source: Source,
    chunk: ContentChunk,
    log_dir: Path | None = None,
    topic_sn: int | None = None,
) -> list[FactExtraction]:
    """Extract facts from a single chunk using the appropriate schema for topic_type.

    Logs token usage if log_dir is given.
    """
    _, ExtractionModel = get_schema_and_model(topic.topic_type)
    result = chat_json(
        settings=settings,
        messages=extraction_messages(topic, source, chunk),
        model=settings.extraction_model,
        stage="extract",
        topic_sn=topic_sn,
    )

    if log_dir is not None:
        from edu_curator.token_logger import log_usage

        log_usage(
            log_dir, result, stage="extract", model=settings.extraction_model, topic_sn=topic_sn
        )

    payload = parse_json_robust(result.content)
    extraction = ExtractionModel.model_validate(payload)
    return fact_rows_from_extraction(extraction, topic, chunk, settings.extraction_model)


# Backward-compat alias for any external callers
extract_concept_chunk = extract_chunk


# ---------------------------------------------------------------------------
# Batched extraction
# ---------------------------------------------------------------------------


def extract_batch(
    settings: Settings,
    topic: SyllabusTopic,
    source: Source,
    chunks: list[ContentChunk],
    log_dir: Path | None = None,
    topic_sn: int | None = None,
) -> tuple[list[FactExtraction], list[str]]:
    """Extract facts from multiple chunks in a single LLM call.

    Parameters
    ----------
    chunks:   All chunks MUST belong to the same source.
    log_dir:  If provided, token usage is appended to token_usage.jsonl.
    topic_sn: Used for token log labeling.

    Returns
    -------
    (facts, failed_chunk_ids)
      facts:            All successfully extracted FactExtraction rows.
      failed_chunk_ids: IDs of chunks whose extraction failed (empty = full success).
    """
    if not chunks:
        return [], []

    source_ids = {ck.source_id for ck in chunks}
    if len(source_ids) > 1:
        raise ValueError(
            f"extract_batch received chunks from {len(source_ids)} "
            "different sources. All chunks must be from the same source."
        )

    _, ExtractionModel = get_schema_and_model(topic.topic_type)

    result = chat_json(
        settings=settings,
        messages=_batch_messages(topic, source, chunks),
        model=settings.extraction_model,
        stage="extract_batch",
        topic_sn=topic_sn,
    )

    if log_dir is not None:
        from edu_curator.token_logger import log_usage

        log_usage(
            log_dir,
            result,
            stage="extract_batch",
            model=settings.extraction_model,
            topic_sn=topic_sn,
        )

    try:
        outer = parse_json_robust(result.content)
    except Exception as exc:
        logger.error(f"JSON decode error: {exc}. All {len(chunks)} chunks failed.")
        return [], [ck.id for ck in chunks]

    results_map: dict = outer.get("results", {})
    if not isinstance(results_map, dict):
        logger.error(f"Unexpected 'results' type: {type(results_map)}. All chunks failed.")
        return [], [ck.id for ck in chunks]

    chunk_by_id = {ck.id: ck for ck in chunks}
    all_facts: list[FactExtraction] = []
    failed: list[str] = []

    for chunk_id, payload in results_map.items():
        if chunk_id not in chunk_by_id:
            continue
        ck = chunk_by_id[chunk_id]
        try:
            extraction = ExtractionModel.model_validate(payload)
            all_facts.extend(
                fact_rows_from_extraction(extraction, topic, ck, settings.extraction_model)
            )
        except (ValidationError, TypeError) as exc:
            logger.error(f"Validation failed for chunk {chunk_id}: {exc}")
            failed.append(chunk_id)

    for ck in chunks:
        if ck.id not in results_map and ck.id not in failed:
            logger.warning(f"No result returned for chunk {ck.id}.")
            failed.append(ck.id)

    return all_facts, failed


# Backward-compat alias
extract_concept_batch = extract_batch


# ---------------------------------------------------------------------------
# Batched extraction orchestrator (groups chunks by source, respects batch_size)
# ---------------------------------------------------------------------------


def extract_topic_batched(
    settings: Settings,
    topic: SyllabusTopic,
    chunks_to_extract: list[ContentChunk],
    source_by_id: dict[str, Source],
    batch_size: int = 3,
    log_dir: Path | None = None,
    topic_sn: int | None = None,
    parallel: bool = True,
) -> tuple[list[FactExtraction], list[ExtractionError]]:
    """Run batched extraction across all chunks for a topic.

    Groups chunks by source_id, then slices each group into windows of
    `batch_size`.  For each window one LLM call is made.  Any chunks that
    fail inside a batch are retried individually (single-chunk fallback).

    Parameters
    ----------
    batch_size: Max chunks per LLM call (default 3, keep ≤5 for reliability).
    parallel:   If True, execute batch requests concurrently via ThreadPoolExecutor.

    Returns
    -------
    (all_facts, all_errors)
    """
    by_source: dict[str, list[ContentChunk]] = {}
    for ck in chunks_to_extract:
        by_source.setdefault(ck.source_id, []).append(ck)

    tasks = []
    for source_id, src_chunks in by_source.items():
        source = source_by_id[source_id]
        for batch_start in range(0, len(src_chunks), batch_size):
            batch = src_chunks[batch_start : batch_start + batch_size]
            tasks.append((source, batch))

    all_facts: list[FactExtraction] = []
    all_errors: list[ExtractionError] = []

    def process_task(task_idx: int, source: Source, batch: list[ContentChunk]):
        logger.info(
            f"[batch {task_idx}] {len(batch)} chunk(s) from '{source.title[:50]}' ..."
        )
        task_facts = []
        task_errors = []
        try:
            facts, failed_ids = extract_batch(
                settings=settings,
                topic=topic,
                source=source,
                chunks=batch,
                log_dir=log_dir,
                topic_sn=topic_sn,
            )
            task_facts.extend(facts)
            logger.info(f"OK [batch {task_idx}]: {len(facts)} fact rows extracted.")
        except Exception as exc:
            failed_ids = [ck.id for ck in batch]
            logger.error(f"ERROR in batch {task_idx}: {type(exc).__name__}: {exc}")

        if failed_ids:
            failed_set = set(failed_ids)
            logger.info(
                f"Retrying {len(failed_set)} failed chunk(s) in batch {task_idx} individually ..."
            )
            failed_chunks = [ck for ck in batch if ck.id in failed_set]
            for ck in failed_chunks:
                try:
                    facts = extract_chunk(
                        settings=settings,
                        topic=topic,
                        source=source_by_id[ck.source_id],
                        chunk=ck,
                        log_dir=log_dir,
                        topic_sn=topic_sn,
                    )
                    task_facts.extend(facts)
                    logger.info(
                        f"OK [batch {task_idx} fallback]: chunk {ck.chunk_number}"
                    )
                except Exception as exc2:
                    task_errors.append(extraction_error(exc2, topic, ck))
                    logger.error(
                        f"FAIL [batch {task_idx} fallback]: chunk {ck.chunk_number}: {exc2}"
                    )
        return task_facts, task_errors

    if parallel and len(tasks) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(process_task, i + 1, src, b) for i, (src, b) in enumerate(tasks)
            ]
            for future in as_completed(futures):
                try:
                    facts, errors = future.result()
                    all_facts.extend(facts)
                    all_errors.extend(errors)
                except Exception as exc:
                    logger.error(f"Task execution failed: {exc}")
    else:
        for i, (src, b) in enumerate(tasks):
            facts, errors = process_task(i + 1, src, b)
            all_facts.extend(facts)
            all_errors.extend(errors)

    return all_facts, all_errors


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def extraction_error(
    error: Exception,
    topic: SyllabusTopic,
    chunk: ContentChunk,
    retry_count: int = 0,
) -> ExtractionError:
    return ExtractionError(
        id=new_id(),
        topic_id=topic.id,
        source_id=chunk.source_id,
        chunk_id=chunk.id,
        error_type=type(error).__name__,
        error_detail=str(error),
        retry_count=retry_count,
        resolved=False,
        created_at=datetime.now(UTC),
    )


def is_validation_error(error: Exception) -> bool:
    return isinstance(error, (json.JSONDecodeError, ValidationError))
