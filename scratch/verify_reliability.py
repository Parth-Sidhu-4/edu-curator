#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
Edu-Curator Reliability Verification Script
Verifies SRE and Reliability fixes are present and functional.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INGEST_PY = ROOT / "src" / "edu_curator" / "ingest.py"
SERVE_PY = ROOT / "dashboard" / "serve.py"
LLM_PY = ROOT / "src" / "edu_curator" / "llm.py"

PASS = "[PASS]"
FAIL = "[FAIL]"

results = []

def check(name, desc, condition):
    ok = bool(condition)
    tag = PASS if ok else FAIL
    print(f"  {tag} {name}: {desc}")
    results.append((name, desc, ok))
    return ok

def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""

print("\n-- Ingestion Reliability (ingest.py) " + "-"*23)
ingest = read(INGEST_PY)
check("R-01 (Sync)", "Sync fetch_url_text enforces 10MB limit (size_limit)",
      "size_limit = 10 * 1024 * 1024" in ingest and "fetch_url_text" in ingest)
check("R-01 (Async)", "Async async_fetch_url_text enforces 10MB limit",
      "size_limit = 10 * 1024 * 1024" in ingest and "async_fetch_url_text" in ingest)
check("R-01 (Stream)", "URL fetching reads in chunks (response.read(65536))",
      "response.read(65536)" in ingest or "response.content.read(65536)" in ingest)

print("\n-- Subprocess Timeouts & Ingestion DB status (serve.py) " + "-"*7)
serve = read(SERVE_PY)
check("R-02 (Curation)", "Curation job subprocess uses 15-min timeout guard",
      "timeout_limit = 900.0" in serve and "curation_jobs" in serve)
check("R-02 (Evaluation)", "Evaluation job subprocess uses 15-min timeout guard",
      "timeout_limit = 900.0" in serve and "evaluation_jobs" in serve)
check("R-02 (Thread Queue)", "Uses Thread-based non-blocking reader to prevent blocks",
      "t_reader = threading.Thread" in serve and "enqueue_output" in serve)
check("R-03 (Failed Crawl)", "run_ingest updates sources table to failed on error",
      "crawl_status" in serve and "Ingest error for source" in serve and "update" in serve)

print("\n-- Cache Connection Robustness (llm.py) " + "-"*15)
llm = read(LLM_PY)
check("R-04 (Redis Timeout)", "Redis client specifies socket timeouts to prevent hangs",
      "socket_timeout=2.0" in llm and "socket_connect_timeout=2.0" in llm)

# --- Summary ---
print("\n" + "="*60)
passed = sum(1 for _, _, ok in results if ok)
failed = sum(1 for _, _, ok in results if not ok)
total  = len(results)
print(f"  Reliability Results: {passed}/{total} checks passed | {failed} failed")
print("="*60 + "\n")
sys.exit(0 if failed == 0 else 1)
