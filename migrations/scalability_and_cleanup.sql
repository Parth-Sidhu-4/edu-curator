-- =============================================================================
-- Migration: Scalability & Performance Hardening
-- Generated:  2026-06-04
-- Purpose:    Add composite indexes on hot query paths, a curation_jobs status
--             index (eliminates full-table scan every 2s), and a log-cleanup
--             stored procedure with a 30-day TTL for unbounded tables.
--
-- Run in: Supabase Dashboard → SQL Editor (or psql as postgres role)
-- Safe to re-run: all statements use IF NOT EXISTS / OR REPLACE.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- SECTION 1: Composite Indexes on Critical Query Paths
-- ---------------------------------------------------------------------------

-- curation_jobs: polled every 2s by the background worker for status='pending'.
-- Without this index every poll was a full table scan.
CREATE INDEX IF NOT EXISTS idx_curation_jobs_status
    ON curation_jobs (status);

-- curation_jobs: frequently queried together by (topic_id, status) on the dashboard.
CREATE INDEX IF NOT EXISTS idx_curation_jobs_topic_status
    ON curation_jobs (topic_id, status);

-- evaluation_jobs: same access pattern as curation_jobs.
CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_status
    ON evaluation_jobs (status);

CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_topic_status
    ON evaluation_jobs (topic_id, status);

-- knowledge_overrides: every review action queries (topic_id, is_active) together.
-- Without this the per-topic override lookup scans the full overrides table.
CREATE INDEX IF NOT EXISTS idx_overrides_topic_active
    ON knowledge_overrides (topic_id, is_active);

-- fact_extractions: (topic_id, field_name) is the primary access pattern in the
-- conflict resolution stage — resolving each field requires filtering by both.
CREATE INDEX IF NOT EXISTS idx_facts_topic_field
    ON fact_extractions (topic_id, field_name);

-- source_to_topic_mapping: (topic_id, is_active) queried together on every map step.
CREATE INDEX IF NOT EXISTS idx_mapping_topic_active
    ON source_to_topic_mapping (topic_id, is_active);

-- llm_traces: queried by stage + time range on the Observability dashboard.
CREATE INDEX IF NOT EXISTS idx_llm_traces_stage_ts
    ON llm_traces (stage, ts DESC);

-- token_usage: queried by model + time range for cost analytics.
CREATE INDEX IF NOT EXISTS idx_token_usage_model_ts
    ON token_usage (model, ts DESC);

-- sources: is_active filter used on every ingest pre-check.
CREATE INDEX IF NOT EXISTS idx_sources_active
    ON sources (is_active);

-- topic_content: review_status queried on dashboard overview page.
CREATE INDEX IF NOT EXISTS idx_content_review_status
    ON topic_content (review_status);

-- ---------------------------------------------------------------------------
-- SECTION 2: Log & Trace Cleanup Stored Procedures (30-day TTL)
-- ---------------------------------------------------------------------------
-- These functions implement a lightweight archival/cleanup policy for tables
-- that grow unbounded. Call them manually or via a pg_cron schedule:
--
--   SELECT cron.schedule('cleanup-llm-traces', '0 3 * * *', $$SELECT cleanup_old_llm_traces(30)$$);
--   SELECT cron.schedule('cleanup-token-usage', '0 3 * * *', $$SELECT cleanup_old_token_usage(90)$$);
--
-- The retention_days parameter is configurable per invocation.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION cleanup_old_llm_traces(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM llm_traces
    WHERE ts < NOW() - (retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'cleanup_old_llm_traces: deleted % rows older than % days', deleted_count, retention_days;
    RETURN deleted_count;
END;
$$;

CREATE OR REPLACE FUNCTION cleanup_old_token_usage(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM token_usage
    WHERE ts < NOW() - (retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'cleanup_old_token_usage: deleted % rows older than % days', deleted_count, retention_days;
    RETURN deleted_count;
END;
$$;

-- Cleanup for completed/failed job logs older than N days.
-- Keeps recent jobs for debugging; removes old ones to control storage.
CREATE OR REPLACE FUNCTION cleanup_old_job_logs(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Truncate logs column for old completed/failed jobs rather than deleting the job record.
    -- This preserves auditability (the job row remains) but reclaims storage.
    UPDATE curation_jobs
    SET logs = '[log truncated by cleanup policy]'
    WHERE updated_at < NOW() - (retention_days || ' days')::INTERVAL
      AND status IN ('completed', 'failed')
      AND length(logs) > 0;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    UPDATE evaluation_jobs
    SET logs = '[log truncated by cleanup policy]'
    WHERE updated_at < NOW() - (retention_days || ' days')::INTERVAL
      AND status IN ('completed', 'failed')
      AND length(logs) > 0;

    RAISE NOTICE 'cleanup_old_job_logs: truncated logs for % job rows older than % days', deleted_count, retention_days;
    RETURN deleted_count;
END;
$$;

-- ---------------------------------------------------------------------------
-- SECTION 3: Grant execute rights on cleanup functions to service_role only.
-- Anon/authenticated roles must NEVER be able to call these.
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION cleanup_old_llm_traces(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_llm_traces(INTEGER) TO service_role, postgres;

REVOKE ALL ON FUNCTION cleanup_old_token_usage(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_token_usage(INTEGER) TO service_role, postgres;

REVOKE ALL ON FUNCTION cleanup_old_job_logs(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_job_logs(INTEGER) TO service_role, postgres;

-- ---------------------------------------------------------------------------
-- SECTION 4: How to schedule automatic cleanup (requires pg_cron extension)
-- ---------------------------------------------------------------------------
-- Enable pg_cron in Supabase Dashboard → Database → Extensions → pg_cron
-- Then run:
--
-- Daily at 03:00 UTC — trim LLM traces older than 30 days
-- SELECT cron.schedule('cleanup-llm-traces', '0 3 * * *',
--     $$SELECT cleanup_old_llm_traces(30)$$);
--
-- Daily at 03:05 UTC — trim token usage older than 90 days
-- SELECT cron.schedule('cleanup-token-usage', '5 3 * * *',
--     $$SELECT cleanup_old_token_usage(90)$$);
--
-- Daily at 03:10 UTC — truncate old job logs
-- SELECT cron.schedule('cleanup-job-logs', '10 3 * * *',
--     $$SELECT cleanup_old_job_logs(30)$$);
-- ---------------------------------------------------------------------------
