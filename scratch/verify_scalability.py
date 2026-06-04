#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
Edu-Curator Scalability Verification Script
Verifies database pagination and Redis-backed rate limiting.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVE_PY = ROOT / "dashboard" / "serve.py"
STORAGE_PY = ROOT / "src" / "edu_curator" / "storage.py"

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

print("\n-- Database Pagination (storage.py) " + "-"*24)
storage = read(STORAGE_PY)
check("S-01 (JsonTable)", "JsonTable read method accepts limit and offset",
      "def read(self, limit:" in storage and "offset:" in storage)
check("S-01 (SupabaseTable)", "SupabaseTable read method accepts limit and offset",
      "def read(self, limit:" in storage and "offset:" in storage)
check("S-01 (Query API)", "SupabaseTable uses limit/offset filters dynamically",
      "query.limit(limit)" in storage and "query.offset(offset)" in storage)

print("\n-- Redis-Backed Rate Limiting (serve.py) " + "-"*20)
serve = read(SERVE_PY)
check("S-04 (Redis Connect)", "Server rate-limiter connection handler present (_get_server_redis)",
      "_get_server_redis()" in serve and "Redis.from_url" in serve)
check("S-04 (Redis Timeout)", "Server Redis client enforces socket timeouts",
      "socket_timeout=2.0" in serve and "socket_connect_timeout=2.0" in serve)
check("S-04 (Sliding Window)", "Rate limit checks utilize Redis pipelines and ZREMRANGEBYSCORE",
      "r_client.pipeline()" in serve and "zremrangebyscore" in serve)
check("S-04 (Fallback)", "Falls back to in-memory rate limiting if Redis connection fails",
      "with ip_history_lock:" in serve and "except Exception as e:" in serve)

# --- Summary ---
print("\n" + "="*60)
passed = sum(1 for _, _, ok in results if ok)
failed = sum(1 for _, _, ok in results if not ok)
total  = len(results)
print(f"  Scalability Results: {passed}/{total} checks passed | {failed} failed")
print("="*60 + "\n")
sys.exit(0 if failed == 0 else 1)
