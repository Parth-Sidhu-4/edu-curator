"""
Lightweight dashboard server for Edu-Curator.

Reads SUPABASE_URL / SUPABASE_KEY from .env, injects them into index.html
as JavaScript globals, and serves the static dashboard on port 8502.

Optionally starts the background curation worker thread so that
pipeline functionality is preserved without needing a separate process.
"""

import os
import sys
import threading
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]
src_dir = str(ROOT / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

DASHBOARD_DIR = Path(__file__).resolve().parent

# ── Load .env ──────────────────────────────────────────────────────────────
load_dotenv(ROOT / ".env")

from edu_curator.config import load_settings
settings = load_settings(ROOT)

from edu_curator.storage import get_table, JsonTable, SupabaseTable
from edu_curator.schemas import (
    SyllabusTopic, Source, TopicContent, CurationJob, KnowledgeOverride,
    ReviewerActivity, KnowledgeOverrideHistory, EvaluationJob
)

logger = logging.getLogger("edu_curator.dashboard")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().strip('"')
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip().strip('"')
# SEC-05: Only ever serve the public anon key to the browser. Never fall back to
# the service_role key — that key bypasses RLS and must never leave the server.
_anon_key = (
    os.getenv("SUPABASE_ANON_KEY", "").strip().strip('"')
    or os.getenv("SUPABASE_PUBLIC_KEY", "").strip().strip('"')
)
if not _anon_key:
    logger.critical(
        "FATAL: SUPABASE_ANON_KEY is not set. "
        "Refusing to start — the service_role key must never be sent to browsers. "
        "Set SUPABASE_ANON_KEY in your .env file."
    )
    sys.exit(1)
SUPABASE_BROWSER_KEY = _anon_key
PORT = int(os.getenv("DASHBOARD_PORT", "8502"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")

# ── Build Hash (cache-busting) ────────────────────────────────────────────────
# Computed once at startup from the content of all JS and CSS files.
# Changes automatically whenever any frontend file is modified.
# Injected as {{BUILD_HASH}} into index.html so browsers re-fetch assets immediately.
import hashlib as _hashlib

def _compute_build_hash() -> str:
    h = _hashlib.sha256()
    for pattern in ("*.js", "*.css"):
        for f in sorted(DASHBOARD_DIR.rglob(pattern)):
            try:
                h.update(f.read_bytes())
            except Exception:
                pass
    return h.hexdigest()[:12]   # 12 hex chars is more than enough

BUILD_HASH = _compute_build_hash()
logger.info(f"Build hash computed: {BUILD_HASH}")

# L-01: Global thread lock for JSON storage writes
json_write_lock = threading.Lock()

# ── SN → UUID Reverse Lookup (built once at startup) ─────────────────────────
# Replaces the O(9,999) per-job scan loop that called uuid5() in a tight loop.
# Pre-building this dict at import time costs ~5ms and saves ~100ms per job.
import uuid as _uuid_mod

_SDLC_TOPIC_UUID = "11111111-1111-1111-1111-111111111111"
_MAX_TOPIC_SN = 9999


def _build_sn_reverse_lookup() -> dict[str, int]:
    lookup: dict[str, int] = {_SDLC_TOPIC_UUID: 1}
    for sn in range(2, _MAX_TOPIC_SN + 1):
        uid = str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_DNS, f"devops-topic-sn-{sn}"))
        lookup[uid] = sn
    return lookup


# Built once when the module loads. Takes ~5ms. Never recomputed.
_TOPIC_UUID_TO_SN: dict[str, int] = _build_sn_reverse_lookup()

# AUTH-01: Email allowlist — only these addresses may use the dashboard.
# Comma-separated in .env: ALLOWED_EMAILS=you@gmail.com,colleague@example.com
# Leave empty to allow ANY authenticated Supabase user (not recommended for production).
_raw_allowed = os.getenv("ALLOWED_EMAILS", "")
ALLOWED_EMAILS: set[str] = {
    e.strip().lower() for e in _raw_allowed.split(",") if e.strip()
}
if not ALLOWED_EMAILS:
    logger.warning(
        "ALLOWED_EMAILS is not set. "
        "Any authenticated Supabase user can access this dashboard. "
        "Set ALLOWED_EMAILS=your@email.com in .env to restrict access."
    )


def validate_file_signature(file_bytes: bytes, ext: str) -> bool:
    ext = ext.lower().strip()
    if not file_bytes:
        return True
    if ext == ".pdf":
        return file_bytes.startswith(b"%PDF")
    elif ext == ".png":
        return file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext in (".jpg", ".jpeg"):
        return file_bytes.startswith(b"\xff\xd8\xff")
    elif ext == ".pptx":
        if not file_bytes.startswith(b"PK\x03\x04"):
            return False
        import zipfile
        import io
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                names = z.namelist()
                return "[Content_Types].xml" in names and any("ppt/presentation.xml" in n for n in names)
        except Exception:
            return False
    elif ext in (".txt", ".md", ".csv", ".html", ".htm"):
        try:
            file_bytes.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return True


def _get_restricted_env():
    """Return a restricted env dictionary containing only keys required by the subprocess."""
    import os
    allowed_keys = {
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_ANON_KEY",
        "CEREBRAS_API_KEY",
        "GROQ_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "REDIS_URL",
        "LLM_CACHE_ENABLED",
        "PLAYWRIGHT_ENABLED",
        "LLM_PROVIDER",
        "EXTRACTION_MODEL",
        "GENERATION_MODEL",
        "FALLBACK_MODEL",
        "LITELLM_FALLBACK_ENABLED",
        "LOG_LLM_LOCALLY",
        "PATH",
        "SYSTEMROOT",
        "COMSPEC",
        "TEMP",
        "TMP",
        # Windows user-profile variables required by Python packages (transformers,
        # torch, huggingface_hub, etc.) to locate the home directory cache.
        # Without these, transformers falls back to the Unix-only 'pwd' module
        # and raises ModuleNotFoundError: No module named 'pwd' on Windows.
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "USERNAME",
        "PROGRAMDATA",
        "WINDIR",
    }
    env = {}
    for key in allowed_keys:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ── Background worker (preserves Streamlit worker functionality) ───────────
def start_background_worker():
    """Spawn the curation queue worker in a daemon thread."""

    def _worker():
        # Add src to path so edu_curator is importable
        src = str(ROOT / "src")
        if src not in sys.path:
            sys.path.insert(0, src)

        from datetime import datetime, timezone
        from supabase import create_client
        from edu_curator.config import load_settings

        settings = load_settings(ROOT)
        if not settings.supabase_url or not settings.supabase_key:
            logger.warning("No Supabase credentials — worker disabled.")
            return

        supabase = create_client(settings.supabase_url, settings.supabase_key)

        # Reset stuck jobs
        try:
            from edu_curator.storage import get_table
            from edu_curator.schemas import CurationJob
            curation_jobs_tbl = get_table("curation_jobs", CurationJob, settings)
            stuck_jobs = curation_jobs_tbl.read(filters={"status": "running"})
            for j in stuck_jobs:
                j.status = "failed"
                j.error_message = "Worker restarted. Stale job aborted."
                j.updated_at = datetime.now(timezone.utc)
            if stuck_jobs:
                curation_jobs_tbl.write(stuck_jobs)
        except Exception:
            pass

        logger.info("Background curation worker started. Polling for jobs…")
        _last_stuck_check = 0.0
        while True:
            # Periodically reset jobs that got stuck in 'running' (e.g. from a mid-run crash).
            # This runs every 5 minutes without needing a full server restart.
            now_t = time.time()
            if now_t - _last_stuck_check > 300:
                try:
                    from edu_curator.storage import get_table
                    from edu_curator.schemas import CurationJob
                    _stuck_tbl = get_table("curation_jobs", CurationJob, settings)
                    _stuck_jobs = _stuck_tbl.read(filters={"status": "running"})
                    _newly_stuck = [
                        j for j in _stuck_jobs
                        if j.updated_at and (datetime.now(timezone.utc) - j.updated_at).total_seconds() > 1200
                    ]
                    if _newly_stuck:
                        for j in _newly_stuck:
                            j.status = "failed"
                            j.error_message = "Auto-reset: job was stuck in running state for >20 minutes."
                            j.updated_at = datetime.now(timezone.utc)
                        _stuck_tbl.write(_newly_stuck)
                        logger.warning(f"Periodic stuck-job sweep: reset {len(_newly_stuck)} stuck job(s).")
                except Exception as _stuck_exc:
                    logger.warning(f"Stuck-job sweep failed: {_stuck_exc}")
                _last_stuck_check = now_t
            try:
                # F-16: Claim job atomically via RPC
                res = supabase.rpc("claim_next_job", {"worker_name": "CurationWorker"}).execute()
                jobs = res.data
                if not jobs:
                    time.sleep(2)
                    continue

                job = jobs[0]
                job_id = job["id"]
                topic_id = job["topic_id"]

                # Resolve serial number via pre-built O(1) reverse lookup dict.
                # Replaces the old O(9999) scan loop that called uuid5() per iteration.
                topic_sn = _TOPIC_UUID_TO_SN.get(topic_id)

                if topic_sn is None:
                    from edu_curator.storage import get_table
                    from edu_curator.schemas import CurationJob
                    curation_jobs_tbl = get_table("curation_jobs", CurationJob, settings)
                    job_records = curation_jobs_tbl.read(filters={"id": job_id})
                    if job_records:
                        job_records[0].status = "failed"
                        job_records[0].error_message = f"Cannot resolve SN for topic {topic_id}"
                        job_records[0].updated_at = datetime.now(timezone.utc)
                        curation_jobs_tbl.write([job_records[0]])
                    continue

                # Execute pipeline
                import subprocess

                cmd = [sys.executable, "-m", "edu_curator.cli", "run-topic", "--sn", str(topic_sn), "--force", "--no-parallel", "--batch-size", "1"]
                # F-08: Narrow env dict
                env = _get_restricted_env()
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", cwd=str(ROOT), env=env)

                # SRE: Non-blocking log reading with 15-minute execution timeout
                import queue
                q = queue.Queue()
                def enqueue_output(out, q):
                    try:
                        for line in iter(out.readline, ''):
                            q.put(line)
                    except Exception:
                        pass
                    finally:
                        try:
                            out.close()
                        except Exception:
                            pass
                
                t_reader = threading.Thread(target=enqueue_output, args=(proc.stdout, q), daemon=True)
                t_reader.start()

                log_lines = []
                last_flush = time.time()
                start_time = time.time()
                timeout_limit = 900.0  # 15 minutes
                timed_out = False

                while True:
                    if time.time() - start_time > timeout_limit:
                        proc.kill()
                        timed_out = True
                        break
                    
                    try:
                        line = q.get_nowait()
                    except queue.Empty:
                        line = None

                    if line is not None:
                        log_lines.append(line)
                        # Cap log lines to prevent OOM on verbose jobs.
                        # Keeps the last 5,000 lines (most recent are most useful).
                        if len(log_lines) > 5000:
                            log_lines = log_lines[-5000:]
                        if time.time() - last_flush > 10.0:  # flush every 10s (was 2s)
                            from edu_curator.storage import get_table
                            from edu_curator.schemas import CurationJob
                            curation_jobs_tbl = get_table("curation_jobs", CurationJob, settings)
                            job_records = curation_jobs_tbl.read(filters={"id": job_id})
                            if job_records:
                                job_records[0].logs = "".join(log_lines)
                                job_records[0].updated_at = datetime.now(timezone.utc)
                                curation_jobs_tbl.write([job_records[0]])
                            last_flush = time.time()
                    else:
                        if proc.poll() is not None:
                            # Drain remaining queue logs
                            while not q.empty():
                                try:
                                    log_lines.append(q.get_nowait())
                                except queue.Empty:
                                    break
                            break
                        time.sleep(0.1)

                rc = proc.poll()
                from edu_curator.storage import get_table
                from edu_curator.schemas import CurationJob
                curation_jobs_tbl = get_table("curation_jobs", CurationJob, settings)
                job_records = curation_jobs_tbl.read(filters={"id": job_id})
                if job_records:
                    job_records[0].logs = "".join(log_lines)
                    job_records[0].status = "completed" if (rc == 0 and not timed_out) else "failed"
                    if rc != 0:
                        job_records[0].error_message = f"Pipeline exited with code {rc}"
                    job_records[0].updated_at = datetime.now(timezone.utc)
                    curation_jobs_tbl.write([job_records[0]])

            except Exception as exc:
                try:
                    import traceback
                    traceback.print_exc()
                    # F-12: Mask exception string in database
                    from edu_curator.storage import get_table
                    from edu_curator.schemas import CurationJob
                    curation_jobs_tbl = get_table("curation_jobs", CurationJob, settings)
                    job_records = curation_jobs_tbl.read(filters={"id": job_id})
                    if job_records:
                        job_records[0].status = "failed"
                        job_records[0].error_message = "Pipeline execution failed. Check server logs."
                        job_records[0].updated_at = datetime.now(timezone.utc)
                        curation_jobs_tbl.write([job_records[0]])
                except Exception:
                    pass
                time.sleep(2)

    t = threading.Thread(target=_worker, daemon=True, name="CurationWorker")
    t.start()
    return t


def run_ingest(source_id):
    """Run ingestion in a background thread/subprocess and update the database on failure."""
    from datetime import datetime, timezone
    import subprocess
    import queue
    logger.info(f"Starting ingestion task for source: {source_id}")
    cmd = [sys.executable, "-m", "edu_curator.cli", "ingest-single", "--id", source_id]
    env = _get_restricted_env()
    try:
        proc = subprocess.Popen(cmd, env=env, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        
        q = queue.Queue()
        def enqueue_output(out, q):
            try:
                for line in iter(out.readline, ''):
                    q.put(line)
            except Exception:
                pass
            finally:
                try:
                    out.close()
                except Exception:
                    pass
        
        t_reader = threading.Thread(target=enqueue_output, args=(proc.stdout, q), daemon=True)
        t_reader.start()

        log_lines = []
        start_time = time.time()
        timeout_limit = 900.0  # 15 minutes
        timed_out = False

        while True:
            if time.time() - start_time > timeout_limit:
                proc.kill()
                timed_out = True
                break
            
            try:
                line = q.get_nowait()
            except queue.Empty:
                line = None

            if line is not None:
                log_lines.append(line)
            else:
                if proc.poll() is not None:
                    while not q.empty():
                        try:
                            log_lines.append(q.get_nowait())
                        except queue.Empty:
                            break
                    break
                time.sleep(0.1)

        rc = proc.poll()
        if rc != 0 or timed_out:
            raise Exception(f"Ingest subprocess failed with code {rc} (timed_out={timed_out})")
            
    except Exception as e:
        logger.error(f"Ingestion error for source {source_id}: {e}")
        try:
            from edu_curator.storage import get_table
            from edu_curator.schemas import Source
            sources_tbl = get_table("sources", Source, settings)
            sources = sources_tbl.read(filters={"id": source_id})
            if sources:
                updated_source = sources[0].model_copy(update={
                    "crawl_status": "failed",
                    "updated_at": datetime.now(timezone.utc)
                })
                sources_tbl.write([updated_source])
        except Exception as sync_exc:
            logger.warning(f"Failed to sync crawl status: {sync_exc}")



def run_evaluation_task(topic_sn, job_id=None):
    """Run evaluation command in the background, streaming logs if job_id is provided."""
    from datetime import datetime, timezone
    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    import subprocess
    cmd = [sys.executable, "-m", "edu_curator.cli", "evaluate", "--sn", str(topic_sn)]
    # F-08: Narrow env dict
    env = _get_restricted_env()
    
    logger.info(f"Evaluation started for topic SN: {topic_sn} (Job ID: {job_id})")
    
    if job_id:
        try:
            from edu_curator.storage import get_table
            from edu_curator.schemas import EvaluationJob
            eval_jobs_tbl = get_table("evaluation_jobs", EvaluationJob, settings)
            jobs = eval_jobs_tbl.read(filters={"id": job_id})
            if jobs:
                updated_job = jobs[0].model_copy(update={
                    "status": "running",
                    "updated_at": datetime.now(timezone.utc)
                })
                eval_jobs_tbl.write([updated_job])
        except Exception as e:
            logger.warning(f"Failed to transition evaluation job status: {e}")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
        
        import queue
        q = queue.Queue()
        def enqueue_output(out, q):
            try:
                for line in iter(out.readline, ''):
                    q.put(line)
            except Exception:
                pass
            finally:
                try:
                    out.close()
                except Exception:
                    pass
        
        t_reader = threading.Thread(target=enqueue_output, args=(proc.stdout, q), daemon=True)
        t_reader.start()

        log_lines = []
        last_flush = time.time()
        start_time = time.time()
        timeout_limit = 900.0  # 15 minutes
        timed_out = False

        while True:
            if time.time() - start_time > timeout_limit:
                proc.kill()
                timed_out = True
                break

            try:
                line = q.get_nowait()
            except queue.Empty:
                line = None

            if line is not None:
                log_lines.append(line)
                # Cap log lines to prevent OOM on verbose jobs.
                if len(log_lines) > 5000:
                    log_lines = log_lines[-5000:]
                if job_id and (time.time() - last_flush > 10.0):
                    try:
                        from edu_curator.storage import get_table
                        from edu_curator.schemas import EvaluationJob
                        eval_jobs_tbl = get_table("evaluation_jobs", EvaluationJob, settings)
                        jobs = eval_jobs_tbl.read(filters={"id": job_id})
                        if jobs:
                            updated_job = jobs[0].model_copy(update={
                                "logs": "".join(log_lines),
                                "updated_at": datetime.now(timezone.utc)
                            })
                            eval_jobs_tbl.write([updated_job])
                            last_flush = time.time()
                    except Exception as db_exc:
                        logger.warning(f"Failed to flush evaluation logs: {db_exc}")
            else:
                if proc.poll() is not None:
                    while not q.empty():
                        try:
                            log_lines.append(q.get_nowait())
                        except queue.Empty:
                            break
                    break
                time.sleep(0.1)
                        
        rc = proc.poll()
        if job_id:
            try:
                from edu_curator.storage import get_table
                from edu_curator.schemas import EvaluationJob
                eval_jobs_tbl = get_table("evaluation_jobs", EvaluationJob, settings)
                jobs = eval_jobs_tbl.read(filters={"id": job_id})
                if jobs:
                    final_update = {
                        "logs": "".join(log_lines),
                        "status": "completed" if (rc == 0 and not timed_out) else "failed",
                        "updated_at": datetime.now(timezone.utc)
                    }
                    if rc != 0:
                        final_update["error_message"] = f"Evaluation exited with code {rc}"
                    updated_job = jobs[0].model_copy(update=final_update)
                    eval_jobs_tbl.write([updated_job])
            except Exception as e:
                logger.warning(f"Failed to complete evaluation job in DB: {e}")
                
        logger.info(f"Evaluation completed for topic SN {topic_sn}. Return code: {rc}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        # F-12: Mask exception string in database
        if job_id:
            try:
                from edu_curator.storage import get_table
                from edu_curator.schemas import EvaluationJob
                eval_jobs_tbl = get_table("evaluation_jobs", EvaluationJob, settings)
                jobs = eval_jobs_tbl.read(filters={"id": job_id})
                if jobs:
                    updated_job = jobs[0].model_copy(update={
                        "status": "failed",
                        "error_message": "Evaluation execution failed. Check server logs.",
                        "updated_at": datetime.now(timezone.utc)
                    })
                    eval_jobs_tbl.write([updated_job])
            except Exception:
                pass


def get_raw_content(topic_id: str, content_json: dict) -> dict:
    """Reconstruct the original raw generated content by removing active overrides."""
    try:
        table = get_table("knowledge_overrides", KnowledgeOverride, settings)
        overrides = table.read(filters={"topic_id": topic_id, "is_active": True})
    except Exception as exc:
        logger.warning(f"Error fetching overrides: {exc}")
        overrides = []

    raw_content = content_json.copy()
    for o in overrides:
        field = o.field_name
        if field in raw_content:
            raw_content[field] = o.original_value
    return raw_content


def save_knowledge_overrides(topic_id: str, reviewer_id: str, edited_content: dict, raw_content: dict, note: str = ""):
    """Compare edited content to raw content and save overrides to Supabase."""
    from datetime import datetime, timezone
    from edu_curator.ids import new_id
    now = datetime.now(timezone.utc)

    try:
        table = get_table("knowledge_overrides", KnowledgeOverride, settings)
        overrides = table.read(filters={"topic_id": topic_id, "is_active": True})
        existing_overrides = {o.field_name: o for o in overrides}
    except Exception as exc:
        logger.warning(f"Error fetching existing overrides: {exc}")
        existing_overrides = {}

    try:
        history_table = get_table("knowledge_override_history", KnowledgeOverrideHistory, settings)
    except Exception as exc:
        logger.warning(f"Error getting history table: {exc}")
        history_table = None

    for field_name, edited_val in edited_content.items():
        raw_val = raw_content.get(field_name)

        if edited_val != raw_val:
            # Override is needed
            if field_name in existing_overrides:
                existing_o = existing_overrides[field_name]
                if existing_o.corrected_value != edited_val:
                    updated_o = existing_o.model_copy(update={
                        "corrected_value": edited_val,
                        "correction_note": note,
                        "reviewer_id": reviewer_id,
                        "updated_at": now
                    })
                    table.write([updated_o])
                    if history_table and isinstance(table, JsonTable):
                        history_rec = KnowledgeOverrideHistory(
                            id=new_id(),
                            override_id=existing_o.id,
                            topic_id=topic_id,
                            field_name=field_name,
                            old_value=existing_o.corrected_value,
                            new_value=edited_val,
                            reviewer_id=reviewer_id,
                            changed_at=now
                        )
                        try:
                            history_table.write(history_table.read() + [history_rec])
                        except Exception as e:
                            logger.error(f"Error writing history: {e}")
            else:
                new_o = KnowledgeOverride(
                    id=new_id(),
                    topic_id=topic_id,
                    field_name=field_name,
                    original_value=raw_val,
                    corrected_value=edited_val,
                    correction_note=note,
                    reviewer_id=reviewer_id,
                    is_active=True,
                    created_at=now,
                    updated_at=now
                )
                table.write([new_o])
                if history_table and isinstance(table, JsonTable):
                    history_rec = KnowledgeOverrideHistory(
                        id=new_id(),
                        override_id=new_o.id,
                        topic_id=topic_id,
                        field_name=field_name,
                        old_value=raw_val,
                        new_value=edited_val,
                        reviewer_id=reviewer_id,
                        changed_at=now
                    )
                    try:
                        history_table.write(history_table.read() + [history_rec])
                    except Exception as e:
                        logger.error(f"Error writing history: {e}")
        else:
            # Reverted to raw, mark existing override as inactive
            if field_name in existing_overrides:
                existing_o = existing_overrides[field_name]
                updated_o = existing_o.model_copy(update={
                    "is_active": False,
                    "updated_at": now
                })
                table.write([updated_o])
                if history_table and isinstance(table, JsonTable):
                    history_rec = KnowledgeOverrideHistory(
                        id=new_id(),
                        override_id=existing_o.id,
                        topic_id=topic_id,
                        field_name=field_name,
                        old_value=existing_o.corrected_value,
                        new_value=None,
                        reviewer_id=reviewer_id,
                        changed_at=now
                    )
                    try:
                        history_table.write(history_table.read() + [history_rec])
                    except Exception as e:
                        logger.error(f"Error writing history: {e}")


# SEC-10: Rate Limiting Globals (IP-based, thread-safe)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 60  # max requests per window
RATE_LIMIT_AUTH_MAX = 30  # tighter auth limit to prevent brute force / DoS on Supabase auth
ip_request_history = {}  # IP -> list of floats
auth_request_history = {}  # IP -> list of floats
ip_history_lock = threading.Lock()

_redis_server_client = None
_redis_server_client_initialized = False

def _get_server_redis():
    global _redis_server_client, _redis_server_client_initialized
    if not _redis_server_client_initialized:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                # SRE: Configure socket timeouts to prevent block stalls under heavy latency/network outages
                _redis_server_client = redis.Redis.from_url(
                    redis_url, 
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0
                )
                logger.info("Server rate-limiter connected to Redis.")
            except Exception as e:
                logger.warning(f"Server rate-limiter failed to connect to Redis: {e}")
        _redis_server_client_initialized = True
    return _redis_server_client


# ── FastAPI App Setup ────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan handler — replaces the deprecated @app.on_event('startup')."""
    # ── Startup ──────────────────────────────────────────────────────────────
    # Sync allowed emails to Supabase table
    if ALLOWED_EMAILS and SUPABASE_URL and SUPABASE_KEY:
        try:
            from supabase import create_client
            admin_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            admin_client.table("allowed_emails").upsert([{"email": e} for e in ALLOWED_EMAILS]).execute()
            logger.info(f"Successfully synced {len(ALLOWED_EMAILS)} allowed emails to Supabase table (upsert mode).")
        except Exception as sync_exc:
            logger.warning(f"Failed to sync allowed emails: {sync_exc}")

    # Launch background curation worker
    run_in_process_worker = os.getenv("START_IN_PROCESS_WORKER", "true").lower() not in {"false", "0", "no"}
    if run_in_process_worker:
        global _background_worker_thread
        _background_worker_thread = start_background_worker()
        worker_status = "active"
    else:
        worker_status = "disabled"

    # Launch in-memory rate-limiter cleanup thread (prevents unbounded dict growth)
    def _rl_cleanup_loop():
        while True:
            time.sleep(300)   # run every 5 minutes
            cutoff = time.time() - RATE_LIMIT_WINDOW
            with ip_history_lock:
                for d in (ip_request_history, auth_request_history):
                    stale_ips = [ip for ip, ts_list in d.items() if not ts_list or max(ts_list) < cutoff]
                    for ip in stale_ips:
                        del d[ip]

    _rl_cleanup = threading.Thread(target=_rl_cleanup_loop, daemon=True, name="RateLimiterCleanup")
    _rl_cleanup.start()

    from urllib.parse import urlparse
    parsed_supabase = urlparse(SUPABASE_URL)
    redacted_supabase_url = f"{parsed_supabase.scheme}://{parsed_supabase.netloc}" if parsed_supabase.netloc else "configured"

    logger.info(f"Edu-Curator Dashboard API Started")
    logger.info(f"  -> Dashboard Interface: http://{DASHBOARD_HOST}:{PORT}")
    logger.info(f"  -> Health Check:        http://{DASHBOARD_HOST}:{PORT}/health")
    logger.info(f"  -> Supabase Endpoint: {redacted_supabase_url}")
    logger.info(f"  -> Background Worker Status: {worker_status}")
    logger.info(f"  -> Build Hash: {BUILD_HASH}")

    yield  # Application runs here

    # ── Shutdown (nothing special needed) ────────────────────────────────────
    logger.info("Edu-Curator Dashboard shutting down.")


app = FastAPI(title="Edu-Curator Dashboard API", lifespan=lifespan)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Apply rate limiting specifically on POST requests (endpoints mutate data or auth)
    if request.method == "POST":
        ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        is_auth = request.url.path == "/api/auth/verify"
        
        max_reqs = RATE_LIMIT_AUTH_MAX if is_auth else RATE_LIMIT_MAX_REQUESTS
        prefix = "rate_auth:" if is_auth else "rate_api:"
        redis_key = f"{prefix}{ip}"
        
        r_client = _get_server_redis()
        rate_limit_exceeded = False
        
        if r_client:
            try:
                p = r_client.pipeline()
                p.zremrangebyscore(redis_key, 0, now - RATE_LIMIT_WINDOW)
                p.zadd(redis_key, {str(now): now})
                p.zcard(redis_key)
                p.expire(redis_key, RATE_LIMIT_WINDOW + 5)
                results = p.execute()
                
                count = results[2]
                if count > max_reqs:
                    rate_limit_exceeded = True
            except Exception as e:
                logger.warning(f"Redis rate check fallback triggered: {e}")
                
        if not r_client or rate_limit_exceeded is False:
            with ip_history_lock:
                history = auth_request_history if is_auth else ip_request_history
                if ip not in history:
                    history[ip] = []
                history[ip] = [t for t in history[ip] if now - t < RATE_LIMIT_WINDOW]
                if len(history[ip]) >= max_reqs:
                    rate_limit_exceeded = True
                else:
                    history[ip].append(now)
                    
        if rate_limit_exceeded:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests. Please try again later."}
            )
            
    return await call_next(request)


def is_email_allowed(email: str) -> bool:
    """Check if the given email is present in the database allowed_emails table."""
    email_lower = email.strip().lower()
    
    # 1. Fallback to memory set if database credentials are not set
    if not SUPABASE_URL or not SUPABASE_KEY:
        return not ALLOWED_EMAILS or email_lower in ALLOWED_EMAILS
        
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Check if the allowed_emails table is empty. If it is, allow any authenticated user.
        # Otherwise, check if the email exists.
        # This mirrors the behavior of the database is_allowed_user() PL/pgSQL function.
        res_count = client.table("allowed_emails").select("email", count="exact").limit(1).execute()
        if res_count.count == 0:
            return True
            
        res = client.table("allowed_emails").select("email").eq("email", email_lower).execute()
        return len(res.data) > 0
    except Exception as exc:
        logger.warning(f"Error checking email allowlist dynamically: {exc}")
        # Secure fallback: if database query fails, fall back to the in-memory ALLOWED_EMAILS list
        return not ALLOWED_EMAILS or email_lower in ALLOWED_EMAILS


# Security / Auth Dependency
def get_current_user_email(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorised: missing or invalid token")
    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorised: missing or invalid token")
    
    try:
        from supabase import create_client
        admin = create_client(SUPABASE_URL, SUPABASE_KEY)
        res = admin.auth.get_user(token)
        user = res.user
        if not user or not user.email:
            raise HTTPException(status_code=401, detail="Unauthorised: missing or invalid token")
        email = user.email.lower()
    except Exception as exc:
        logger.warning(f"Token verification failed: {exc}")
        raise HTTPException(status_code=401, detail="Unauthorised: missing or invalid token")

    if not is_email_allowed(email):
        raise HTTPException(status_code=403, detail="Forbidden: access denied")
    return email


# ── Static File Routes ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def read_index(request: Request):
    import secrets
    nonce = secrets.token_urlsafe(16)
    supabase_src = f" {SUPABASE_URL}" if SUPABASE_URL else ""
    csp = (
        "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://unpkg.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        f"img-src 'self' data:{supabase_src}; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com https://cdn.jsdelivr.net; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        f"connect-src 'self' {SUPABASE_URL} wss://{SUPABASE_URL.replace('https://', '')} https://cdn.jsdelivr.net;"
    )
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Content-Security-Policy": csp
    }
    html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{SUPABASE_URL_VALUE}}", SUPABASE_URL)
    html = html.replace("{{SUPABASE_KEY_VALUE}}", SUPABASE_BROWSER_KEY)
    html = html.replace("{{CSP_NONCE}}", nonce)
    html = html.replace("{{BUILD_HASH}}", BUILD_HASH)
    return HTMLResponse(content=html, headers=headers)


@app.get("/app.js")
def get_app_js():
    # Versioned via ?v=BUILD_HASH — safe to cache for 1 year
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}
    return FileResponse(DASHBOARD_DIR / "app.js", headers=headers)


