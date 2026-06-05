"""CLI entry point for the edu-curator pipeline.

Run from the project root (D:\\Internship) with:
    $env:PYTHONPATH="src"  # PowerShell
    set PYTHONPATH=src      # CMD

Commands
--------
  load-syllabus          Load all 82 topics from devops_rows (3).csv
  validate-seed          Check syllabus_topics.json and sources.json
  add-source             Register + immediately ingest one source for a topic
  ingest                 Re-ingest all sources (refresh existing documents)
  chunk                  Chunk documents (additive — skips already-chunked sources)
  map-topic              Build source->topic mappings from source.topic_ids
  extract                LLM extraction  [--sn N] [--batch-size N]
  resolve                Conflict resolution  [--sn N]
  generate-content       Content generation  [--sn N]
  check-consistency      Post-generation consistency check  [--sn N]
  run-topic              Run full pipeline for one topic  --sn N
  token-stats            Show LLM token usage summary
  check-llm-config       Validate LLM environment variables
  list-models            List Cerebras models
  test-llm               Send a test request to the LLM
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import typer

from edu_curator.chunking import word_chunks
from edu_curator.config import load_settings
from edu_curator.conflict_resolution import resolve_topic_knowledge
from edu_curator.consistency_check import run_consistency_check
from edu_curator.extraction import (
    extract_concept_chunk,
    extract_topic_batched,
    extraction_error,
    selected_chunks,
)
from edu_curator.generation import canonical_knowledge_summary, generate_topic_content
from edu_curator.ids import new_id
from edu_curator.ingest import normalize_source
from edu_curator.llm import cerebras_public_models, chat_json
from edu_curator.schemas import (
    ContentChunk,
    ExtractionError,
    FactExtraction,
    NormalizedDocument,
    ProcessingStatus,
    Source,
    SourceToTopicMapping,
    SourceType,
    SyllabusTopic,
    TopicContent,
    TopicKnowledge,
    TopicType,
)
from edu_curator.storage import get_table
from edu_curator.token_logger import log_usage, summarise_usage

app = typer.Typer(pretty_exceptions_show_locals=False)
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CSV_PATH = ROOT / "devops_rows (3).csv"
settings = load_settings(ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SDLC_TOPIC_UUID = "11111111-1111-1111-1111-111111111111"


def _topic_uuid(serial_number: int) -> str:
    """Deterministic UUID for a topic by serial number."""
    if serial_number == 1:
        return SDLC_TOPIC_UUID  # preserve existing
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"devops-topic-sn-{serial_number}"))


def _detect_topic_type(topic_name: str) -> TopicType:
    """Auto-detect topic type from topic name keywords."""
    t = topic_name.lower()
    if any(w in t for w in ["architecture", "components - kube", "components"]):
        return TopicType.architecture
    if any(
        w in t
        for w in [
            "lifecycle",
            "workflow",
            "ci/cd",
            "ci-cd",
            "pipeline",
            "deployment strateg",
            "build lifecycle",
            "build trigger",
            "incident",
            "disaster recovery",
            "troubleshoot",
            "installation",
            "install",
            "configuration",
            "playbook",
            "inventory",
            "modules",
            "scaling",
            "replication",
            "loops and conditions",
            "python automation",
            "devsecoops",
            "security in ci",
            "devsecops",
            "configuration management",
        ]
    ):
        return TopicType.process
    if any(
        w in t
        for w in [
            "jenkins",
            "docker",
            "maven",
            "sonarqube",
            "tomcat",
            "jfrog",
            "ansible",
            "kubernetes",
            "helm",
            "terraform",
            "prometheus",
            "grafana",
            "cloudwatch",
            "azure monitor",
            "git",
            "github",
            "containeriz",
            "artifact storage",
            "metrics and alert",
            "logging system",
            "cloud monitor",
            "state management",
            "images and container",
            "volumes",
            "docker compose",
            "docker swarm",
            "swarm scal",
            "ec2 and s3",
            "azure basics",
            "pods and service",
            "deployment",
            "configmap",
            "container security",
        ]
    ):
        return TopicType.tool
    return TopicType.concept


def _load_csv_topics() -> list[dict]:
    """Read devops_rows CSV and return list of row dicts."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")
    with open(CSV_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _get_topic_by_sn(sn: int) -> SyllabusTopic:
    """Look up a topic by serial number. Raises if not found."""
    topics = get_table("syllabus_topics", SyllabusTopic, settings).read()
    topic_id = _topic_uuid(sn)
    for t in topics:
        if t.id == topic_id:
            return t
    raise typer.BadParameter(
        f"Topic with serial number {sn} not found. "
        "Run 'load-syllabus' first, then check the serial number."
    )


from edu_curator.pipeline import _append_json_table, compute_topic_inputs_hash


# ---------------------------------------------------------------------------
# Syllabus loading
# ---------------------------------------------------------------------------


@app.command()
def load_syllabus() -> None:
    """Load all 82 topics from devops_rows (3).csv into syllabus_topics.json.

    Existing topics are preserved (matched by id). New topics are appended.
    Existing SDLC topic UUID is always preserved.
    """
    rows = _load_csv_topics()
    existing_table = get_table("syllabus_topics", SyllabusTopic, settings)
    existing = {t.id: t for t in existing_table.read()}

    now = datetime.now(UTC)
    topics: list[SyllabusTopic] = []
    for row in rows:
        sn = int(row["serial_number"].strip())
        tid = _topic_uuid(sn)
        if tid in existing:
            # Keep existing record unchanged
            topics.append(existing[tid])
        else:
            topics.append(
                SyllabusTopic(
                    id=tid,
                    chapter=row["chapter_name"].strip(),
                    topic_name=row["topics"].strip(),
                    topic_type=_detect_topic_type(row["topics"].strip()),
                    keywords=[],
                    difficulty_level=None,
                    status=ProcessingStatus.pending,
                    created_at=now,
                    updated_at=now,
                )
            )

    existing_table.write(topics)
    typer.echo(f"OK: loaded {len(topics)} topics into syllabus_topics.json.")
    typer.echo("    Topics by type:")
    from collections import Counter

    counts = Counter(t.topic_type for t in topics)
    for ttype, n in sorted(counts.items()):
        typer.echo(f"      {ttype}: {n}")


# ---------------------------------------------------------------------------
# Source management
# ---------------------------------------------------------------------------


@app.command()
def add_source(
    sn: int = typer.Option(..., "--sn", help="Topic serial number (1-82)"),
    url: Optional[str] = typer.Option(None, "--url", help="URL to fetch"),
    file: Optional[Path] = typer.Option(
        None, "--file", help="Local file path (pdf/image/txt/html/md)"
    ),
    title: str = typer.Option(..., "--title", help="Human-readable source title"),
    trust_score: float = typer.Option(..., "--trust-score", help="Trust score 1.0-10.0"),
    source_type: Optional[str] = typer.Option(
        None, "--source-type", help="website/pdf/image/docx (auto-detected if omitted)"
    ),
    owner: str = typer.Option("System Admin", "--owner", help="Source owner"),
    license_type: str = typer.Option("public documentation", "--license", help="License type"),
) -> None:
    """Register a new source for a topic and immediately ingest it.

    Examples
    --------
    # Website
    python -m edu_curator.cli add-source --sn 2 --url "https://..." --title "Git Phases - Atlassian" --trust-score 8

    # PDF
    python -m edu_curator.cli add-source --sn 5 --file "docs/devops_book.pdf" --title "DevOps Handbook Ch5" --trust-score 7

    # Image (requires PaddleOCR)
    python -m edu_curator.cli add-source --sn 3 --file "slides/docker_arch.png" --title "Docker Architecture Slide" --trust-score 6
    """
    if not url and not file:
        raise typer.BadParameter("Provide either --url or --file.")
    if url and file:
        raise typer.BadParameter("Provide either --url or --file, not both.")

    # Resolve topic
    topic = _get_topic_by_sn(sn)

    # Auto-detect source_type if not provided
    if source_type is None:
        if url:
            source_type = "website"
        elif file:
            ext = Path(file).suffix.lower()
            if ext == ".pdf":
                source_type = "pdf"
            elif ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}:
                source_type = "image"
            elif ext in {".docx"}:
                source_type = "docx"
            else:
                source_type = "website"  # treat .html/.md etc. as website-like

    # Build local_path relative to ROOT if file is given
    local_path_str: str | None = None
    if file:
        file = Path(file)
        if not file.is_absolute():
            file = ROOT / file
        if not file.exists():
            raise typer.BadParameter(f"File not found: {file}")
        try:
            local_path_str = str(file.relative_to(ROOT))
        except ValueError:
            local_path_str = str(file)

    # Dedup logic:
    # 1. If URL/file already exists for THIS topic -> skip (already done)
    # 2. If URL/file already exists for ANOTHER topic -> just link it (no re-fetch)
    # 3. Brand new URL/file -> ingest fresh
    sources_table = get_table("sources", Source, settings)
    existing_sources = sources_table.read()

    existing_match: Source | None = None
    for s in existing_sources:
        same_url = url and s.url == url
        same_file = local_path_str and s.local_path == local_path_str
        if same_url or same_file:
            existing_match = s
            break

    if existing_match is not None:
        if topic.id in existing_match.topic_ids:
            typer.echo(
                f"SKIP: '{existing_match.title}' already linked to topic '{topic.topic_name}'."
            )
            return
        # Link existing source to this additional topic (no re-fetch needed)
        updated = existing_match.model_copy(
            update={"topic_ids": existing_match.topic_ids + [topic.id]}
        )
        sources_table.write([updated if s.id == updated.id else s for s in existing_sources])
        typer.echo(
            f"OK: linked existing source '{existing_match.title}' "
            f"-> topic '{topic.topic_name}' (sn={sn}). No re-fetch needed."
        )
        return

    # Brand new source — create record and ingest
    source = Source(
        id=new_id(),
        title=title,
        source_type=SourceType(source_type),
        url=url,
        local_path=local_path_str,
        trust_score=trust_score,
        license_type=license_type,
        owner=owner,
        topic_ids=[topic.id],
        created_at=datetime.now(UTC),
    )

    typer.echo(f"Ingesting: {title} ...")
    try:
        updated_source, document = normalize_source(source, ROOT)
    except Exception as exc:
        raise typer.BadParameter(f"Ingestion failed: {exc}") from exc

    sources_table.write(existing_sources + [updated_source])

    docs_table = get_table("documents", NormalizedDocument, settings)
    docs_table.write(docs_table.read() + [document])

    typer.echo(
        f"OK: added source '{title}' (id={updated_source.id}) "
        f"for topic '{topic.topic_name}' (sn={sn})."
    )
    typer.echo(f"    Words: ~{len(document.content.split()):,}")
    typer.echo(f"    Next: run 'run-topic --sn {sn}' when all sources are added.")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@app.command()
