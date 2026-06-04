# Specification Document 3

# Database Schema Reference (DSR)

**Version:** 1.0
**Status:** Implementation Blueprint
**Priority:** Critical

---

# 1. Purpose

This document defines:

- All database tables
- Relationships
- Constraints
- Indexes
- Enums
- Foreign keys
- Versioning strategy

for the MVP implementation.

Target Platform:

```text
Supabase
(PostgreSQL + pgvector)
```

---

# 2. Database Design Principles

## Principle 1

Knowledge must be traceable.

Every generated field must be traceable back to:

```text
Topic
Source
Chunk
Extraction
```

---

## Principle 2

Source-level information is never overwritten.

Store:

```text
Raw Extraction
```

before:

```text
Canonical Knowledge
```

---

## Principle 3

Version everything.

Track:

```text
Schema Version
Prompt Version
Model Version
```

---

# 3. Entity Relationship Diagram

```text
syllabus_topics
       │
       │
       ▼
fact_extractions
       ▲
       │
       │
content_chunks
       ▲
       │
       │
sources

fact_extractions
       │
       ▼
topic_knowledge
       │
       ▼
topic_content

sources
       │
       ▼
source_to_topic_mapping
```

---

# 4. ENUM Definitions

## Topic Type

```sql
CREATE TYPE topic_type AS ENUM (
  'concept',
  'command',
  'tool',
  'architecture',
  'process'
);
```

---

## Source Type

```sql
CREATE TYPE source_type AS ENUM (
  'website',
  'pdf',
  'docx',
  'book',
  'internal_document'
);
```

---

## Review Status

```sql
CREATE TYPE review_status AS ENUM (
  'pending',
  'approved',
  'rejected',
  'needs_regeneration'
);
```

---

## Processing Status

```sql
CREATE TYPE processing_status AS ENUM (
  'pending',
  'processing',
  'completed',
  'failed'
);
```

---

# 5. syllabus_topics

Master syllabus structure.

---

