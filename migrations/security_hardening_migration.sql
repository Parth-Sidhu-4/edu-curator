-- =============================================================================
-- SECURITY MIGRATION: Database Hardening (F-02 & F-16)
-- Run this script in your Supabase SQL Editor.
-- =============================================================================

-- ── 1. Create allowed_emails table ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS allowed_emails (
    email TEXT PRIMARY KEY
);

-- Enable RLS on allowed_emails
ALTER TABLE allowed_emails ENABLE ROW LEVEL SECURITY;

-- Allow service_role full control, and authenticated users to read it
DROP POLICY IF EXISTS "Allow service role all allowed_emails" ON allowed_emails;
CREATE POLICY "Allow service role all allowed_emails" ON allowed_emails FOR ALL TO service_role USING (true);
DROP POLICY IF EXISTS "Allow authenticated read allowed_emails" ON allowed_emails;
CREATE POLICY "Allow authenticated read allowed_emails" ON allowed_emails FOR SELECT TO authenticated USING (true);

-- Ensure table permissions are granted to database roles (neutralizes code 42501 permission denied)
GRANT ALL ON TABLE allowed_emails TO service_role, postgres;
GRANT SELECT ON TABLE allowed_emails TO authenticated;


-- ── 2. Create is_allowed_user security function ──────────────────────────────
CREATE OR REPLACE FUNCTION is_allowed_user()
RETURNS BOOLEAN SECURITY DEFINER AS $$
BEGIN
    -- Return true if role is authenticated AND either the allowed_emails list is
    -- empty (fallback/empty database default) OR their email is listed.
    RETURN (
        auth.role() = 'authenticated' AND (
            NOT EXISTS (SELECT 1 FROM allowed_emails) OR
            EXISTS (
                SELECT 1 FROM allowed_emails
                WHERE allowed_emails.email = LOWER(auth.jwt() ->> 'email')
            )
        )
    );
END;
$$ LANGUAGE plpgsql;


-- ── 3. Revoke public/anon read access on all database tables ─────────────────
REVOKE SELECT ON TABLE syllabus_topics FROM anon;
REVOKE SELECT ON TABLE sources FROM anon;
REVOKE SELECT ON TABLE normalized_documents FROM anon;
REVOKE SELECT ON TABLE content_chunks FROM anon;
REVOKE SELECT ON TABLE source_to_topic_mapping FROM anon;
REVOKE SELECT ON TABLE fact_extractions FROM anon;
REVOKE SELECT ON TABLE topic_knowledge FROM anon;
REVOKE SELECT ON TABLE topic_content FROM anon;
REVOKE SELECT ON TABLE knowledge_overrides FROM anon;
REVOKE SELECT ON TABLE reviewer_activity FROM anon;
REVOKE SELECT ON TABLE evaluation_results FROM anon;
REVOKE SELECT ON TABLE token_usage FROM anon;
REVOKE SELECT ON TABLE llm_traces FROM anon;
REVOKE SELECT ON TABLE curation_jobs FROM anon;
REVOKE SELECT ON TABLE evaluation_jobs FROM anon;


-- ── 4. Recreate RLS policies with email allowlist checking ───────────────────

-- syllabus_topics
DROP POLICY IF EXISTS "Allow public read syllabus_topics" ON syllabus_topics;
DROP POLICY IF EXISTS "Allow authenticated read syllabus_topics" ON syllabus_topics;
CREATE POLICY "Allow authenticated read syllabus_topics" ON syllabus_topics FOR SELECT TO authenticated USING (is_allowed_user());

-- sources
DROP POLICY IF EXISTS "Allow public read sources" ON sources;
DROP POLICY IF EXISTS "Allow authenticated read sources" ON sources;
CREATE POLICY "Allow authenticated read sources" ON sources FOR SELECT TO authenticated USING (is_allowed_user());

-- normalized_documents
DROP POLICY IF EXISTS "Allow public read normalized_documents" ON normalized_documents;
DROP POLICY IF EXISTS "Allow authenticated read normalized_documents" ON normalized_documents;
CREATE POLICY "Allow authenticated read normalized_documents" ON normalized_documents FOR SELECT TO authenticated USING (is_allowed_user());

-- content_chunks
DROP POLICY IF EXISTS "Allow public read content_chunks" ON content_chunks;
DROP POLICY IF EXISTS "Allow authenticated read content_chunks" ON content_chunks;
CREATE POLICY "Allow authenticated read content_chunks" ON content_chunks FOR SELECT TO authenticated USING (is_allowed_user());