def validate_seed() -> None:
    """Validate syllabus_topics.json and sources.json."""
    topics = get_table("syllabus_topics", SyllabusTopic, settings).read()
    sources = get_table("sources", Source, settings).read()
    typer.echo(f"OK: {len(topics)} topics and {len(sources)} sources are valid.")


# ---------------------------------------------------------------------------
# Ingestion (re-ingest all existing sources)
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    all_sources: bool = typer.Option(
        False, "--all", help="Re-ingest all sources, including already completed ones"
    )
) -> None:
    """Ingest sources concurrently using asyncio.

    By default, only ingests pending sources (crawl_status != completed).
    Use --all to re-ingest all sources in the database.
    """
    source_table = get_table("sources", Source, settings)
    sources = source_table.read()

    if not all_sources:
        sources = [s for s in sources if s.crawl_status != ProcessingStatus.completed]
        if not sources:
            typer.echo("All sources are already completed. Nothing to ingest.")
            return

    typer.echo(f"Ingesting {len(sources)} sources concurrently using asyncio (concurrency limit: 3)...")

    import asyncio

    from edu_curator.ingest import normalize_sources_async

    results = asyncio.run(normalize_sources_async(sources, ROOT))

    updated_sources = [r[0] for r in results]
    documents = [r[1] for r in results if r[1].content]

    for s, doc in results:
        if doc.content:
            typer.echo(f"  OK: {s.title[:60]}")
        else:
            typer.echo(f"  ERROR: {s.title[:60]} failed during ingest")

    # Read existing sources to merge / update in-place
    existing = source_table.read()
    updated_map = {s.id: s for s in updated_sources}
    final_sources = [updated_map.get(s.id, s) for s in existing]
    
    source_table.write(final_sources)
    
    # Update documents table
    doc_table = get_table("documents", NormalizedDocument, settings)
    existing_docs = doc_table.read()
    new_doc_map = {d.source_id: d for d in documents}
    final_docs = [new_doc_map.get(d.source_id, d) for d in existing_docs]
    # Add brand new docs
    existing_source_ids = {d.source_id for d in existing_docs}
    for doc in documents:
        if doc.source_id not in existing_source_ids:
            final_docs.append(doc)
            
    doc_table.write(final_docs)
    typer.echo(f"OK: normalized {len(documents)} documents.")