```sql
CREATE TABLE syllabus_topics (

    id UUID PRIMARY KEY,

    chapter TEXT NOT NULL,

    topic_name TEXT NOT NULL,

    topic_type topic_type NOT NULL,

    keywords TEXT[],

    difficulty_level TEXT,

    status processing_status DEFAULT 'pending',

    created_at TIMESTAMP DEFAULT NOW(),

    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## Indexes

```sql
CREATE INDEX idx_topics_type
ON syllabus_topics(topic_type);
```

---

# 6. sources

Trusted source registry.

---

```sql
CREATE TABLE sources (

    id UUID PRIMARY KEY,

    title TEXT NOT NULL,

    source_type source_type NOT NULL,

    url TEXT,

    trust_score INTEGER CHECK (
        trust_score BETWEEN 1 AND 10
    ),

    license_type TEXT,

    publication_date DATE,

    content_hash TEXT,

    last_crawled TIMESTAMP,

    crawl_status processing_status,

    created_at TIMESTAMP DEFAULT NOW(),

    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## Indexes

```sql
CREATE INDEX idx_source_trust
ON sources(trust_score);

CREATE INDEX idx_source_type
ON sources(source_type);
```

---

# 7. content_chunks

Stores normalized source content.

---

```sql
CREATE TABLE content_chunks (

    id UUID PRIMARY KEY,

    source_id UUID NOT NULL,

    chunk_text TEXT NOT NULL,

    metadata JSONB,

    embedding VECTOR(1024),

    chunk_number INTEGER,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (source_id)
    REFERENCES sources(id)
);
```

---

## Indexes

Vector:

```sql
CREATE INDEX idx_chunks_embedding
ON content_chunks
USING hnsw (embedding vector_cosine_ops);
```

---

Standard:

```sql
CREATE INDEX idx_chunks_source
ON content_chunks(source_id);
```

---

# 8. source_to_topic_mapping

Traceability layer.

---

```sql
CREATE TABLE source_to_topic_mapping (

    id UUID PRIMARY KEY,

    source_id UUID NOT NULL,

    chunk_id UUID NOT NULL,

    topic_id UUID NOT NULL,

    vector_score NUMERIC,

    reranker_score NUMERIC,

    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (source_id)
    REFERENCES sources(id),

    FOREIGN KEY (chunk_id)
    REFERENCES content_chunks(id),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id)
);
```

---

## Indexes

```sql
CREATE INDEX idx_mapping_topic
ON source_to_topic_mapping(topic_id);

CREATE INDEX idx_mapping_source
ON source_to_topic_mapping(source_id);
```

---

# 9. fact_extractions

Most important table.

Stores source-level knowledge.

---

```sql
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

    status processing_status,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id),

    FOREIGN KEY (source_id)
    REFERENCES sources(id),

    FOREIGN KEY (chunk_id)
    REFERENCES content_chunks(id)
);
```

---

## Example

```json
{
  "field_name": "definition",
  "field_value": {
    "value": "SDLC is a structured process..."
  }
}
```

---

## Indexes

```sql
CREATE INDEX idx_fact_topic
ON fact_extractions(topic_id);

CREATE INDEX idx_fact_source
ON fact_extractions(source_id);

CREATE INDEX idx_fact_field
ON fact_extractions(field_name);
```

---

# 10. topic_knowledge

Canonical knowledge.

Generated from CRS.

---

```sql
CREATE TABLE topic_knowledge (

    id UUID PRIMARY KEY,

    topic_id UUID NOT NULL,

    schema_version TEXT NOT NULL,

    knowledge JSONB NOT NULL,

    sources_used UUID[],

    confidence NUMERIC,

    created_at TIMESTAMP DEFAULT NOW(),

    updated_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id)
);
```

---

## Example

```json
{
  "definition": {
    "canonical_value": "...",
    "confidence": 92,
    "sources": ["IBM", "Atlassian"]
  }
}
```

---

## Indexes

```sql
CREATE INDEX idx_knowledge_topic
ON topic_knowledge(topic_id);
```

---

# 11. topic_content

Generated educational content.

---

```sql
CREATE TABLE topic_content (

    id UUID PRIMARY KEY,

    topic_id UUID NOT NULL,

    content_json JSONB NOT NULL,

    schema_version TEXT,

    generation_model TEXT,

    sources_used UUID[],

    confidence_score NUMERIC,

    consistency_check_status BOOLEAN,

    consistency_check_flags JSONB,

    review_status review_status,

    reviewer_id UUID,

    reviewed_at TIMESTAMP,

    review_notes TEXT,

    published_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id)
);
```

---

## Indexes

```sql
CREATE INDEX idx_content_topic
ON topic_content(topic_id);

CREATE INDEX idx_content_review
ON topic_content(review_status);
```

---

# 12. knowledge_overrides

Reviewer corrections.

Phase 2 ready.

---

```sql
CREATE TABLE knowledge_overrides (

    id UUID PRIMARY KEY,

    topic_id UUID NOT NULL,

    field_name TEXT NOT NULL,

    original_value JSONB,

    corrected_value JSONB,

    correction_note TEXT,

    reviewer_id UUID,

    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id)
);
```

---

# 13. pipeline_runs

Operational monitoring.

---

```sql
CREATE TABLE pipeline_runs (

    id UUID PRIMARY KEY,

    started_at TIMESTAMP,

    completed_at TIMESTAMP,

    status processing_status,

    topics_processed INTEGER,

    topics_failed INTEGER,

    total_llm_calls INTEGER,

    estimated_cost NUMERIC,

    error_log JSONB
);
```

---

# 14. llm_call_log

Cost and debugging.

---

```sql
CREATE TABLE llm_call_log (

    id UUID PRIMARY KEY,

    call_type TEXT,

    topic_id UUID,

    model TEXT,

    prompt_tokens INTEGER,

    completion_tokens INTEGER,

    latency_ms INTEGER,

    estimated_cost NUMERIC,

    success BOOLEAN,

    error_message TEXT,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id)
);
```

---

# 15. extraction_errors

Failure tracking.

---

```sql
CREATE TABLE extraction_errors (

    id UUID PRIMARY KEY,

    topic_id UUID,

    source_id UUID,

    chunk_id UUID,

    error_type TEXT,

    error_detail TEXT,

    retry_count INTEGER,

    resolved BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (topic_id)
    REFERENCES syllabus_topics(id),

    FOREIGN KEY (source_id)
    REFERENCES sources(id),

    FOREIGN KEY (chunk_id)
    REFERENCES content_chunks(id)
);
```

---

# 16. allowed_emails

Controls console dashboard credentials access and Row Level Security allowlists.

```sql
CREATE TABLE allowed_emails (
    email TEXT PRIMARY KEY
);
```

---

# 17. Security & Helper Functions

Enforces schema security and concurrency controls directly inside the PostgreSQL layer.

## is_allowed_user()

Restricts table access by evaluating the Supabase Auth JWT email against the allowlist database.

```sql
CREATE OR REPLACE FUNCTION is_allowed_user()
RETURNS BOOLEAN SECURITY DEFINER AS $$
BEGIN
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
```

---

## claim_next_job(worker_name)

Provides an atomic transaction block that prevents TOCTOU collisions during parallel curation pipeline job runs.

```sql
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
```

---

# 18. Future Tables (Deferred)

Not required for MVP.

---

## source_update_history

Track source changes.

---

## reviewer_activity

Audit reviewer actions.

---

## content_versions

Track generated content revisions.

---

## schema_registry

Manage schema evolution.

---

# 19. Row Counts (Expected MVP)

| Table                   | Approx Rows |
| ----------------------- | ----------: |
| syllabus_topics         |          10 |
| allowed_emails          |           5 |
| sources                 |          30 |
| content_chunks          |    500-3000 |
| source_to_topic_mapping |   1000-5000 |
| fact_extractions        |  5000-20000 |
| topic_knowledge         |          10 |
| topic_content           |          10 |

---

# 20. Backup Strategy

Daily backup:

```text
Supabase Scheduled Backup
```

---

Retention:

```text
30 Days
```

---

# 21. MVP Database Flow

```text
sources
    ↓
content_chunks
    ↓
source_to_topic_mapping
    ↓
fact_extractions
    ↓
topic_knowledge
    ↓
topic_content
```

---

# 22. Acceptance Criteria

The database design is accepted if:

1. Every generated statement can be traced to sources.
2. Source-level extractions are never lost.
3. Canonical knowledge can be regenerated.
4. Source updates can trigger selective reprocessing.
5. Reviewer actions are recorded.
6. The schema supports future expansion to 82+ topics.
7. All core workflows can be implemented directly in Supabase without architectural changes.
8. Row Level Security policies prevent unauthorized access to private data blocks.

---

## Relationship to Other Documents

### Input

- Extraction Prompt Specification (EPS)
- Conflict Resolution Specification (CRS)

### Output

Provides storage layer for:

```text
Extraction
Conflict Resolution
Content Generation
Human Review
```