@app.get("/style.css")
def get_style_css():
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}
    return FileResponse(DASHBOARD_DIR / "style.css", headers=headers)


@app.get("/purify.min.js")
def get_purify_js():
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}
    return FileResponse(DASHBOARD_DIR / "purify.min.js", headers=headers)


@app.get("/data/uploads/{filename}")
def serve_upload(filename: str):
    uploads_dir = (ROOT / "data" / "uploads").resolve()
    file_path = (uploads_dir / filename).resolve()
    
    # Path traversal validation
    if uploads_dir not in file_path.parents and uploads_dir != file_path:
        raise HTTPException(status_code=400, detail="Path traversal attempt detected")
        
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
    return FileResponse(file_path, headers=headers)


@app.get("/{path:path}.js")
def get_js_file(path: str):
    allowed_js = {
        "app", "state", "utils", "api", "auth",
        "views/index", "views/overview", "views/content",
        "views/topics", "views/sources", "views/observability",
        "views/evaluation"
    }
    if path not in allowed_js:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = DASHBOARD_DIR / f"{path}.js"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Versioned via ?v=BUILD_HASH — safe to cache for 1 year
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}
    return FileResponse(file_path, headers=headers)



# ── Health Check ─────────────────────────────────────────────────────────────

_server_start_time = time.time()
_background_worker_thread: threading.Thread | None = None  # set by on_startup