@app.command()
def ingest_single(
    source_id: str = typer.Option(..., "--id", help="Source ID to ingest")
) -> None:
    """Ingest a single source by ID, chunk it, and save to database."""
    from datetime import datetime, timezone
    from edu_curator.ingest import normalize_source
    from edu_curator.chunking import word_chunks
    from edu_curator.schemas import Source, NormalizedDocument, ContentChunk
    
    settings = load_settings(ROOT)
    
    sources_tbl = get_table("sources", Source, settings)
    doc_tbl = get_table("documents", NormalizedDocument, settings)
    chunks_tbl = get_table("content_chunks", ContentChunk, settings)

    sources = sources_tbl.read(filters={"id": source_id})
    src = sources[0] if sources else None
    if not src:
        typer.echo(f"Error: Source {source_id} not found in database.")
        raise typer.Exit(code=1)


    typer.echo(f"Starting single ingestion for: {src.title}")
    
    try:
        updated_src, doc = normalize_source(src, ROOT)
        sources_tbl.write([updated_src])
        doc_tbl.write([doc])
        
        chunks = word_chunks(doc, chunk_size=800, overlap=100)
        chunks_tbl.delete("source_id", source_id)
        if hasattr(chunks_tbl, "path"):
            existing_chunks = chunks_tbl.read()
            chunks_tbl.write(existing_chunks + chunks)
        else:
            chunks_tbl.write(chunks)
        typer.echo(f"Ingestion completed for: {src.title}. Created {len(chunks)} chunks.")
    except Exception as e:
        typer.echo(f"Ingestion failed: {e}")
        try:
            sources_tbl.write([
                src.model_copy(update={
                    "crawl_status": "failed",
                    "updated_at": datetime.now(timezone.utc)
                })
            ])
        except Exception as sync_err:
            typer.echo(f"Failed to sync crawl status: {sync_err}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Chunking (additive — only chunks new sources)
# ---------------------------------------------------------------------------


@app.command()
def chunk(chunk_size: int = 800, overlap: int = 100) -> None:
    """Chunk documents into overlapping word windows.

    Additive: skips source_ids that already have chunks in content_chunks.json.
    """
    from edu_curator.pipeline import run_chunk
    try:
        added, total = run_chunk(settings, chunk_size=chunk_size, overlap=overlap)
        if added > 0:
            typer.echo(f"OK: added {added} new chunks (total: {total}).")
        else:
            typer.echo(f"OK: all documents already chunked. Nothing to do.")
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


# ---------------------------------------------------------------------------
# Topic mapping
# ---------------------------------------------------------------------------


@app.command()
def map_topic(
    sn: Optional[int] = typer.Option(
        None, "--sn", help="Only map chunks for this topic serial number"
    ),
    threshold: float = typer.Option(
        0.40, "--threshold", help="Cosine similarity threshold for mapping"
    ),
) -> None:
    """Build source-to-topic mappings semantically using local embeddings & cosine similarity.

    If --sn is given, only updates mappings for that topic (additive).
    Otherwise rebuilds mappings for ALL topics (replaces existing).
    """
    if hasattr(sn, "default"):
        sn = sn.default
    if hasattr(threshold, "default"):
        threshold = threshold.default
    if not isinstance(threshold, (int, float)):
        threshold = 0.40

    from edu_curator.pipeline import run_map_topic
    try:
        mapped, total_mapped, topic_name = run_map_topic(settings, sn=sn, threshold=threshold)
        if sn is not None:
            typer.echo(
                f"OK: mapped {mapped} chunks to topic '{topic_name}' using threshold={threshold}."
            )
        else:
            typer.echo(
                f"OK: mapped {mapped} chunk-topic pairs across {total_mapped} topics using threshold={threshold}."
            )
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


@app.command()
def extract(
    sn: int = typer.Option(..., "--sn", help="Topic serial number to extract"),
    max_chunks_per_source: int = typer.Option(1, "--max-chunks-per-source"),
    batch_size: int = typer.Option(
        3,
        "--batch-size",
        help=(
            "Number of chunks to pack into a single LLM prompt (batch). "
            "Use 1 to disable batching (original behaviour). "
            "Recommended: 3-5. Higher = fewer API calls but larger prompts."
        ),
    ),
    parallel: bool = typer.Option(
        False,
        "--parallel/--no-parallel",
        help="Extract chunks concurrently using thread pool",
    ),
    use_batch_api: bool = typer.Option(
        None, "--use-batch-api/--no-batch-api", help="Use Cerebras Offline Batch API for extraction"
    ),
) -> None:
    """Run LLM extraction for one topic.

    By default uses batched extraction (--batch-size 3) which packs multiple
    chunks into a single LLM call to save API requests and token overhead.
    Use --batch-size 1 to restore the original one-chunk-per-call behaviour.
    Token usage is logged to data/logs/token_usage.jsonl automatically.
    """
    if hasattr(max_chunks_per_source, "default"):
        max_chunks_per_source = max_chunks_per_source.default
    if hasattr(batch_size, "default"):
        batch_size = batch_size.default
    if hasattr(parallel, "default"):
        parallel = parallel.default
    if hasattr(use_batch_api, "default"):
        use_batch_api = use_batch_api.default

    if not isinstance(max_chunks_per_source, int):
        max_chunks_per_source = 1
    if not isinstance(batch_size, int):
        batch_size = 3
    if not isinstance(parallel, bool):
        parallel = False

    from edu_curator.pipeline import run_extract
    try:
        facts_count, errors_count = run_extract(
            settings,
            sn=sn,
            max_chunks_per_source=max_chunks_per_source,
            batch_size=batch_size,
            parallel=parallel,
            use_batch_api=use_batch_api,
        )
        typer.echo(f"OK: wrote {facts_count} fact rows and {errors_count} errors.")
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


# ---------------------------------------------------------------------------
# Asynchronous Offline Batch API
# ---------------------------------------------------------------------------


@app.command()
def create_batch(
    sn: int = typer.Option(..., "--sn", help="Topic serial number to extract via batch"),
    max_chunks_per_source: int = typer.Option(1, "--max-chunks-per-source"),
) -> None:
    """Create and submit a Cerebras Batch job for a topic's chunk extractions."""
    topic = _get_topic_by_sn(sn)
    sources = get_table("sources", Source, settings).read()
    chunks = get_table("content_chunks", ContentChunk, settings).read()
    mappings = get_table("source_to_topic_mapping", SourceToTopicMapping, settings).read(filters={"topic_id": topic.id})

    source_by_id = {s.id: s for s in sources}
    topic_mappings = mappings
    if not topic_mappings:
        raise typer.BadParameter(f"No mappings for topic sn={sn}. Run 'map-topic --sn {sn}' first.")

    chunks_to_extract = selected_chunks(chunks, topic_mappings, max_chunks_per_source)
    if not chunks_to_extract:
        typer.echo("No chunks to process.")
        return

    typer.echo(f"Preparing batch file for {len(chunks_to_extract)} chunks...")

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
    from edu_curator.llm import create_batch_job, upload_batch_file

    try:
        file_bytes = jsonl_content.encode("utf-8")
        file_id = upload_batch_file(settings, file_bytes, f"topic_{sn}_extract.jsonl")
        typer.echo(f"OK: Uploaded batch input file. File ID: {file_id}")

        # Submit batch job
        batch_id = create_batch_job(settings, file_id)
        typer.echo(f"OK: Created batch job. Batch ID: {batch_id}")

        # Save batch job metadata locally
        batch_metadata = {
            "batch_id": batch_id,
            "input_file_id": file_id,
            "topic_sn": sn,
            "topic_id": topic.id,
            "status": "validating",
            "created_at": datetime.now(UTC).isoformat(),
        }
        batch_dir = DATA / "batches"
        batch_dir.mkdir(parents=True, exist_ok=True)
        with open(batch_dir / f"batch_{batch_id}.json", "w", encoding="utf-8") as f:
            json.dump(batch_metadata, f, indent=2)
        typer.echo("Batch metadata saved locally.")
    except Exception as exc:
        typer.echo(f"ERROR creating batch: {exc}")
        raise typer.Exit(code=1)


@app.command()
def check_batches() -> None:
    """Scan and retrieve completions for all pending Cerebras Batch jobs."""
    batch_dir = DATA / "batches"
    if not batch_dir.exists():
        typer.echo("No batch records found.")
        return

    batch_files = list(batch_dir.glob("batch_*.json"))
    if not batch_files:
        typer.echo("No batch files found.")
        return

    import json

    from edu_curator.extraction import fact_rows_from_extraction, get_schema_and_model, parse_json_robust
    from edu_curator.llm import ChatResult, download_file_content, retrieve_batch_job
    from edu_curator.token_logger import log_usage

    # Load database tables
    sources = get_table("sources", Source, settings).read()
    chunks = get_table("content_chunks", ContentChunk, settings).read()
    topics = get_table("syllabus_topics", SyllabusTopic, settings).read()

    source_by_id = {s.id: s for s in sources}
    chunk_by_id = {ck.id: ck for ck in chunks}
    topic_by_id = {t.id: t for t in topics}

    log_dir = DATA / "logs"

    for bf in batch_files:
        with open(bf, encoding="utf-8") as f:
            meta = json.load(f)

        batch_id = meta["batch_id"]
        status = meta.get("status")
        topic_sn = meta.get("topic_sn")

        if status in {"completed", "failed"}:
            continue

        typer.echo(f"Checking batch {batch_id} (topic sn={topic_sn})...")
        try:
            job = retrieve_batch_job(settings, batch_id)
            new_status = job.get("status")
            typer.echo(f"  Current status: {new_status}")

            meta["status"] = new_status
            meta["updated_at"] = datetime.now(UTC).isoformat()

            if new_status == "completed":
                output_file_id = job.get("output_file_id")
                if not output_file_id:
                    typer.echo("  ERROR: Batch marked as completed but has no output_file_id.")
                    meta["status"] = "failed"
                    meta["error_detail"] = "No output file ID found"
                else:
                    typer.echo("  Downloading completions output file...")
                    content = download_file_content(settings, output_file_id)

                    # Parse JSONL output
                    facts = []
                    errors = []

                    for line_num, line in enumerate(content.splitlines(), 1):
                        line = line.strip()
                        if not line:
                            continue
                        row = json.loads(line)
                        chunk_id = row.get("custom_id")
                        ck = chunk_by_id.get(chunk_id)
                        if not ck:
                            typer.echo(
                                f"  Warning: chunk ID {chunk_id} in output not found in local DB."
                            )
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
                            errors.append(
                                extraction_error(
                                    RuntimeError(err_msg), topic_by_id[ck.topic_id], ck
                                )
                            )
                            continue

                        ans_content = choices[0]["message"]["content"]

                        # Use robust JSON Repair
                        try:
                            payload = parse_json_robust(ans_content)
                            topic_obj = topic_by_id[meta["topic_id"]]
                            _, ExtractionModel = get_schema_and_model(topic_obj.topic_type)
                            extraction = ExtractionModel.model_validate(payload)
                            chunk_facts = fact_rows_from_extraction(
                                extraction,
                                topic_obj,
                                ck,
                                settings.extraction_model,
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
                                stage="extract_batch_offline",
                                model=settings.extraction_model,
                                topic_sn=topic_sn,
                            )
                        except Exception as exc:
                            errors.append(extraction_error(exc, topic_by_id[meta["topic_id"]], ck))

                    _append_json_table(
                        DATA / "extractions" / "fact_extractions.json",
                        FactExtraction,
                        facts,
                        delete_field="topic_id",
                        delete_value=meta["topic_id"],
                    )
                    _append_json_table(
                        DATA / "extractions" / "extraction_errors.json",
                        ExtractionError,
                        errors,
                        delete_field="topic_id",
                        delete_value=meta["topic_id"],
                    )
                    typer.echo(
                        f"  OK: Wrote {len(facts)} facts and {len(errors)} errors to Supabase."
                    )

            elif new_status in {"failed", "cancelled", "expired"}:
                typer.echo(f"  Job failed with status: {new_status}")
                meta["error_detail"] = f"Job finished with state {new_status}"

            # Write updated metadata
            with open(bf, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

        except Exception as exc:
            typer.echo(f"  Error processing batch {batch_id}: {exc}")


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


@app.command()
def resolve(sn: int = typer.Option(..., "--sn", help="Topic serial number to resolve")) -> None:
    """Resolve canonical knowledge for one topic."""
    from edu_curator.pipeline import run_resolve
    try:
        topic_knowledge = run_resolve(settings, sn=sn)
        typer.echo(f"OK: resolved '{_get_topic_by_sn(sn).topic_name}' — confidence={topic_knowledge.confidence}.")
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------


@app.command()
def generate_content(
    sn: int = typer.Option(..., "--sn", help="Topic serial number to generate"),
) -> None:
    """Generate educational content for one topic from its canonical knowledge.

    Token usage is logged to data/logs/token_usage.jsonl automatically.
    """
    from edu_curator.pipeline import run_generate_content
    try:
        topic_content, eval_result = run_generate_content(settings, sn=sn)
        typer.echo(
            f"OK: generated. review_status={topic_content.review_status}, "
            f"confidence={topic_content.confidence_score}."
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------


@app.command()
def check_consistency(
    sn: int = typer.Option(..., "--sn", help="Topic serial number to check"),
) -> None:
    """Run post-generation consistency check for one topic.

    Token usage is logged to data/logs/token_usage.jsonl automatically.
    """
    from edu_curator.pipeline import run_check_consistency
    try:
        updated, check_result = run_check_consistency(settings, sn=sn)
        verdict = "PASS" if updated.consistency_check_status else "FLAG"
        flags = (updated.consistency_check_flags or {}).get("flags", [])
        typer.echo(f"OK: verdict={verdict}, flags={len(flags)}.")
        for flag in flags:
            typer.echo(f"  FLAG: {flag}")
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    except RuntimeError as exc:
        typer.echo(f"ERROR: {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# run-topic (full pipeline for one topic in one command)
# ---------------------------------------------------------------------------


@app.command()
def run_topic(
    sn: int = typer.Option(..., "--sn", help="Topic serial number to run"),
    max_chunks_per_source: int = typer.Option(1, "--max-chunks-per-source"),
    batch_size: int = typer.Option(3, "--batch-size"),
    parallel: bool = typer.Option(False, "--parallel/--no-parallel"),
    force: bool = typer.Option(
        False, "--force/--no-force", help="Force pipeline execution even if inputs hash matches"
    ),
    use_batch_api: bool = typer.Option(
        None, "--use-batch-api/--no-batch-api", help="Use Cerebras Offline Batch API for extraction"
    ),
) -> None:
    """Run the full pipeline for one topic: chunk -> map -> extract -> resolve -> generate -> check.

    You must have already added sources with 'add-source --sn N ...' before running this.
    """
    from edu_curator.pipeline import run_full_pipeline
    try:
        run_full_pipeline(
            settings,
            sn=sn,
            max_chunks_per_source=max_chunks_per_source,
            batch_size=batch_size,
            parallel=parallel,
            force=force,
            use_batch_api=use_batch_api,
            echo_fn=typer.echo,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


# ---------------------------------------------------------------------------
# Token stats
# ---------------------------------------------------------------------------


@app.command()
def token_stats() -> None:
    """Show a summary of LLM token usage logged in data/logs/token_usage.jsonl."""
    summary = summarise_usage(DATA / "logs")

    if summary["total_calls"] == 0:
        typer.echo(
            "No token usage records found. Run 'extract', 'generate-content', or 'check-consistency' first."
        )
        return

    typer.echo("\n=======================================")
    typer.echo("  LLM TOKEN USAGE SUMMARY")
    typer.echo("=======================================")
    typer.echo(f"  Total LLM calls   : {summary['total_calls']:,}")
    typer.echo(f"  Prompt tokens     : {summary['total_prompt']:,}")
    typer.echo(f"  Completion tokens : {summary['total_completion']:,}")
    typer.echo(f"  TOTAL tokens      : {summary['total_tokens']:,}")

    typer.echo("\nBy stage:")
    for stage, b in sorted(summary["by_stage"].items()):
        typer.echo(
            f"  {stage:<18} calls={b['calls']:>4}  "
            f"prompt={b['prompt']:>7,}  completion={b['completion']:>7,}  total={b['total']:>8,}"
        )

    typer.echo("\nBy model:")
    for model, b in sorted(summary["by_model"].items()):
        typer.echo(f"  {model:<25} calls={b['calls']:>4}  total={b['total']:>8,}")

    typer.echo("\nBy topic (serial number):")
    for sn_key, b in sorted(summary["by_topic_sn"].items()):
        typer.echo(f"  sn={sn_key:<6} calls={b['calls']:>4}  total={b['total']:>8,}")
    typer.echo("")


# ---------------------------------------------------------------------------
# LLM utilities
# ---------------------------------------------------------------------------


@app.command()
def check_llm_config() -> None:
    """Validate LLM environment variables."""
    settings = load_settings(ROOT)
    if settings.llm_provider == "cerebras" and not settings.cerebras_api_key:
        raise typer.BadParameter("CEREBRAS_API_KEY is required for LLM_PROVIDER=cerebras.")
    if settings.llm_provider in {"huggingface", "hf"} and not settings.hf_token:
        raise typer.BadParameter("HF_TOKEN is required for Hugging Face.")
    typer.echo(f"OK: provider={settings.llm_provider}")
    typer.echo(f"OK: extraction_model={settings.extraction_model}")
    typer.echo(f"OK: generation_model={settings.generation_model}")


@app.command()
def test_llm() -> None:
    """Send a test JSON request to the configured LLM."""
    settings = load_settings(ROOT)
    result = chat_json(
        settings=settings,
        model=settings.extraction_model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": 'Return {"ok": true}.'},
        ],
    )
    typer.echo(result.content)


@app.command()
def list_models() -> None:
    """List available Cerebras models."""
    settings = load_settings(ROOT)
    if settings.llm_provider != "cerebras":
        raise typer.BadParameter("list-models currently supports Cerebras only.")
    for model in cerebras_public_models():
        model_id = model.get("id")
        name = model.get("name", "")
        json_mode = model.get("capabilities", {}).get("json_mode")
        typer.echo(f"{model_id} | {name} | json_mode={json_mode}")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    typer.echo("edu-curator 0.2.0")


@app.command()
def migrate_to_supabase() -> None:
    """Migrate all local JSON data to Supabase."""
    settings = load_settings(ROOT)
    if not settings.supabase_url or not settings.supabase_key:
        typer.secho("SUPABASE_URL and SUPABASE_KEY must be set in .env", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.echo("Starting migration to Supabase...")

    # We need to load from JsonTable explicitly, and write to SupabaseTable explicitly
    from supabase import create_client

    from edu_curator.storage import JsonTable, SupabaseTable

    supabase = create_client(settings.supabase_url, settings.supabase_key)

    tables = [
        ("syllabus_topics", SyllabusTopic, DATA / "seed" / "syllabus_topics.json"),
        ("sources", Source, DATA / "seed" / "sources.json"),
        ("content_chunks", ContentChunk, DATA / "chunks" / "content_chunks.json"),
        (
            "source_to_topic_mapping",
            SourceToTopicMapping,
            DATA / "mappings" / "source_to_topic_mapping.json",
        ),
        ("fact_extractions", FactExtraction, DATA / "extractions" / "fact_extractions.json"),
        ("extraction_errors", ExtractionError, DATA / "extractions" / "extraction_errors.json"),
        ("topic_knowledge", TopicKnowledge, DATA / "knowledge" / "topic_knowledge.json"),
        ("topic_content", TopicContent, DATA / "generated" / "topic_content.json"),
    ]

    for table_name, model_cls, path in tables:
        json_table = JsonTable(path, model_cls)
        rows = json_table.read()
        if not rows:
            typer.echo(f"Skipping {table_name}, no local data found.")
            continue

        typer.echo(f"Migrating {len(rows)} rows to {table_name}...")
        sb_table = SupabaseTable(table_name, model_cls, supabase)
        # Note: writing large batches might fail if rows > 1000,
        # but for our local MVP sizes it should be okay.
        # If needed, batch them in chunks of 500.
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            sb_table.write(rows[i : i + batch_size])

    typer.secho("Migration complete!", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# Background Queue Worker Daemon
# ---------------------------------------------------------------------------

import io


class SupabaseLogStream(io.StringIO):
    def __init__(self, job_id: str, settings, table_name="curation_jobs"):
        super().__init__()
        self.job_id = job_id
        self.settings = settings
        self.table_name = table_name
        self.buffer = []
        self.last_flush = time.time()
        self.terminal = sys.__stdout__

    def write(self, s):
        self.terminal.write(s)
        self.terminal.flush()
        self.buffer.append(s)
        # Flush periodically (every 1.5 seconds)
        if time.time() - self.last_flush > 1.5:
            self.flush_to_db()

    def flush(self):
        super().flush()
        self.flush_to_db()

    def flush_to_db(self):
        full_logs = "".join(self.buffer)
        try:
            from edu_curator.storage import get_table
            from edu_curator.schemas import CurationJob, EvaluationJob
            
            model_cls = EvaluationJob if self.table_name == "evaluation_jobs" else CurationJob
            jobs_tbl = get_table(self.table_name, model_cls, self.settings)
            jobs = jobs_tbl.read(filters={"id": self.job_id})
            if jobs:
                updated_job = jobs[0].model_copy(update={
                    "logs": full_logs,
                    "updated_at": datetime.now(UTC)
                })
                jobs_tbl.write([updated_job])
            self.last_flush = time.time()
        except Exception as e:
            self.terminal.write(f"\n[Worker DB Log Flush Error] {e}\n")
            self.terminal.flush()



@app.command()
def run_worker() -> None:
    """Start the background curation queue worker polling Supabase curation_jobs."""
    from datetime import datetime
    from edu_curator.storage import get_table
    from edu_curator.schemas import CurationJob

    settings = load_settings(ROOT)
    jobs_tbl = get_table("curation_jobs", CurationJob, settings)
    
    typer.echo("Background Curation Job Queue worker started. Listening for pending tasks...")

    while True:
        try:
            # Poll for one pending job
            # We can't sort locally but read() returns all, and we select the first pending.
            # In SupabaseTable read() executes a query. Filter by status="pending" gets them.
            # In JsonTable it reads from JSON and filters.
            jobs = jobs_tbl.read(filters={"status": "pending"})
            if not jobs:
                time.sleep(2)
                continue

            job = jobs[0]
            job_id = job.id
            topic_id = job.topic_id

            # Transition status to running
            updated_job = job.model_copy(update={
                "status": "running",
                "updated_at": datetime.now(UTC)
            })
            jobs_tbl.write([updated_job])

            typer.echo(f"\nExecuting Job ID: {job_id} for topic: {topic_id}")

            # Determine topic serial number
            topic_sn = None
            for sn_val in range(1, 100):
                if _topic_uuid(sn_val) == topic_id:
                    topic_sn = sn_val
                    break

            if topic_sn is None:
                raise ValueError(f"Could not resolve serial number for topic ID: {topic_id}")

            # Setup log redirect stream
            log_stream = SupabaseLogStream(job_id, settings)
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = log_stream
            sys.stderr = log_stream

            try:
                # Import dynamically inside run block to avoid circular import issues
                from edu_curator.cli import run_topic

                run_topic(sn=topic_sn, force=True)

                log_stream.flush()
                sys.stdout = old_stdout
                sys.stderr = old_stderr

                # Update status to completed
                jobs = jobs_tbl.read(filters={"id": job_id})
                if jobs:
                    updated_job = jobs[0].model_copy(update={
                        "status": "completed",
                        "updated_at": datetime.now(UTC)
                    })
                    jobs_tbl.write([updated_job])
                typer.echo(f"Job ID: {job_id} completed successfully.")

            except Exception as run_exc:
                log_stream.flush()
                sys.stdout = old_stdout
                sys.stderr = old_stderr

                err_msg = str(run_exc)
                jobs = jobs_tbl.read(filters={"id": job_id})
                if jobs:
                    updated_job = jobs[0].model_copy(update={
                        "status": "failed",
                        "error_message": err_msg,
                        "updated_at": datetime.now(UTC)
                    })
                    jobs_tbl.write([updated_job])
                typer.echo(f"Job ID: {job_id} failed with error: {err_msg}")

        except Exception as e:
            typer.echo(f"Worker iteration encountered error: {e}")
            time.sleep(5)


@app.command()
def evaluate(sn: int = typer.Option(..., "--sn", help="Topic serial number to evaluate")) -> None:
    """Evaluate generated curriculum using LLM-as-a-Judge."""
    from edu_curator.evaluation import evaluate_topic, print_evaluation_scorecard

    topic = _get_topic_by_sn(sn)
    contents = get_table("topic_content", TopicContent, settings).read(filters={"topic_id": topic.id})
    knowledges = get_table("topic_knowledge", TopicKnowledge, settings).read(filters={"topic_id": topic.id})

    content = contents[0] if contents else None
    knowledge = knowledges[0] if knowledges else None

    if not content:
        raise typer.BadParameter(f"No generated content found for topic sn={sn}.")
    if not knowledge:
        raise typer.BadParameter(f"No canonical knowledge found for topic sn={sn}.")

    typer.echo(f"Evaluating curriculum for topic '{topic.topic_name}'...")
    result = evaluate_topic(settings, topic, content, knowledge)
    
    if "error" not in result:
        try:
            from edu_curator.schemas import EvaluationResult
            from edu_curator.ids import new_id
            from datetime import datetime, UTC
            eval_table = get_table("evaluation_results", EvaluationResult, settings)
            eval_rec = EvaluationResult(
                id=new_id(),
                topic_id=topic.id,
                faithfulness_score=result.get("faithfulness_score"),
                completeness_score=result.get("completeness_score"),
                faithfulness_reasoning=result.get("faithfulness_reason"),
                completeness_reasoning=result.get("completeness_reason"),
                created_at=datetime.now(UTC)
            )
            eval_table.write([eval_rec])
            typer.echo("Successfully saved evaluation results to repository.")
        except Exception as db_exc:
            typer.echo(f"Warning: Failed to save evaluation results to repository: {db_exc}")


    print_evaluation_scorecard(topic.topic_name, result)


if __name__ == "__main__":
    from edu_curator.logging import setup_logging
    setup_logging()
    app()
