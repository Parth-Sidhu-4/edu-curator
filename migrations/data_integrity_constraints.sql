-- 1. Clean up orphaned rows
DELETE FROM content_chunks WHERE source_id NOT IN (SELECT id FROM sources);
DELETE FROM source_to_topic_mapping WHERE source_id NOT IN (SELECT id FROM sources);
DELETE FROM source_to_topic_mapping WHERE chunk_id NOT IN (SELECT id FROM content_chunks);
DELETE FROM source_to_topic_mapping WHERE topic_id NOT IN (SELECT id FROM syllabus_topics);
DELETE FROM fact_extractions WHERE topic_id NOT IN (SELECT id FROM syllabus_topics);
DELETE FROM fact_extractions WHERE source_id NOT IN (SELECT id FROM sources);
DELETE FROM fact_extractions WHERE chunk_id NOT IN (SELECT id FROM content_chunks);
DELETE FROM topic_knowledge WHERE topic_id NOT IN (SELECT id FROM syllabus_topics);
DELETE FROM topic_content WHERE topic_id NOT IN (SELECT id FROM syllabus_topics);
DELETE FROM knowledge_overrides WHERE topic_id NOT IN (SELECT id FROM syllabus_topics);

-- 2. Add Foreign Key constraints
ALTER TABLE content_chunks
ADD CONSTRAINT fk_content_chunks_source_id
FOREIGN KEY (source_id) REFERENCES sources(id)
ON DELETE CASCADE;

ALTER TABLE source_to_topic_mapping
ADD CONSTRAINT fk_mapping_source_id
FOREIGN KEY (source_id) REFERENCES sources(id)
ON DELETE CASCADE;

ALTER TABLE source_to_topic_mapping
ADD CONSTRAINT fk_mapping_chunk_id
FOREIGN KEY (chunk_id) REFERENCES content_chunks(id)
ON DELETE CASCADE;

ALTER TABLE source_to_topic_mapping
ADD CONSTRAINT fk_mapping_topic_id
FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id)
ON DELETE CASCADE;

ALTER TABLE fact_extractions
ADD CONSTRAINT fk_facts_topic_id
FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id)
ON DELETE CASCADE;

ALTER TABLE fact_extractions
ADD CONSTRAINT fk_facts_source_id
FOREIGN KEY (source_id) REFERENCES sources(id)
ON DELETE CASCADE;

ALTER TABLE fact_extractions
ADD CONSTRAINT fk_facts_chunk_id
FOREIGN KEY (chunk_id) REFERENCES content_chunks(id)
ON DELETE CASCADE;

ALTER TABLE topic_knowledge
ADD CONSTRAINT fk_knowledge_topic_id
FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id)
ON DELETE CASCADE;

ALTER TABLE topic_content
ADD CONSTRAINT fk_content_topic_id
FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id)
ON DELETE CASCADE;

ALTER TABLE knowledge_overrides
ADD CONSTRAINT fk_overrides_topic_id
FOREIGN KEY (topic_id) REFERENCES syllabus_topics(id)
ON DELETE CASCADE;
