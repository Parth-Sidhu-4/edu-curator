"""Decoupled curation pipeline execution controller.

Provides standard Python interfaces for orchestrating the curation pipeline stages
independent of CLI formatting and Typer input structures.
"""

from __future__ import annotations

import json
import time
import uuid
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from edu_curator.chunking import word_chunks
from edu_curator.conflict_resolution import resolve_topic_knowledge
from edu_curator.consistency_check import run_consistency_check
from edu_curator.extraction import (
    extract_concept_chunk,
    extract_topic_batched,
    extraction_error,
    selected_chunks,
)
from edu_curator.generation import canonical_knowledge_summary
from edu_curator.ids import new_id
from edu_curator.schemas import (
    ContentChunk,
    ExtractionError,
    FactExtraction,
    NormalizedDocument,
    Source,
    SourceToTopicMapping,
    SyllabusTopic,
    TopicContent,
    TopicKnowledge,
)
from edu_curator.storage import get_table
from edu_curator.token_logger import log_usage

logger = logging.getLogger("edu_curator.pipeline")

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SDLC_TOPIC_UUID = "11111111-1111-1111-1111-111111111111"


def _topic_uuid(serial_number: int) -> str:
    """Deterministic UUID for a topic by serial number."""
    if serial_number == 1:
        return SDLC_TOPIC_UUID
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"devops-topic-sn-{serial_number}"))


def _get_topic_by_sn(sn: int, settings) -> SyllabusTopic:
    """Look up a topic by serial number. Raises ValueError if not found."""
    topics = get_table("syllabus_topics", SyllabusTopic, settings).read()
    topic_id = _topic_uuid(sn)
    for t in topics:
        if t.id == topic_id:
            return t
    raise ValueError(f"Topic with serial number {sn} not found.")


def _append_json_table(
    settings,
    path: Path,
    model_cls,
    new_rows: list,
    delete_field: Optional[str] = None,
    delete_value: Any = None,
) -> None:
    """Append rows to a table, optionally deleting existing rows matching delete_field=delete_value first."""
    table = get_table(path.stem, model_cls, settings)
    if delete_field is not None:
        table.delete(delete_field, delete_value)

    from edu_curator.storage import SupabaseTable

    if isinstance(table, SupabaseTable):
        table.write(new_rows)
    else:
        existing = table.read()
        table.write(existing + new_rows)


def compute_topic_inputs_hash(topic_id: str, settings) -> str:
    """Generate a SHA-256 hash of all topic generation input variables for caching."""
    # Fetch target topic
    topics = get_table("syllabus_topics", SyllabusTopic, settings).read()
    target_topic = [t for t in topics if t.id == topic_id]
    if not target_topic:
        return ""
    topic = target_topic[0]

    # Get sources mapped to this topic
    sources = get_table("sources", Source, settings).read()
    topic_sources = [s for s in sources if topic_id in s.topic_ids]
    # Sort by ID to ensure deterministic concatenation
    topic_sources.sort(key=lambda s: s.id)
    sources_hashes = ",".join(s.content_hash or "" for s in topic_sources)

    # Get static system prompt structures
    from edu_curator.extraction import concept_messages
    from edu_curator.generation import generation_messages

    dummy_source = Source(
        id="dummy-id",
        title="dummy-title",
        source_type="website",
        trust_score=5,
        topic_ids=[topic_id],
    )
    dummy_chunk = ContentChunk(
        id="dummy-chunk", source_id="dummy-id", chunk_text="dummy-text", chunk_number=1
    )

    try:
        ext_messages = concept_messages(topic, dummy_source, dummy_chunk)
        ext_system_prompt = ext_messages[0]["content"] if ext_messages else ""
    except Exception:
        ext_system_prompt = ""

    try:
        gen_messages = generation_messages(
            topic.topic_name, str(topic.topic_type), "dummy-summary", ["dummy-source"]
        )
        gen_system_prompt = gen_messages[0]["content"] if gen_messages else ""
    except Exception:
        gen_system_prompt = ""

    # Combine all variables into payload
    hash_payload = (
        f"topic_name:{topic.topic_name}|"
        f"topic_type:{topic.topic_type}|"
        f"sources_hashes:{sources_hashes}|"
        f"ext_model:{settings.extraction_model}|"
        f"gen_model:{settings.generation_model}|"
        f"ext_sys_prompt:{ext_system_prompt}|"
        f"gen_sys_prompt:{gen_system_prompt}"
    )
    return hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()


