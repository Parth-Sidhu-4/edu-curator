"""Token usage logger.

Every LLM call in the pipeline returns prompt_tokens / completion_tokens via
ChatResult.  This module provides a thin helper that:

  1. Appends one JSON-Lines record to  data/logs/token_usage.jsonl
  2. Exposes a summary helper used by the  token-stats  CLI command.

Record format (one JSON object per line):
  {
    "ts":               "2026-06-01T14:30:00Z",  # UTC ISO-8601
    "stage":            "extract",               # pipeline stage
    "topic_sn":         3,                       # serial number (int) or null
    "model":            "llama3.1-8b",
    "prompt_tokens":    412,
    "completion_tokens": 87,
    "total_tokens":     499
  }
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edu_curator.ids import new_id
from edu_curator.llm import ChatResult

# ---------------------------------------------------------------------------
# Append one record
# ---------------------------------------------------------------------------


def log_usage(
    log_dir: Path,
    result: ChatResult,
    stage: str,
    model: str,
    topic_sn: int | None = None,
) -> None:
    """Append a single token-usage record to token_usage.jsonl and Supabase (if configured).

    Parameters
    ----------
    log_dir:   Path to the data/logs directory (created if absent).
    result:    The ChatResult from chat_json() — carries token counts.
    stage:     Pipeline stage label, e.g. "extract", "generate", "consistency".
    model:     Model name used for this call.
    topic_sn:  Topic serial number, or None for utility calls.
    """
    if result.prompt_tokens is None and result.completion_tokens is None:
        return  # provider returned no usage info — nothing to log

    prompt_tok = result.prompt_tokens or 0
    completion_tok = result.completion_tokens or 0

    record: dict[str, Any] = {
        "id": new_id(),
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": stage,
        "topic_sn": topic_sn,
        "model": model,
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion_tok,
        "total_tokens": prompt_tok + completion_tok,
    }

    # 1. Local backup writing
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "token_usage.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    # 2. Write to repository (Supabase or local JSON fallback)
    try:
        from edu_curator.config import load_settings
        from edu_curator.storage import get_table
        from edu_curator.schemas import TokenUsageRecord

        root = log_dir.parent.parent
        settings = load_settings(root)
        
        tbl = get_table("token_usage", TokenUsageRecord, settings)
        tbl.write([TokenUsageRecord.model_validate(record)])
    except Exception as exc:
        print(f"  [token_logger] Failed to write token log to repository: {exc}")



# ---------------------------------------------------------------------------
# Summarise all records
# ---------------------------------------------------------------------------


def summarise_usage(log_dir: Path) -> dict[str, Any]:
    """Read from Supabase if configured, otherwise read token_usage.jsonl. Return summary."""
    records: list[dict[str, Any]] = []
    loaded_from_supabase = False

    try:
        from edu_curator.config import load_settings

        from edu_curator.storage import get_table
        from edu_curator.schemas import TokenUsageRecord
        from edu_curator.storage import SupabaseTable

        root = log_dir.parent.parent
        settings = load_settings(root)
        tbl = get_table("token_usage", TokenUsageRecord, settings)
        if isinstance(tbl, SupabaseTable):
            rows = tbl.read()
            records = [r.model_dump(mode="json") for r in rows]
            loaded_from_supabase = True
    except Exception as exc:
        print(
            f"  [token_logger] Failed to fetch token usage from repository: {exc}. Falling back to local logs."
        )


    if not loaded_from_supabase:
        log_path = log_dir / "token_usage.jsonl"
        if not log_path.exists():
            return {
                "total_calls": 0,
                "total_prompt": 0,
                "total_completion": 0,
                "total_tokens": 0,
                "by_stage": {},
                "by_model": {},
                "by_topic_sn": {},
            }
        with open(log_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    def _empty_bucket() -> dict[str, int]:
        return {"calls": 0, "prompt": 0, "completion": 0, "total": 0}

    by_stage: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, int]] = {}
    by_sn: dict[str, dict[str, int]] = {}

    total_prompt = total_completion = 0

    for r in records:
        pt = r.get("prompt_tokens", 0) or 0
        ct = r.get("completion_tokens", 0) or 0
        tt = pt + ct
        total_prompt += pt
        total_completion += ct

        stage = r.get("stage", "unknown")
        by_stage.setdefault(stage, _empty_bucket())
        by_stage[stage]["calls"] += 1
        by_stage[stage]["prompt"] += pt
        by_stage[stage]["completion"] += ct
        by_stage[stage]["total"] += tt

        model = r.get("model", "unknown")
        by_model.setdefault(model, _empty_bucket())
        by_model[model]["calls"] += 1
        by_model[model]["prompt"] += pt
        by_model[model]["completion"] += ct
        by_model[model]["total"] += tt

        sn_key = str(r.get("topic_sn", "—"))
        by_sn.setdefault(sn_key, _empty_bucket())
        by_sn[sn_key]["calls"] += 1
        by_sn[sn_key]["prompt"] += pt
        by_sn[sn_key]["completion"] += ct
        by_sn[sn_key]["total"] += tt

    return {
        "total_calls": len(records),
        "total_prompt": total_prompt,
        "total_completion": total_completion,
        "total_tokens": total_prompt + total_completion,
        "by_stage": by_stage,
        "by_model": by_model,
        "by_topic_sn": by_sn,
    }
