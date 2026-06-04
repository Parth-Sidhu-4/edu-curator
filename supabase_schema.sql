-- Supabase SQL Schema for Edu-Curator

CREATE TABLE syllabus_topics (
    id UUID PRIMARY KEY,
    chapter TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    keywords JSONB DEFAULT '[]'::jsonb,
    difficulty_level TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sources (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT,
    local_path TEXT,
    trust_score DOUBLE PRECISION NOT NULL,
    auto_trust_score DOUBLE PRECISION,
    license_type TEXT,
    publication_date DATE,
    owner TEXT,
    topic_ids JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    content_hash TEXT,
    last_crawled TIMESTAMPTZ,
    crawl_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE normalized_documents (
    source_id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE content_chunks (
    id UUID PRIMARY KEY,
    source_id UUID NOT NULL,
    chunk_text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding JSONB,
    chunk_number INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE source_to_topic_mapping (
    id UUID PRIMARY KEY,
    source_id UUID NOT NULL,
    chunk_id UUID NOT NULL,
    topic_id UUID NOT NULL,
    vector_score NUMERIC,
    reranker_score NUMERIC,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE fact_extractions (
    id UUID PRIMARY KEY,
    topic_id UUID NOT NULL,
    source_id UUID NOT NULL,
    chunk_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    field_value JSONB NOT NULL,
    schema_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    extraction_model TEXT NOT NULL,
    extraction_confidence NUMERIC,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topic_knowledge (
    id UUID PRIMARY KEY,
    topic_id UUID NOT NULL,
    schema_version TEXT NOT NULL,
    knowledge JSONB NOT NULL,
    sources_used JSONB DEFAULT '[]'::jsonb,
    confidence NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topic_content (
    id UUID PRIMARY KEY,
    topic_id UUID NOT NULL,
    content_json JSONB NOT NULL,
    schema_version TEXT,
    generation_model TEXT,
    sources_used JSONB DEFAULT '[]'::jsonb,
    confidence_score NUMERIC,
    consistency_check_status BOOLEAN,
    consistency_check_flags JSONB,
    review_status TEXT DEFAULT 'pending',
    reviewer_id TEXT,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    published_at TIMESTAMPTZ,
    inputs_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    original_value JSONB,
    corrected_value JSONB NOT NULL,
    correction_note TEXT,
    reviewer_id TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reviewer_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL,
    content_id UUID,
    reviewer_id TEXT,
    action TEXT NOT NULL,
    review_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE evaluation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL,
    faithfulness_score NUMERIC,
    completeness_score NUMERIC,
    faithfulness_reasoning TEXT,
    completeness_reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE extraction_errors (
    id UUID PRIMARY KEY,
    topic_id UUID,
    source_id UUID,
    chunk_id UUID,
    error_type TEXT NOT NULL,
    error_detail TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Token usage observability table
CREATE TABLE token_usage (
    id UUID PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stage TEXT NOT NULL,
    topic_sn INTEGER,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL
);

-- Foreign Key Constraints for integrity
ALTER TABLE content_chunks 
  ADD CONSTRAINT fk_chunks_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE;

ALTER TABLE source_to_topic_mapping 
  ADD CONSTRAINT fk_mapping_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_mapping_chunk FOREIGN KEY (chunk_id) REFERENCES content_chunks(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_mapping_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE;

ALTER TABLE fact_extractions 
  ADD CONSTRAINT fk_facts_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_facts_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_facts_chunk FOREIGN KEY (chunk_id) REFERENCES content_chunks(id) ON DELETE CASCADE;

ALTER TABLE topic_knowledge 
  ADD CONSTRAINT fk_knowledge_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE;

ALTER TABLE topic_content 
  ADD CONSTRAINT fk_content_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE;

ALTER TABLE knowledge_overrides
  ADD CONSTRAINT fk_overrides_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE;

ALTER TABLE reviewer_activity
  ADD CONSTRAINT fk_reviewer_activity_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_reviewer_activity_content FOREIGN KEY (content_id) REFERENCES topic_content(id) ON DELETE SET NULL;

ALTER TABLE evaluation_results
  ADD CONSTRAINT fk_evaluation_results_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE;

ALTER TABLE extraction_errors 
  ADD CONSTRAINT fk_errors_topic FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_errors_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_errors_chunk FOREIGN KEY (chunk_id) REFERENCES content_chunks(id) ON DELETE CASCADE;

-- Tracing table for granular LLM observability
CREATE TABLE llm_traces (
    id UUID PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stage TEXT,
    topic_sn INTEGER,
    model TEXT NOT NULL,
    prompt JSONB NOT NULL,
    response TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER
);

-- Background Curation Queue
CREATE TABLE curation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    logs TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE evaluation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    logs TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_source ON content_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_mapping_topic ON source_to_topic_mapping(topic_id);
CREATE INDEX IF NOT EXISTS idx_facts_topic ON fact_extractions(topic_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON topic_knowledge(topic_id);
CREATE INDEX IF NOT EXISTS idx_content_topic ON topic_content(topic_id);
CREATE INDEX IF NOT EXISTS idx_overrides_topic ON knowledge_overrides(topic_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_activity_topic ON reviewer_activity(topic_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_activity_content ON reviewer_activity(content_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_results_topic ON evaluation_results(topic_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_topic ON token_usage(topic_sn);
CREATE INDEX IF NOT EXISTS idx_llm_traces_topic ON llm_traces(topic_sn);
CREATE INDEX IF NOT EXISTS idx_curation_jobs_topic ON curation_jobs(topic_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_topic ON evaluation_jobs(topic_id);

-- ---------------------------------------------------------------------------
-- Row Level Security (RLS) policies
-- ---------------------------------------------------------------------------

-- Enable RLS for all tables:
ALTER TABLE syllabus_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_to_topic_mapping ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviewer_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE curation_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_jobs ENABLE ROW LEVEL SECURITY;

-- 1. syllabus_topics Policies
CREATE POLICY "Allow public read syllabus_topics" ON syllabus_topics FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write syllabus_topics" ON syllabus_topics FOR ALL TO service_role USING (true);

-- 2. sources Policies
CREATE POLICY "Allow public read sources" ON sources FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write sources" ON sources FOR ALL TO service_role USING (true);

-- 3. normalized_documents Policies
CREATE POLICY "Allow public read normalized_documents" ON normalized_documents FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write normalized_documents" ON normalized_documents FOR ALL TO service_role USING (true);

-- 4. content_chunks Policies
CREATE POLICY "Allow public read content_chunks" ON content_chunks FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write content_chunks" ON content_chunks FOR ALL TO service_role USING (true);

-- 5. source_to_topic_mapping Policies
CREATE POLICY "Allow public read source_to_topic_mapping" ON source_to_topic_mapping FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write source_to_topic_mapping" ON source_to_topic_mapping FOR ALL TO service_role USING (true);

-- 6. fact_extractions Policies
CREATE POLICY "Allow public read fact_extractions" ON fact_extractions FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write fact_extractions" ON fact_extractions FOR ALL TO service_role USING (true);

-- 7. topic_knowledge Policies
CREATE POLICY "Allow public read topic_knowledge" ON topic_knowledge FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write topic_knowledge" ON topic_knowledge FOR ALL TO service_role USING (true);

-- 8. topic_content Policies
CREATE POLICY "Allow public read topic_content" ON topic_content FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write topic_content" ON topic_content FOR ALL TO service_role USING (true);

-- 9. knowledge_overrides Policies
CREATE POLICY "Allow public read knowledge_overrides" ON knowledge_overrides FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write knowledge_overrides" ON knowledge_overrides FOR ALL TO service_role USING (true);

-- 10. extraction_errors Policies
-- 10. reviewer_activity Policies
CREATE POLICY "Allow public read reviewer_activity" ON reviewer_activity FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write reviewer_activity" ON reviewer_activity FOR ALL TO service_role USING (true);

-- 11. evaluation_results Policies
CREATE POLICY "Allow public read evaluation_results" ON evaluation_results FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write evaluation_results" ON evaluation_results FOR ALL TO service_role USING (true);

-- 12. extraction_errors Policies
CREATE POLICY "Allow public read extraction_errors" ON extraction_errors FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write extraction_errors" ON extraction_errors FOR ALL TO service_role USING (true);

-- 13. token_usage Policies
CREATE POLICY "Allow public read token_usage" ON token_usage FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write token_usage" ON token_usage FOR ALL TO service_role USING (true);

-- 14. llm_traces Policies
CREATE POLICY "Allow public read llm_traces" ON llm_traces FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write llm_traces" ON llm_traces FOR ALL TO service_role USING (true);

-- 15. curation_jobs Policies
CREATE POLICY "Allow public read curation_jobs" ON curation_jobs FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write curation_jobs" ON curation_jobs FOR ALL TO service_role USING (true);

-- 16. evaluation_jobs Policies
CREATE POLICY "Allow public read evaluation_jobs" ON evaluation_jobs FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow service role write evaluation_jobs" ON evaluation_jobs FOR ALL TO service_role USING (true);

-- ---------------------------------------------------------------------------
-- Database Role Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON TABLE syllabus_topics TO service_role, postgres;
GRANT ALL ON TABLE sources TO service_role, postgres;
GRANT ALL ON TABLE normalized_documents TO service_role, postgres;
GRANT ALL ON TABLE content_chunks TO service_role, postgres;
GRANT ALL ON TABLE source_to_topic_mapping TO service_role, postgres;
GRANT ALL ON TABLE fact_extractions TO service_role, postgres;
GRANT ALL ON TABLE topic_knowledge TO service_role, postgres;
GRANT ALL ON TABLE topic_content TO service_role, postgres;
GRANT ALL ON TABLE knowledge_overrides TO service_role, postgres;
GRANT ALL ON TABLE reviewer_activity TO service_role, postgres;
GRANT ALL ON TABLE evaluation_results TO service_role, postgres;
GRANT ALL ON TABLE extraction_errors TO service_role, postgres;
GRANT ALL ON TABLE token_usage TO service_role, postgres;
GRANT ALL ON TABLE llm_traces TO service_role, postgres;
GRANT ALL ON TABLE curation_jobs TO service_role, postgres;
GRANT ALL ON TABLE evaluation_jobs TO service_role, postgres;

GRANT SELECT ON TABLE syllabus_topics TO anon, authenticated;
GRANT SELECT ON TABLE sources TO anon, authenticated;
GRANT SELECT ON TABLE normalized_documents TO anon, authenticated;
GRANT SELECT ON TABLE content_chunks TO anon, authenticated;
GRANT SELECT ON TABLE source_to_topic_mapping TO anon, authenticated;
GRANT SELECT ON TABLE fact_extractions TO anon, authenticated;
GRANT SELECT ON TABLE topic_knowledge TO anon, authenticated;
GRANT SELECT ON TABLE topic_content TO anon, authenticated;
GRANT SELECT ON TABLE knowledge_overrides TO anon, authenticated;
GRANT SELECT ON TABLE reviewer_activity TO anon, authenticated;
GRANT SELECT ON TABLE evaluation_results TO anon, authenticated;
GRANT SELECT ON TABLE extraction_errors TO anon, authenticated;
GRANT SELECT ON TABLE token_usage TO anon, authenticated;
GRANT SELECT ON TABLE llm_traces TO anon, authenticated;
GRANT SELECT ON TABLE curation_jobs TO anon, authenticated;
GRANT SELECT ON TABLE evaluation_jobs TO anon, authenticated;

-- Migration to add inputs_hash column for incremental generation caching (C)
ALTER TABLE topic_content ADD COLUMN IF NOT EXISTS inputs_hash TEXT;

-- Migration to add soft-retirement support for sources.
ALTER TABLE sources ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS reviewer_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    content_id UUID REFERENCES topic_content(id) ON DELETE SET NULL,
    reviewer_id TEXT,
    action TEXT NOT NULL,
    review_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    faithfulness_score NUMERIC,
    completeness_score NUMERIC,
    faithfulness_reasoning TEXT,
    completeness_reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW Vector Index Migration (Run via: alembic upgrade head)
-- Converts embedding column from JSONB to vector(384) and adds HNSW index
-- for O(log N) approximate nearest-neighbour search.
CREATE EXTENSION IF NOT EXISTS vector;
-- ALTER TABLE content_chunks DROP COLUMN IF EXISTS embedding;
-- ALTER TABLE content_chunks ADD COLUMN embedding vector(384);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw
--   ON content_chunks USING hnsw (embedding vector_cosine_ops)
--   WITH (m = 16, ef_construction = 64);