def run_chunk(settings, chunk_size: int = 800, overlap: int = 100) -> tuple[int, int]:
    """Chunk documents into overlapping word windows.

    Returns a tuple of (added_chunks_count, total_chunks_count).
    """
    documents = get_table("documents", NormalizedDocument, settings).read()
    if not documents:
        raise ValueError("No normalized documents found. Run 'ingest' or 'add-source' first.")

    existing_chunks = get_table("content_chunks", ContentChunk, settings).read()
    already_chunked = {c.source_id for c in existing_chunks}

    new_docs = [d for d in documents if d.source_id not in already_chunked]
    if not new_docs:
        return 0, len(existing_chunks)

    new_chunks: list[ContentChunk] = []
    for document in new_docs:
        doc_chunks = word_chunks(document, chunk_size=chunk_size, overlap=overlap)
        new_chunks.extend(doc_chunks)

    all_chunks = existing_chunks + new_chunks
    get_table("content_chunks", ContentChunk, settings).write(all_chunks)
    return len(new_chunks), len(all_chunks)


def run_map_topic(
    settings,
    sn: Optional[int] = None,
    threshold: float = 0.40,
) -> tuple[int, int, str]:
    """Build source-to-topic mappings semantically using local embeddings & cosine similarity.

    Returns a tuple of (new_mappings_count, total_written_or_processed, topic_name).
    """
    topics = get_table("syllabus_topics", SyllabusTopic, settings).read()
    sources = get_table("sources", Source, settings).read()
    chunks = get_table("content_chunks", ContentChunk, settings).read()

    if not topics:
        raise ValueError("No topics found. Run 'load-syllabus' first.")
    if not chunks:
        raise ValueError("No chunks found. Run 'chunk' first.")

    mappings_table = get_table("source_to_topic_mapping", SourceToTopicMapping, settings)

    from edu_curator.mapping import map_chunks_semantically

    topic_filter_ids = {_topic_uuid(sn)} if sn is not None else None

    # Calculate embeddings and map semantically
    new_mappings, updated_chunks = map_chunks_semantically(
        topics=topics,
        chunks=chunks,
        sources=sources,
        topic_filter_ids=topic_filter_ids,
        similarity_threshold=threshold,
    )

    # Write newly computed embeddings back
    if updated_chunks:
        chunks_table = get_table("content_chunks", ContentChunk, settings)
        chunks_table.write(chunks)

    topic_name = ""
    if sn is not None:
        topic = _get_topic_by_sn(sn, settings)
        topic_name = topic.topic_name
        # Remove old mappings for this topic, add new ones
        mappings_table.delete("topic_id", topic.id)
        from edu_curator.storage import SupabaseTable

        if isinstance(mappings_table, SupabaseTable):
            mappings_table.write(new_mappings)
        else:
            existing = mappings_table.read()
            mappings_table.write(existing + new_mappings)
        return len(new_mappings), len(new_mappings), topic_name
    else:
        # Full rebuild
        from edu_curator.storage import SupabaseTable

        if isinstance(mappings_table, SupabaseTable):
            for t in topics:
                mappings_table.delete("topic_id", t.id)
            mappings_table.write(new_mappings)
        else:
            mappings_table.write(new_mappings)
        return len(new_mappings), len(topics), ""


