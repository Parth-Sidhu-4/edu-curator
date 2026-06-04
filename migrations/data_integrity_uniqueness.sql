-- 1. Add version column to topic_content if not exists
ALTER TABLE topic_content ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- 2. Clean up existing duplicate records before applying constraints
DELETE FROM topic_knowledge a USING topic_knowledge b
WHERE a.id < b.id AND a.topic_id = b.topic_id;

DELETE FROM topic_content a USING topic_content b
WHERE a.id < b.id AND a.topic_id = b.topic_id;

DELETE FROM source_to_topic_mapping a USING source_to_topic_mapping b
WHERE a.id < b.id AND a.source_id = b.source_id AND a.chunk_id = b.chunk_id AND a.topic_id = b.topic_id;

DELETE FROM fact_extractions a USING fact_extractions b
WHERE a.id < b.id AND a.topic_id = b.topic_id AND a.source_id = b.source_id AND a.chunk_id = b.chunk_id AND a.field_name = b.field_name;

DELETE FROM knowledge_overrides a USING knowledge_overrides b
WHERE a.id < b.id AND a.topic_id = b.topic_id AND a.field_name = b.field_name AND a.is_active = true AND b.is_active = true;

DELETE FROM curation_jobs a USING curation_jobs b
WHERE a.id < b.id AND a.topic_id = b.topic_id AND a.status = b.status AND a.status IN ('pending', 'running');

DELETE FROM evaluation_jobs a USING evaluation_jobs b
WHERE a.id < b.id AND a.topic_id = b.topic_id AND a.status = b.status AND a.status IN ('pending', 'running');

-- 3. Add range checks and status constraints
ALTER TABLE sources DROP CONSTRAINT IF EXISTS check_trust_score_range;
ALTER TABLE sources ADD CONSTRAINT check_trust_score_range CHECK (trust_score >= 1.0 AND trust_score <= 10.0);

ALTER TABLE syllabus_topics DROP CONSTRAINT IF EXISTS check_topics_status;
ALTER TABLE syllabus_topics ADD CONSTRAINT check_topics_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'));

ALTER TABLE topic_content DROP CONSTRAINT IF EXISTS check_content_review_status;
ALTER TABLE topic_content ADD CONSTRAINT check_content_review_status CHECK (review_status IN ('pending', 'approved', 'rejected', 'needs_regeneration'));

-- 4. Add unique constraints and partial unique indexes
ALTER TABLE topic_knowledge DROP CONSTRAINT IF EXISTS unique_topic_knowledge_topic_id;
ALTER TABLE topic_knowledge ADD CONSTRAINT unique_topic_knowledge_topic_id UNIQUE (topic_id);

ALTER TABLE topic_content DROP CONSTRAINT IF EXISTS unique_topic_content_topic_id;
ALTER TABLE topic_content ADD CONSTRAINT unique_topic_content_topic_id UNIQUE (topic_id);

ALTER TABLE source_to_topic_mapping DROP CONSTRAINT IF EXISTS unique_source_to_topic_mapping;
ALTER TABLE source_to_topic_mapping ADD CONSTRAINT unique_source_to_topic_mapping UNIQUE (source_id, chunk_id, topic_id);

ALTER TABLE fact_extractions DROP CONSTRAINT IF EXISTS unique_fact_extractions;
ALTER TABLE fact_extractions ADD CONSTRAINT unique_fact_extractions UNIQUE (topic_id, source_id, chunk_id, field_name);

DROP INDEX IF EXISTS idx_unique_active_override;
CREATE UNIQUE INDEX idx_unique_active_override ON knowledge_overrides (topic_id, field_name) WHERE is_active = true;

DROP INDEX IF EXISTS idx_unique_active_curation_job;
CREATE UNIQUE INDEX idx_unique_active_curation_job ON curation_jobs (topic_id, status) WHERE status IN ('pending', 'running');

DROP INDEX IF EXISTS idx_unique_active_evaluation_job;
CREATE UNIQUE INDEX idx_unique_active_evaluation_job ON evaluation_jobs (topic_id, status) WHERE status IN ('pending', 'running');
