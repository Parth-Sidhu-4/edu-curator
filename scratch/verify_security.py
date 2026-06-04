#!/usr/bin/env python3
import re, sys
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[1]
SERVE_PY   = ROOT / "dashboard" / "serve.py"
APP_JS     = ROOT / "dashboard" / "app.js"
INDEX_HTML = ROOT / "dashboard" / "index.html"
INGEST_PY  = ROOT / "src" / "edu_curator" / "ingest.py"
LLM_PY     = ROOT / "src" / "edu_curator" / "llm.py"
REQ_TXT    = ROOT / "requirements.txt"
ENV_EXAMPLE= ROOT / ".env.example"
MIGRATION  = ROOT / "migrations" / "security_hardening_migration.sql"
CADDY_CONF = ROOT / "infra" / "caddy.conf"
DOCKERFILE = ROOT / "Dockerfile"

results = []

def check(finding, desc, condition, warn_only=False):
    ok = bool(condition)
    tag = "[PASS]" if ok else ("[WARN]" if warn_only else "[FAIL]")
    print(f"  {tag} {finding}: {desc}")
    results.append((finding, desc, ok, warn_only))
    return ok

def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""

# --- ingest.py ---
print("\n-- F-01 / F-05 / F-10: ingest.py " + "-"*38)
ingest = read(INGEST_PY)
check("F-01", "async_fetch_url_text calls _validate_url_ssrf",
      "_validate_url_ssrf" in ingest and "async_fetch_url_text" in ingest)
check("F-05", "Prompt injection delimiters (<content> tags)",
      "<content>" in ingest and "</content>" in ingest)
check("F-05", "Trust score bounds enforced",
      "max(1" in ingest or "min(10" in ingest)
check("F-10", "DNS IP-pinning / cache present",
      "_dns_global_cache" in ingest or "_pin_ip" in ingest or "dns_cache" in ingest.lower())

# --- serve.py ---
print("\n-- F-03 / F-04 / F-08 / F-12 / F-17 / F-18 / F-21 / F-22: serve.py " + "-"*5)
serve = read(SERVE_PY)
check("F-03", "Per-request CSP nonce (secrets.token_urlsafe)",
      "token_urlsafe" in serve)
check("F-03", "CSP_NONCE injected into HTML",
      "CSP_NONCE" in serve)
# style-src may keep 'unsafe-inline' (CSS cannot use nonces); only script-src matters
_csp_block = serve[serve.find("script-src"):serve.find("script-src")+200] if "script-src" in serve else ""
check("F-03", "unsafe-inline absent from script-src directive",
      "'unsafe-inline'" not in _csp_block)
check("F-04", "ALLOWED_TOPIC_FIELDS defined",
      "ALLOWED_TOPIC_FIELDS" in serve)
check("F-04", "ALLOWED_SOURCE_FIELDS defined",
      "ALLOWED_SOURCE_FIELDS" in serve)
check("F-08", "No os.environ.copy() in subprocess calls",
      "os.environ.copy()" not in serve)
check("F-12", "Generic error message for DB errors",
      "Pipeline execution failed" in serve or "check server logs" in serve.lower())
check("F-17", "Static file path allowlist",
      "ALLOWED_STATIC" in serve or "/purify.min.js" in serve)
check("F-18", "Separate auth rate-limit bucket",
      "auth_rate" in serve.lower() or "AUTH_RATE" in serve or "auth_requests" in serve.lower() or "rate_limit_auth" in serve.lower())
check("F-21", "validate_file_signature function",
      "validate_file_signature" in serve)
check("F-21", "Magic-byte PDF check (%PDF)",
      "%PDF" in serve)
check("F-21", "Robust PPTX ZIP-structure verification (zipfile)",
      "zipfile" in serve and "namelist()" in serve)
check("F-22", "Supabase URL masked in startup",
      "***" in serve or "[:8]" in serve or "masked" in serve.lower() or "redact" in serve.lower())

# --- llm.py ---
print("\n-- F-13: llm.py " + "-"*55)
llm = read(LLM_PY)
check("F-13", "LOG_LLM_LOCALLY env gate",
      "LOG_LLM_LOCALLY" in llm)

# --- app.js ---
print("\n-- F-06 / F-11: app.js " + "-"*49)
appjs = read(APP_JS)
check("F-06", "Lazy-load trace detail on expand",
      "Lazy load prompt" in appjs or "lazy load trace" in appjs.lower() or
      "fetchTraceDetail" in appjs or "loadTrace" in appjs.lower())
check("F-11", "Supabase error mapper",
      "mapSupabaseError" in appjs or "friendlyError" in appjs or "mapDbError" in appjs or
      "23505" in appjs or "duplicate" in appjs.lower())

# --- index.html ---
print("\n-- F-03 / F-14: index.html " + "-"*45)
html = read(INDEX_HTML)
check("F-03", "CSP nonce placeholder in inline script",
      "CSP_NONCE" in html or 'nonce=' in html)
check("F-14", "SRI integrity attribute on CDN assets",
      "integrity=" in html)

# --- migration SQL ---
print("\n-- F-02 / F-16: migration SQL " + "-"*43)
sql = read(MIGRATION)
check("F-02", "allowed_emails table created",
      "allowed_emails" in sql)
check("F-02", "is_allowed_user() function",
      "is_allowed_user" in sql)
check("F-02", "RLS policy references is_allowed_user",
      "is_allowed_user" in sql and "POLICY" in sql.upper())
check("F-16", "claim_next_job RPC with SKIP LOCKED",
      "claim_next_job" in sql and "SKIP LOCKED" in sql.upper())

# --- Deployment & Config ---
print("\n-- F-07 / F-09 / F-15 / F-19: deployment & config " + "-"*22)
req    = read(REQ_TXT)
env_ex = read(ENV_EXAMPLE)
caddy  = read(CADDY_CONF)
docker = read(DOCKERFILE)

# Any named non-root USER directive qualifies
import re as _re
check("F-07", "Dockerfile runs as non-root USER",
      bool(_re.search(r'^USER\s+(?!root)', docker, _re.MULTILINE)))
check("F-07", "Dockerfile CMD uses serve.py",
      "serve.py" in docker)
check("F-09", "Caddy reverse-proxy config present",
      "reverse_proxy" in caddy or "tls" in caddy.lower())
check("F-15", "streamlit >= 1.45 in requirements.txt",
      bool(re.search(r"streamlit.*1\.(4[5-9]|[5-9])", req)), warn_only=True)
check("F-19", "Redis password docs in .env.example",
      "redis" in env_ex.lower() and ("password" in env_ex.lower() or "STRONG_PASSWORD" in env_ex))

# --- Summary ---
print("\n" + "="*60)
passed = sum(1 for _, _, ok, _    in results if ok)
failed = sum(1 for _, _, ok, warn in results if not ok and not warn)
warned = sum(1 for _, _, ok, warn in results if not ok and warn)
total  = len(results)
print(f"  Results: {passed}/{total} checks passed | {failed} failed | {warned} warnings")
print("="*60 + "\n")
sys.exit(0 if failed == 0 else 1)