-- source_to_topic_mapping
DROP POLICY IF EXISTS "Allow public read source_to_topic_mapping" ON source_to_topic_mapping;
DROP POLICY IF EXISTS "Allow authenticated read source_to_topic_mapping" ON source_to_topic_mapping;
CREATE POLICY "Allow authenticated read source_to_topic_mapping" ON source_to_topic_mapping FOR SELECT TO authenticated USING (is_allowed_user());

-- fact_extractions
DROP POLICY IF EXISTS "Allow public read fact_extractions" ON fact_extractions;
DROP POLICY IF EXISTS "Allow authenticated read fact_extractions" ON fact_extractions;
CREATE POLICY "Allow authenticated read fact_extractions" ON fact_extractions FOR SELECT TO authenticated USING (is_allowed_user());

-- topic_knowledge
DROP POLICY IF EXISTS "Allow public read topic_knowledge" ON topic_knowledge;
DROP POLICY IF EXISTS "Allow authenticated read topic_knowledge" ON topic_knowledge;
CREATE POLICY "Allow authenticated read topic_knowledge" ON topic_knowledge FOR SELECT TO authenticated USING (is_allowed_user());

-- topic_content
DROP POLICY IF EXISTS "Allow public read topic_content" ON topic_content;
DROP POLICY IF EXISTS "Allow authenticated read topic_content" ON topic_content;
CREATE POLICY "Allow authenticated read topic_content" ON topic_content FOR SELECT TO authenticated USING (is_allowed_user());

-- knowledge_overrides
DROP POLICY IF EXISTS "Allow public read knowledge_overrides" ON knowledge_overrides;
DROP POLICY IF EXISTS "Allow authenticated read knowledge_overrides" ON knowledge_overrides;
CREATE POLICY "Allow authenticated read knowledge_overrides" ON knowledge_overrides FOR SELECT TO authenticated USING (is_allowed_user());

-- reviewer_activity
DROP POLICY IF EXISTS "Allow public read reviewer_activity" ON reviewer_activity;
DROP POLICY IF EXISTS "Allow authenticated read reviewer_activity" ON reviewer_activity;
CREATE POLICY "Allow authenticated read reviewer_activity" ON reviewer_activity FOR SELECT TO authenticated USING (is_allowed_user());

-- evaluation_results
DROP POLICY IF EXISTS "Allow public read evaluation_results" ON evaluation_results;
DROP POLICY IF EXISTS "Allow authenticated read evaluation_results" ON evaluation_results;
CREATE POLICY "Allow authenticated read evaluation_results" ON evaluation_results FOR SELECT TO authenticated USING (is_allowed_user());

-- token_usage
DROP POLICY IF EXISTS "Allow public read token_usage" ON token_usage;
DROP POLICY IF EXISTS "Allow authenticated read token_usage" ON token_usage;
CREATE POLICY "Allow authenticated read token_usage" ON token_usage FOR SELECT TO authenticated USING (is_allowed_user());

-- llm_traces
DROP POLICY IF EXISTS "Allow public read llm_traces" ON llm_traces;
DROP POLICY IF EXISTS "Allow authenticated read llm_traces" ON llm_traces;
CREATE POLICY "Allow authenticated read llm_traces" ON llm_traces FOR SELECT TO authenticated USING (is_allowed_user());

-- curation_jobs
DROP POLICY IF EXISTS "Allow public read curation_jobs" ON curation_jobs;
DROP POLICY IF EXISTS "Allow authenticated read curation_jobs" ON curation_jobs;
CREATE POLICY "Allow authenticated read curation_jobs" ON curation_jobs FOR SELECT TO authenticated USING (is_allowed_user());

-- evaluation_jobs
DROP POLICY IF EXISTS "Allow public read evaluation_jobs" ON evaluation_jobs;
DROP POLICY IF EXISTS "Allow authenticated read evaluation_jobs" ON evaluation_jobs;
CREATE POLICY "Allow authenticated read evaluation_jobs" ON evaluation_jobs FOR SELECT TO authenticated USING (is_allowed_user());


-- ── 5. Create atomic job claiming function (F-16 TOCTOU lock) ─────────────────
CREATE OR REPLACE FUNCTION claim_next_job(worker_name TEXT)
RETURNS SETOF curation_jobs AS $$
DECLARE
    claimed_job curation_jobs;
BEGIN
    UPDATE curation_jobs
    SET status = 'running',
        updated_at = NOW(),
        logs = logs || E'\n[worker] Claimed by ' || worker_name
    WHERE id = (
        SELECT id FROM curation_jobs
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING * INTO claimed_job;
    
    IF FOUND THEN
        RETURN NEXT claimed_job;
    END IF;
END;
$$ LANGUAGE plpgsql;