@app.get("/health")
def health_check():
    """
    Liveness + readiness probe.

    Returns 200 when the server is up and the database is reachable.
    Returns 503 if the database ping fails.

    Used by: Docker HEALTHCHECK, uptime monitors, load balancers.
    """
    uptime_seconds = int(time.time() - _server_start_time)

    # Lightweight DB ping — count rows in a small table rather than a full read
    db_status = "ok"
    try:
        from supabase import create_client
        _ping_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _ping_client.table("syllabus_topics").select("id", count="exact").limit(1).execute()
    except Exception as db_exc:
        logger.warning(f"Health check DB ping failed: {db_exc}")
        db_status = "unreachable"

    worker_alive = (
        _background_worker_thread is not None
        and _background_worker_thread.is_alive()
    )

    payload = {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "worker": "alive" if worker_alive else "stopped",
        "uptime_seconds": uptime_seconds,
    }

    status_code = 200 if db_status == "ok" else 503
    return JSONResponse(content=payload, status_code=status_code)


# ── JSON API Routes ──────────────────────────────────────────────────────────

@app.post("/api/auth/verify")
def verify_auth_token(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")
    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        from supabase import create_client
        admin = create_client(SUPABASE_URL, SUPABASE_KEY)
        res = admin.auth.get_user(token)
        user = res.user
        if not user or not user.email:
            raise HTTPException(status_code=401, detail="Invalid token")
        email = user.email.lower()
    except Exception as exc:
        logger.warning(f"Token verification failed: {exc}")
        raise HTTPException(status_code=401, detail="Invalid token")

    if not is_email_allowed(email):
        raise HTTPException(status_code=403, detail="Access denied")
    return {"ok": True, "email": email}


@app.post("/api/topic")
def manage_topic(body: dict, email: str = Depends(get_current_user_email)):
    action = body.get("action")
    table = get_table("syllabus_topics", SyllabusTopic, settings)
    
    if action == "insert":
        payload = body.get("topic")
        if not payload:
            raise HTTPException(status_code=400, detail="topic is required")
        ALLOWED_TOPIC_FIELDS = {"id", "chapter", "topic_name", "topic_type", "keywords", "difficulty_level"}
        if "id" not in payload:
            from edu_curator.ids import new_id
            payload["id"] = new_id()
        filtered_payload = {k: v for k, v in payload.items() if k in ALLOWED_TOPIC_FIELDS}
        if not filtered_payload:
            raise HTTPException(status_code=400, detail="No valid topic fields provided")
        topic_obj = SyllabusTopic.model_validate(filtered_payload)
        res_data = table.write([topic_obj])
        return {"status": "inserted", "data": res_data}
        
    if action == "update":
        topic_id = body.get("id")
        fields = body.get("fields")
        if not topic_id or not isinstance(fields, dict):
            raise HTTPException(status_code=400, detail="id and fields are required")
        topic_obj = next(iter(table.read(filters={"id": topic_id})), None)
        if not topic_obj:
            raise HTTPException(status_code=404, detail="Topic not found")
        ALLOWED_TOPIC_FIELDS = {"chapter", "topic_name", "topic_type", "keywords", "difficulty_level", "status"}
        filtered_fields = {k: v for k, v in fields.items() if k in ALLOWED_TOPIC_FIELDS}
        if not filtered_fields:
            raise HTTPException(status_code=400, detail="No valid update fields provided")
        updated_obj = topic_obj.model_copy(update=filtered_fields)
        res_data = table.write([updated_obj])
        return {"status": "updated", "data": res_data}
        
    if action == "delete":
        topic_id = body.get("id")
        if not topic_id:
            raise HTTPException(status_code=400, detail="id is required")
        table.delete("id", topic_id)
        return {"status": "deleted", "data": [{"id": topic_id}]}
        
    raise HTTPException(status_code=400, detail="unknown topic action")


@app.post("/api/source")
def manage_source(body: dict, email: str = Depends(get_current_user_email)):
    source = body.get("source")
    if not source:
        raise HTTPException(status_code=400, detail="source is required")
    ALLOWED_SOURCE_FIELDS = {"id", "title", "source_type", "url", "local_path", "trust_score", "license_type", "publication_date", "owner", "topic_ids"}
    if "id" not in source:
        from edu_curator.ids import new_id
        source["id"] = new_id()
    filtered_source = {k: v for k, v in source.items() if k in ALLOWED_SOURCE_FIELDS}
    if not filtered_source:
        raise HTTPException(status_code=400, detail="No valid source fields provided")
    table = get_table("sources", Source, settings)
    source_obj = Source.model_validate(filtered_source)
    res_data = table.write([source_obj])
    return {"status": "inserted", "data": res_data}


@app.post("/api/job")
def manage_job(body: dict, email: str = Depends(get_current_user_email)):
    action = body.get("action")
    table_name = body.get("table", "curation_jobs")
    if table_name not in {"curation_jobs", "evaluation_jobs"}:
        raise HTTPException(status_code=400, detail="unsupported job table")
    
    from edu_curator.ids import new_id
    from datetime import datetime
    
    model_cls = CurationJob if table_name == "curation_jobs" else EvaluationJob
    tbl = get_table(table_name, model_cls, settings)
    
    if action == "insert":
        topic_id = body.get("topic_id")
        if not topic_id:
            raise HTTPException(status_code=400, detail="topic_id is required")
        new_job = model_cls(
            id=new_id(),
            topic_id=topic_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        res_data = tbl.write([new_job])
        return {"status": "queued", "data": res_data}
        
    if action == "reset":
        job_id = body.get("job_id")
        if not job_id:
            raise HTTPException(status_code=400, detail="job_id is required")
        jobs = tbl.read(filters={"id": job_id})
        if not jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs[0]
        job.status = "failed"
        job.error_message = "Manually reset by user"
        job.updated_at = datetime.now(timezone.utc)
        res_data = tbl.write([job])
        return {"status": "reset", "data": res_data}
        
    raise HTTPException(status_code=400, detail="unknown job action")


@app.post("/api/review")
def submit_review(body: dict, email: str = Depends(get_current_user_email)):
    content_id = body.get("content_id")
    topic_id = body.get("topic_id")
    review_status = body.get("review_status")
    reviewer_id = email or "human_editor"
    notes = body.get("review_notes")
    content_json = body.get("content_json")
    version = body.get("version")
    
    if not content_id or not topic_id or not review_status:
        raise HTTPException(status_code=400, detail="content_id, topic_id, and review_status are required")
        
    from datetime import datetime
    from edu_curator.ids import new_id
    
    now = datetime.now(timezone.utc)
    
    # Get repositories
    content_tbl = get_table("topic_content", TopicContent, settings)
    topics_tbl = get_table("syllabus_topics", SyllabusTopic, settings)
    activity_tbl = get_table("reviewer_activity", ReviewerActivity, settings)
    jobs_tbl = get_table("curation_jobs", CurationJob, settings)
    
    # Fetch specific content row
    content_rows = content_tbl.read(filters={"id": content_id})
    content_obj = next(iter(content_rows), None)
    if not content_obj:
        raise HTTPException(status_code=404, detail="Content not found")
        
    if version is None:
        version = content_obj.version
        
    # 1. Supabase Atomic Transaction Flow
    if isinstance(content_tbl, SupabaseTable) and content_tbl.supabase:
        try:
            raw_content_json = content_obj.content_json or {}
            raw_content = get_raw_content(topic_id, raw_content_json)
            
            rpc_payload = {
                "p_topic_id": topic_id,
                "p_content_id": content_id,
                "p_review_status": review_status,
                "p_reviewer_id": reviewer_id,
                "p_review_notes": notes or "",
                "p_edited_content": content_json,
                "p_raw_content": raw_content,
                "p_version": version
            }
            
            rpc_res = content_tbl.supabase.rpc("submit_review", rpc_payload).execute()
            
            updated_rows = content_tbl.read(filters={"id": content_id})
            res_data = [r.model_dump(mode="json") for r in updated_rows]
            
            queued_job = None
            if review_status == "needs_regeneration":
                res_job = jobs_tbl.read(filters={"topic_id": topic_id, "status": "pending"})
                queued_job = [j.model_dump(mode="json") for j in res_job] if res_job else None
                
            return {"status": "reviewed", "data": res_data, "queued_job": queued_job}
        except Exception as rpc_err:
            err_str = str(rpc_err)
            logger.error(f"RPC execution failed: {rpc_err}")
            if "Conflict" in err_str or "P0001" in err_str:
                raise HTTPException(status_code=409, detail="Conflict: This content has been modified by another reviewer. Please refresh the page and try again.")
            raise rpc_err
            
    # 2. Local JSON Fallback Concurrency Flow (with Thread Locks & OCC)
    with json_write_lock:
        content_rows = content_tbl.read(filters={"id": content_id})
        content_obj = next(iter(content_rows), None)
        if not content_obj:
            raise HTTPException(status_code=404, detail="Content not found")
            
        if content_obj.version != version:
            raise HTTPException(status_code=409, detail="Conflict: This content has been modified by another reviewer. Please refresh the page and try again.")
            
        update_fields = {
            "review_status": review_status,
            "reviewer_id": reviewer_id,
            "reviewed_at": now,
            "review_notes": notes,
            "version": content_obj.version + 1
        }
        
        if content_json is not None:
            db_content_json = content_obj.content_json or {}
            raw_content = get_raw_content(topic_id, db_content_json)
            save_knowledge_overrides(topic_id, reviewer_id, content_json, raw_content, notes or "")
            
            if review_status == "approved":
                overrides_tbl = get_table("knowledge_overrides", KnowledgeOverride, settings)
                active_overrides = overrides_tbl.read(filters={"topic_id": topic_id, "is_active": True})
                
                merged_content = raw_content.copy()
                for o in active_overrides:
                    merged_content[o.field_name] = o.corrected_value
                    
                update_fields["content_json"] = merged_content
                update_fields["published_at"] = now
                
        updated_content = content_obj.model_copy(update=update_fields)
        res_data = content_tbl.write([updated_content])
        
        topic_status = "completed" if review_status == "approved" else "pending"
        topic_obj = next(iter(topics_tbl.read(filters={"id": topic_id})), None)
        if topic_obj:
            updated_topic = topic_obj.model_copy(update={
                "status": topic_status,
                "updated_at": now
            })
            topics_tbl.write([updated_topic])
            
        audit_payload = ReviewerActivity(
            id=new_id(),
            topic_id=topic_id,
            content_id=content_id,
            reviewer_id=reviewer_id,
            action=review_status,
            review_notes=notes,
            created_at=now
        )
        try:
            activity_tbl.write([audit_payload])
        except Exception as audit_exc:
            logger.warning(f"Audit insert skipped: {audit_exc}")
            
        queued_job = None
        if review_status == "needs_regeneration":
            new_job = CurationJob(
                id=new_id(),
                topic_id=topic_id,
                status="pending",
                created_at=now,
                updated_at=now
            )
            res_job = jobs_tbl.write([new_job])
            queued_job = res_job
            
        return {"status": "reviewed", "data": res_data, "queued_job": queued_job}


@app.post("/api/override")
def manage_override(body: dict, email: str = Depends(get_current_user_email)):
    action = body.get("action")
    topic_id = body.get("topic_id")
    if not topic_id:
        raise HTTPException(status_code=400, detail="topic_id is required")
    
    table = get_table("knowledge_overrides", KnowledgeOverride, settings)
    
    if action == "fetch":
        res = table.read(filters={"topic_id": topic_id, "is_active": True})
        return {"status": "fetched", "data": res}
        
    raise HTTPException(status_code=400, detail="unknown override action")


@app.post("/api/ingest")
def api_ingest(body: dict, email: str = Depends(get_current_user_email)):
    source_id = body.get("source_id")
    if not source_id:
        raise HTTPException(status_code=400, detail="source_id is required")
    
    # Update crawl_status to processing immediately
    try:
        from edu_curator.storage import get_table
        from edu_curator.schemas import Source
        sources_tbl = get_table("sources", Source, settings)
        sources = sources_tbl.read(filters={"id": source_id})
        if sources:
            updated_source = sources[0].model_copy(update={
                "crawl_status": "processing",
                "updated_at": datetime.now(timezone.utc)
            })
            sources_tbl.write([updated_source])
    except Exception as exc:
        logger.warning(f"Failed to set crawl status to processing for source {source_id}: {exc}")

    t = threading.Thread(target=run_ingest, args=(source_id,), daemon=True)
    t.start()
    logger.info(f"Spawned out-of-process ingestion thread for source: {source_id}")
    return {"status": "processing"}


@app.post("/api/evaluate")
def api_evaluate(body: dict, email: str = Depends(get_current_user_email)):
    topic_id = body.get("topic_id")
    if not topic_id:
        raise HTTPException(status_code=400, detail="topic_id is required")
    
    from edu_curator.cli import _topic_uuid
    topic_sn = None
    for sn in range(1, 9999):
        if _topic_uuid(sn) == topic_id:
            topic_sn = sn
            break
    if topic_sn is None:
        raise HTTPException(status_code=400, detail=f"Cannot resolve SN for topic {topic_id}")
        
    from edu_curator.ids import new_id
    from datetime import datetime
    
    eval_jobs_tbl = get_table("evaluation_jobs", EvaluationJob, settings)
    job_id = new_id()
    new_job = EvaluationJob(
        id=job_id,
        topic_id=topic_id,
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    eval_jobs_tbl.write([new_job])
    
    t = threading.Thread(target=run_evaluation_task, args=(topic_sn, job_id), daemon=True)
    t.start()
    return {"status": "processing", "job_id": job_id}


@app.post("/api/upload")
async def api_upload(request: Request, filename: str, email: str = Depends(get_current_user_email)):
    content_length = int(request.headers.get("Content-Length", 0))
    if content_length > 20 * 1024 * 1024:  # 20 MB cap
        raise HTTPException(status_code=413, detail="File size exceeds 20MB limit")
        
    import os
    safe_filename = os.path.basename(filename)
    if not safe_filename or safe_filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    allowed_extensions = {".txt", ".md", ".pdf", ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".csv", ".pptx"}
    _, ext = os.path.splitext(safe_filename.lower())
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File extension {ext} not allowed")
        
    file_bytes = await request.body()
    
    if not validate_file_signature(file_bytes, ext):
        raise HTTPException(status_code=400, detail="File signature validation failed")
        
    uploads_dir = (ROOT / "data" / "uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    save_path = (uploads_dir / safe_filename).resolve()
    
    # Path traversal validation
    if uploads_dir not in save_path.parents and uploads_dir != save_path:
        raise HTTPException(status_code=400, detail="Path traversal attempt detected")
        
    uploaded_to_supabase = False
    local_path = ""
    
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            from supabase import create_client
            # Service role to upload files bypasses RLS
            admin_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            
            # Remove existing file if present to make it idempotent
            try:
                admin_client.storage.from_("uploads").remove([safe_filename])
            except Exception:
                pass
                
            from supabase.storage.errors import StorageException
            admin_client.storage.from_("uploads").upload(
                path=safe_filename,
                file=file_bytes,
                file_options={"x-upsert": "true", "content-type": "application/octet-stream"}
            )
            local_path = f"supabase://uploads/{safe_filename}"
            uploaded_to_supabase = True
        except Exception as upload_err:
            logger.warning(f"Supabase upload failed, falling back to local: {upload_err}")
            
    if not uploaded_to_supabase:
        save_path.write_bytes(file_bytes)
        local_path = f"data/uploads/{safe_filename}"
        
    return {"status": "uploaded", "local_path": local_path}


# ── Server Startup  Synchronization ─────────────────────────────────────────
# NOTE: Startup logic has been moved to the lifespan() context manager above
# (replacing the deprecated @app.on_event("startup") pattern).


if __name__ == "__main__":
    import uvicorn
    from edu_curator.logging import setup_logging
    setup_logging()

    uvicorn.run(app, host=DASHBOARD_HOST, port=PORT, log_level="info")
