# Edu-Curator Operations Runbook

> **Audience**: Any engineer who needs to operate, restart, or debug the system.
> **Scope**: Production deployment on a Linux server + local Windows development.

---

## 1. Quick-Reference Commands

| Task | Command |
|---|---|
| Start server | `python dashboard/serve.py` |
| Start server (background) | `nohup python dashboard/serve.py &> logs/server.log &` |
| Check server health | `curl http://localhost:8502/health` |
| View live logs (Linux service) | `sudo journalctl -u edu-curator -f` |
| Restart (Linux service) | `sudo systemctl restart edu-curator` |
| Stop (Linux service) | `sudo systemctl stop edu-curator` |
| Run tests | `python -m pytest tests/ -v` |
| Run full pipeline for SN 5 | `python -m edu_curator.cli run-topic --sn 5` |
| Ingest all pending sources | `python -m edu_curator.cli ingest` |
| Check token usage | `python -m edu_curator.cli token-stats` |

---

## 2. How to Check System Health

### Option A — Health Endpoint (fastest)
```
curl http://localhost:8502/health
```
Expected OK response:
```json
{"status": "ok", "db": "ok", "worker": "alive", "uptime_seconds": 3721}
```
If `"db": "unreachable"` — Supabase is down. Check Supabase status page.
If `"worker": "stopped"` — the background curation worker thread has died. Restart the server.
If HTTP 503 — the server is up but the database is unreachable.
If connection refused — the server process has crashed. Restart it.

### Option B — Supabase Dashboard
Log in at https://supabase.com/dashboard → your project → Table Editor.
- `curation_jobs` table: check for stuck `running` jobs older than 20 minutes
- `token_usage` table: check for unusual spikes in LLM usage

---

## 3. How to Diagnose Job Failures

1. Open the Dashboard → Overview or Observability tab
2. Find the failed job and click to see the log output
3. Common failure reasons:

| Error Pattern | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pwd'` | Subprocess missing Windows env vars | Already fixed in `_get_restricted_env` |
| `Pipeline exited with code 1` | LLM API error or rate limit hit | Check Langfuse traces, retry the job |
| `Cannot resolve SN for topic <id>` | Topic UUID not in SN range | Topic SN > 9999 (extremely unlikely) |
| `Ingest subprocess failed with code 1` | Source file unreadable or URL blocked | Check source URL / file format |
| `RateLimitError` | Cerebras/Groq quota hit | Wait and retry; check `token_usage` table |
| `Job was stuck in running state` | Server crashed mid-job | Job auto-reset by periodic sweep; re-queue |

---

## 4. How to Reset a Stuck Job

**Via Dashboard (preferred)**:
1. Go to Overview tab → find the stuck job
2. Click "Force Reset Stuck Job" button
3. Re-queue by clicking "Generate Content" on the topic

**Via Supabase SQL Editor** (if dashboard is down):
```sql
UPDATE curation_jobs
SET status = 'failed', error_message = 'Manually reset', updated_at = now()
WHERE status = 'running' AND updated_at < now() - interval '20 minutes';
```

---

## 5. How to Deploy / Update

### Local (Windows development)
```powershell
# 1. Pull latest code (once git is set up)
git pull origin main

# 2. Install any new dependencies
pip install -r requirements.txt

# 3. Kill old server (find PID from task manager or:)
#    Get-Process python | Stop-Process

# 4. Start new server
python dashboard/serve.py
```

### Linux server (production)
```bash
# 1. Pull latest code
git pull origin main

# 2. Install any new dependencies
.venv/bin/pip install -r requirements.txt

# 3. Restart via systemd (handles PID management automatically)
sudo systemctl restart edu-curator

# 4. Verify health
curl http://localhost:8502/health
```

### Docker
```bash
docker compose build
docker compose up -d

# Check health
docker compose ps       # should show "healthy"
curl http://localhost:8502/health
```

---

## 6. Rollback Procedure

There is currently **no automated rollback**. Manual steps:

```bash
# 1. Identify the last working commit
git log --oneline -10

# 2. Check out that commit
git checkout <commit-hash>

# 3. Reinstall dependencies for that version
pip install -r requirements.txt

# 4. Restart the server
sudo systemctl restart edu-curator
```

> ⚠️ If a database schema migration ran as part of the failed deployment, rolling back the code is not sufficient. You will need to manually reverse the schema changes in Supabase SQL Editor. Document migrations before applying them.

---

## 7. Environment Variables Reference

All secrets live in `.env` (never committed to git — already in `.gitignore`).

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Service-role key (server-only, never browser) |
| `SUPABASE_ANON_KEY` | Yes | Anon key sent to browser |
| `CEREBRAS_API_KEY` | Yes | Primary LLM provider |
| `GROQ_API_KEY` | Yes | Fallback LLM provider |
| `LANGFUSE_PUBLIC_KEY` | Optional | Tracing |
| `LANGFUSE_SECRET_KEY` | Optional | Tracing |
| `REDIS_URL` | Optional | Rate limiter (falls back to in-memory) |
| `ALLOWED_EMAILS` | Yes | Comma-separated list of permitted users |
| `DASHBOARD_HOST` | Optional | Default `127.0.0.1`; use `0.0.0.0` in Docker |
| `DASHBOARD_PORT` | Optional | Default `8502` |
| `START_IN_PROCESS_WORKER` | Optional | Default `true`; set `false` to disable worker |
| `LITELLM_FALLBACK_ENABLED` | Optional | Default `false`; set `true` to enable Groq fallback |

---

## 8. Adding a New Allowed User

Edit `.env`:
```
ALLOWED_EMAILS=user1@example.com, user2@example.com, newuser@example.com
```
Then restart the server. The list is synced to the `allowed_emails` Supabase table on startup.

---

## 9. Monitoring Setup (Recommended)

Register at [UptimeRobot](https://uptimerobot.com) (free):
- Monitor URL: `http://your-server:8502/health`
- Interval: 5 minutes
- Alert: Email on status change

This gives you immediate notification if the server crashes or the database becomes unreachable.

---

## 10. Key Architectural Facts for New Engineers

- **Single process**: `dashboard/serve.py` runs both the FastAPI web server and the background curation worker thread
- **Job queue**: Jobs are stored in Supabase `curation_jobs` table; the worker claims them atomically via `claim_next_job` RPC
- **Pipeline**: Each curation job runs `python -m edu_curator.cli run-topic --sn N` as a **subprocess**, not in-process
- **Topic identity**: Topics are identified by deterministic UUID from serial number: `uuid5(DNS, "devops-topic-sn-N")`; SN 1 is hardcoded to `11111111-1111-1111-1111-111111111111`
- **Storage**: Supabase (PostgreSQL) is the primary store; a local JSON fallback exists for development
- **LLM**: Cerebras is primary; Groq (via LiteLLM) is fallback on 429/5xx with 10 retries + exponential backoff
- **Auth**: JWT from Supabase Auth verified server-side; only listed `ALLOWED_EMAILS` can log in