def run_extract(
    settings,
    sn: int,
    max_chunks_per_source: int = 1,
    batch_size: int = 3,
    parallel: bool = False,
    use_batch_api: Optional[bool] = None,
) -> tuple[int, int]:
    """Run LLM extraction for one topic.

    Returns a tuple of (facts_extracted_count, errors_encountered_count).
    """
    if use_batch_api is None:
        use_batch_api = settings.use_batch_api

    topic = _get_topic_by_sn(sn, settings)
    log_dir = DATA / "logs"

    sources = get_table("sources", Source, settings).read()
    source_by_id = {s.id: s for s in sources}
    chunks = get_table("content_chunks", ContentChunk, settings).read()
    mappings = get_table("source_to_topic_mapping", SourceToTopicMapping, settings).read(filters={"topic_id": topic.id})
    topic_mappings = mappings
    if not topic_mappings:
        raise ValueError(f"No mappings for topic sn={sn}. Run 'map-topic --sn {sn}' first.")

    chunks_to_extract = selected_chunks(chunks, topic_mappings, max_chunks_per_source)

    facts: list[FactExtraction] = []
    errors: list[ExtractionError] = []
    batch_succeeded = False

    if use_batch_api:
        # Build JSONL content
        from edu_curator.extraction import concept_messages

        lines = []
        for ck in chunks_to_extract:
            source = source_by_id[ck.source_id]
            messages = concept_messages(topic, source, ck)
            req = {
                "custom_id": ck.id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": settings.extraction_model,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            }
            lines.append(json.dumps(req))
        jsonl_content = "\n".join(lines) + "\n"

        # Upload to Cerebras files
        from edu_curator.llm import (
            create_batch_job,
            download_file_content,
            retrieve_batch_job,
            upload_batch_file,
        )

        try:
            file_bytes = jsonl_content.encode("utf-8")
            file_id = upload_batch_file(settings, file_bytes, f"topic_{sn}_extract.jsonl")

            # Submit batch job
            batch_id = create_batch_job(settings, file_id)

            # Poll status
            while True:
                job = retrieve_batch_job(settings, batch_id)
                status = job.get("status")
                if status == "completed":
                    break
                elif status in {"failed", "failed_validation", "cancelled", "expired"}:
                    raise RuntimeError(
                        f"Cerebras batch job {batch_id} finished with status: {status}"
                    )
                time.sleep(5)

            # Download and parse results
            output_file_id = job.get("output_file_id")
            content = download_file_content(settings, output_file_id)

            from edu_curator.extraction import (
                fact_rows_from_extraction,
                get_schema_and_model,
                parse_json_robust,
            )
            from edu_curator.llm import ChatResult
            from edu_curator.token_logger import log_usage

            chunk_by_id = {ck.id: ck for ck in chunks_to_extract}

            for line_num, line in enumerate(content.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                chunk_id = row.get("custom_id")
                ck = chunk_by_id.get(chunk_id)
                if not ck:
                    continue

                response = row.get("response", {})
                body = response.get("body", {})
                choices = body.get("choices", [])
                usage = body.get("usage", {})
                err = row.get("error")

                if err or not choices:
                    err_msg = (
                        err.get("message")
                        if isinstance(err, dict)
                        else str(err or "No choices in response")
                    )
                    errors.append(extraction_error(RuntimeError(err_msg), topic, ck))
                    continue

                ans_content = choices[0]["message"]["content"]
                try:
                    payload = parse_json_robust(ans_content)
                    _, ExtractionModel = get_schema_and_model(topic.topic_type)
                    extraction = ExtractionModel.model_validate(payload)
                    chunk_facts = fact_rows_from_extraction(
                        extraction, topic, ck, settings.extraction_model
                    )
                    facts.extend(chunk_facts)

                    # Log token usage
                    chat_res = ChatResult(
                        content=ans_content,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                    )
                    log_usage(
                        log_dir,
                        chat_res,
                        stage="extract_batch_api",
                        model=settings.extraction_model,
                        topic_sn=sn,
                    )
                except Exception as exc:
                    errors.append(extraction_error(exc, topic, ck))

            batch_succeeded = True
        except Exception as exc:
            logger.warning(
                f"Cerebras Batch API failed/unauthorized: {exc}. Falling back to standard extraction..."
            )
            batch_succeeded = False

    if not use_batch_api or not batch_succeeded:
        if batch_size <= 1:
            # ── Original single-chunk behaviour ──────────────────────────────────
            def process_chunk(ck):
                try:
                    res_facts = extract_concept_chunk(
                        settings,
                        topic,
                        source_by_id[ck.source_id],
                        ck,
                        log_dir=log_dir,
                        topic_sn=sn,
                    )
                    return res_facts, None
                except Exception as exc:
                    return [], extraction_error(exc, topic, ck)

            if parallel and len(chunks_to_extract) > 1:
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(process_chunk, ck) for ck in chunks_to_extract]
                    for future in futures:
                        res_facts, res_err = future.result()
                        facts.extend(res_facts)
                        if res_err:
                            errors.append(res_err)
            else:
                for i, ck in enumerate(chunks_to_extract):
                    res_facts, res_err = process_chunk(ck)
                    facts.extend(res_facts)
                    if res_err:
                        errors.append(res_err)
                    if i < len(chunks_to_extract) - 1:
                        time.sleep(3)  # pace — Cerebras free tier ~30 RPM
        else:
            # ── Batched extraction ────────────────────────────────────────────────
            facts_batch, errors_batch = extract_topic_batched(
                settings=settings,
                topic=topic,
                chunks_to_extract=chunks_to_extract,
                source_by_id=source_by_id,
                batch_size=batch_size,
                log_dir=log_dir,
                topic_sn=sn,
                parallel=parallel,
            )
            facts.extend(facts_batch)
            errors.extend(errors_batch)

    _append_json_table(
        settings,
        DATA / "extractions" / "fact_extractions.json",
        FactExtraction,
        facts,
        delete_field="topic_id",
        delete_value=topic.id,
    )
    _append_json_table(
        settings,
        DATA / "extractions" / "extraction_errors.json",
        ExtractionError,
        errors,
        delete_field="topic_id",
        delete_value=topic.id,
    )
    return len(facts), len(errors)


def run_resolve(settings, sn: int) -> TopicKnowledge:
    """Resolve canonical knowledge for one topic."""
    topic = _get_topic_by_sn(sn, settings)
    sources = get_table("sources", Source, settings).read()
    topic_facts = get_table("fact_extractions", FactExtraction, settings).read(filters={"topic_id": topic.id})
    if not topic_facts:
        raise ValueError(f"No fact extractions for topic sn={sn}. Run 'extract --sn {sn}' first.")

    topic_knowledge = resolve_topic_knowledge(
        topic.id, topic_facts, sources, topic_type=topic.topic_type, topic_name=topic.topic_name
    )

    # Append/replace in topic_knowledge.json
    tk_table = get_table("topic_knowledge", TopicKnowledge, settings)
    tk_table.delete("topic_id", topic.id)
    from edu_curator.storage import SupabaseTable

    if isinstance(tk_table, SupabaseTable):
        tk_table.write([topic_knowledge])
    else:
        existing = tk_table.read()
        tk_table.write(existing + [topic_knowledge])

    return topic_knowledge


def run_generate_content(settings, sn: int) -> tuple[TopicContent, dict]:
    """Generate educational content for one topic from its canonical knowledge.

    Returns a tuple of (topic_content, eval_result).
    """
    topic = _get_topic_by_sn(sn, settings)

    # Deactivate existing overrides for this topic on new generation
    try:
        from edu_curator.schemas import KnowledgeOverride

        overrides_tbl = get_table("knowledge_overrides", KnowledgeOverride, settings)
        active_overrides = overrides_tbl.read(filters={"topic_id": topic.id, "is_active": True})
        if active_overrides:
            updated_overrides = [
                o.model_copy(update={"is_active": False, "updated_at": datetime.now(UTC)})
                for o in active_overrides
            ]
            overrides_tbl.write(updated_overrides)
    except Exception as exc:
        logger.warning(f"Failed to deactivate existing overrides: {exc}")

    sources = get_table("sources", Source, settings).read()

    knowledge_for_topic = get_table("topic_knowledge", TopicKnowledge, settings).read(filters={"topic_id": topic.id})
    if not knowledge_for_topic:
        raise ValueError(f"No topic knowledge for sn={sn}. Run 'resolve --sn {sn}' first.")
    topic_knowledge = knowledge_for_topic[0]

    source_labels = [s.title for s in sources if s.id in topic_knowledge.sources_used]

    from edu_curator.revision import refine_curriculum

    topic_content, eval_result = refine_curriculum(
        settings=settings,
        topic_knowledge=topic_knowledge,
        topic=topic,
        source_labels=source_labels,
        max_iterations=3,
        target_threshold=9.0,
    )

    # Compute inputs hash to store in the content record
    current_hash = compute_topic_inputs_hash(topic.id, settings)
    topic_content = topic_content.model_copy(update={"inputs_hash": current_hash})

    tc_table = get_table("topic_content", TopicContent, settings)
    tc_table.delete("topic_id", topic.id)
    from edu_curator.storage import SupabaseTable

    if isinstance(tc_table, SupabaseTable):
        try:
            tc_table.write([topic_content])
        except Exception as exc:
            if "inputs_hash" in str(exc):
                # Fallback write without inputs_hash key in payload
                from edu_curator.storage import clean_null_chars

                payload = topic_content.model_dump(mode="json", exclude={"inputs_hash"})
                payload = clean_null_chars(payload)
                tc_table.supabase.table(tc_table.table_name).upsert(payload).execute()
                logger.warning(
                    "Database column 'inputs_hash' missing in Supabase. Upserted without inputs_hash."
                )
            else:
                raise
    else:
        existing = tc_table.read()
        tc_table.write(existing + [topic_content])

    # Save final RAG evaluation results to evaluation_results repository
    if "error" not in eval_result:
        try:
            from edu_curator.ids import new_id
            from edu_curator.schemas import EvaluationResult

            eval_table = get_table("evaluation_results", EvaluationResult, settings)
            eval_rec = EvaluationResult(
                id=new_id(),
                topic_id=topic.id,
                faithfulness_score=eval_result.get("faithfulness_score"),
                completeness_score=eval_result.get("completeness_score"),
                faithfulness_reasoning=eval_result.get("faithfulness_reason"),
                completeness_reasoning=eval_result.get("completeness_reason"),
                created_at=datetime.now(UTC),
            )
            eval_table.write([eval_rec])
        except Exception as db_exc:
            logger.warning(f"Failed to save final RAG evaluation results to repository: {db_exc}")

    return topic_content, eval_result


def run_check_consistency(settings, sn: int) -> tuple[TopicContent, dict]:
    """Run post-generation consistency check for one topic.

    Returns a tuple of (updated_topic_content, check_result).
    """
    topic = _get_topic_by_sn(sn, settings)
    log_dir = DATA / "logs"

    knowledge_for_topic = get_table("topic_knowledge", TopicKnowledge, settings).read(filters={"topic_id": topic.id})
    if not knowledge_for_topic:
        raise ValueError(f"No knowledge for sn={sn}. Run 'resolve --sn {sn}' first.")

    content_for_topic = get_table("topic_content", TopicContent, settings).read(filters={"topic_id": topic.id})
    if not content_for_topic:
        raise ValueError(
            f"No generated content for sn={sn}. Run 'generate-content --sn {sn}' first."
        )

    topic_knowledge = knowledge_for_topic[0]
    topic_content = content_for_topic[0]
    knowledge_summary = canonical_knowledge_summary(topic_knowledge.knowledge)

    sources = get_table("sources", Source, settings).read()
    updated, check_result = run_consistency_check(
        settings=settings,
        topic_content=topic_content,
        topic_knowledge=topic_knowledge,
        topic_name=topic.topic_name,
        knowledge_summary=knowledge_summary,
        topic_sn=sn,
        sources=sources,
    )

    # Log token usage
    log_usage(
        log_dir,
        check_result,
        stage="consistency",
        model=settings.generation_model,
        topic_sn=sn,
    )

    tc_table = get_table("topic_content", TopicContent, settings)
    from edu_curator.storage import SupabaseTable

    if isinstance(tc_table, SupabaseTable):
        try:
            tc_table.write([updated])
        except Exception as exc:
            if "inputs_hash" in str(exc):
                # Fallback write without inputs_hash key in payload
                from edu_curator.storage import clean_null_chars

                payload = updated.model_dump(mode="json", exclude={"inputs_hash"})
                payload = clean_null_chars(payload)
                tc_table.supabase.table(tc_table.table_name).upsert(payload).execute()
            else:
                raise
    else:
        existing = tc_table.read()
        kept = [r for r in existing if r.topic_id != topic.id]
        tc_table.write(kept + [updated])

    return updated, check_result


def run_full_pipeline(
    settings,
    sn: int,
    max_chunks_per_source: int = 1,
    batch_size: int = 3,
    parallel: bool = False,
    force: bool = False,
    use_batch_api: Optional[bool] = None,
    echo_fn=None,
) -> None:
    """Run the full pipeline for one topic: chunk -> map -> extract -> resolve -> generate -> check."""
    if echo_fn is None:

        def default_echo(msg):
            pass

        echo_fn = default_echo

    topic = _get_topic_by_sn(sn, settings)
    current_hash = compute_topic_inputs_hash(topic.id, settings)

    # Read existing content from DB to check if hash matches
    tc_table = get_table("topic_content", TopicContent, settings)
    topic_contents = tc_table.read(filters={"topic_id": topic.id})

    if topic_contents and not force:
        existing_content = topic_contents[0]
        if existing_content.inputs_hash == current_hash:
            echo_fn(
                f"\n[SKIP] Topic '{topic.topic_name}' (sn={sn}) is up-to-date. Skipping pipeline run."
            )
            return

    echo_fn(f"=== run-topic --sn {sn} ===")

    # 1. Chunk (additive)
    echo_fn("\n[1/6] Chunking new documents ...")
    added, total = run_chunk(settings)
    if added > 0:
        echo_fn(f"OK: added {added} new chunks (total: {total}).")
    else:
        echo_fn("OK: all documents already chunked.")

    # 2. Map this topic
    echo_fn(f"\n[2/6] Mapping topic sn={sn} ...")
    mapped, total_mapped, topic_name = run_map_topic(settings, sn=sn)
    echo_fn(f"OK: mapped {mapped} chunks to topic '{topic_name}'.")

    # 3. Extract
    echo_fn(f"\n[3/6] Extracting (max {max_chunks_per_source} chunk/source) ...")
    facts_count, errors_count = run_extract(
        settings,
        sn=sn,
        max_chunks_per_source=max_chunks_per_source,
        batch_size=batch_size,
        parallel=parallel,
        use_batch_api=use_batch_api,
    )
    echo_fn(f"OK: wrote {facts_count} fact rows and {errors_count} errors.")

    # 4. Resolve
    echo_fn("\n[4/6] Resolving canonical knowledge ...")
    topic_knowledge = run_resolve(settings, sn=sn)
    echo_fn(f"OK: resolved '{topic.topic_name}' — confidence={topic_knowledge.confidence}.")

    # 5. Generate content
    echo_fn("\n[5/6] Generating educational content ...")
    topic_content, eval_result = run_generate_content(settings, sn=sn)
    echo_fn(
        f"OK: generated. review_status={topic_content.review_status}, "
        f"confidence={topic_content.confidence_score}."
    )

    # 6. Consistency check
    echo_fn("\n[6/6] Running consistency check ...")
    updated, check_result = run_check_consistency(settings, sn=sn)
    verdict = "PASS" if updated.consistency_check_status else "FLAG"
    flags = (updated.consistency_check_flags or {}).get("flags", [])
    echo_fn(f"OK: verdict={verdict}, flags={len(flags)}.")
    for flag in flags:
        echo_fn(f"  FLAG: {flag}")

    echo_fn(f"\n=== DONE: topic sn={sn} complete ===")
