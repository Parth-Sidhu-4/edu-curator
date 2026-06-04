# AI-Powered Educational Content Curation Platform

## Final Implementation Plan (Architecture Frozen)

**Version:** Final Pre-Implementation Architecture
**Status:** Approved for Specification Phase
**Scope:** Educational Content Generation from Trusted Sources → Syllabus-Aligned Knowledge Base → Human Review → Publication

---

# 1. Project Goal

Build a system that automatically:

1. Ingests trusted educational sources
2. Maps source content to predefined syllabus topics
3. Extracts structured knowledge
4. Resolves conflicts across sources
5. Generates educational content
6. Provides source attribution and confidence scores
7. Supports human review
8. Stores approved content in Supabase

The system is **not a chatbot** and **not a traditional RAG system**.

The primary asset is a **Topic-Centric Knowledge Base** aligned to the syllabus.

---

# 2. Core Philosophy

## Traditional RAG

```text
Question
   ↓
Retrieve
   ↓
Answer
```

---

## Our Architecture

```text
Known Syllabus
      ↓
Trusted Sources
      ↓
Knowledge Extraction
      ↓
Topic Knowledge Base
      ↓
Educational Content
```

---

# 3. High-Level Architecture

```text
Syllabus Topics
        │
        ▼
Topic Classification
        │
        ▼
Source Repository
        │
        ▼
Content Ingestion
        │
        ▼
Normalization
        │
        ▼
Chunking
        │
        ▼
Embeddings
        │
        ▼
Topic Mapping
        │
        ▼
Reranking
        │
        ▼
Structured Extraction
        │
        ▼
Schema Validation
        │
        ▼
Source-Level Knowledge Store
        │
        ▼
Conflict Resolution
        │
        ▼
Canonical Knowledge Base
        │
        ▼
Content Generation
        │
        ▼
Consistency Verification
        │
        ▼
Human Review
        │
        ▼
Publication
```

---

# 4. Syllabus Registration

The syllabus drives the entire system.

Example:

```json
{
  "topic_id": "1.1",
  "chapter": "DevOps Fundamentals",
  "topic_name": "Definition of SDLC",
  "topic_type": "Concept"
}
```

---

## Table

```sql
syllabus_topics

id
chapter
topic_name
topic_type
keywords
difficulty_level
status
created_at
```

---

# 5. Topic Types

Each topic type uses its own extraction schema.

---

## Concept

Examples:

- SDLC
- Agile
- DevOps

---

## Command

Examples:

- git clone
- git commit

---

## Tool

Examples:

- Docker
- Jenkins

---

## Architecture

Examples:

- Kubernetes Architecture

---

## Process

Examples:

- CI/CD Pipeline

---

# 6. Source Repository

## Purpose

Maintain trusted source metadata.

---

## Table

```sql
sources

id
title
source_type
url
trust_score
license_type
publication_date
content_hash
last_crawled
crawl_status
created_at
```

---

## Trust Score Rubric

| Score | Source Type                                      |
| ----- | ------------------------------------------------ |
| 9-10  | Official Documentation, Standards Bodies         |
| 7-8   | University Resources, Microsoft Learn, Atlassian |
| 5-6   | Reputable Books, Established Blogs               |
| 3-4   | Community Resources                              |
| 1-2   | Unknown or Unverified Sources                    |

---

# 7. Content Ingestion

## Supported Sources

- Websites
- PDFs
- DOCX
- Books

---

## Tools

### Websites

- Crawl4AI
- Firecrawl

### PDFs

- PyMuPDF

### DOCX

- python-docx

### OCR

- PaddleOCR

---

# 8. Deduplication

## Exact Duplicates

```text
SHA256 Hash
```

---

## MVP

Near-duplicate detection deferred.

MinHash deferred to Phase 2.

---

# 9. Normalization

All content is converted into:

```json
{
  "source_id": "",
  "title": "",
  "content": "",
  "metadata": {}
}
```

---

# 10. Chunking

Recommended:

```text
Chunk Size: 500–1000 words
Overlap: 100 words
```

---

## Table

```sql
content_chunks

id
source_id
chunk_text
metadata
embedding
created_at
```

---

# 11. Embeddings

## Model

Primary:

```text
BAAI/bge-m3
```

---

## Storage

Supabase pgvector

---

# 12. Topic Mapping

## Goal

Find chunks relevant to syllabus topics.

---

## MVP Retrieval

```text
Vector Search
       ↓
Top K Chunks
```

---

## Future

Hybrid BM25 + Vector Search

Deferred until retrieval quality demands it.

---

# 13. Reranking

## Model

```text
BAAI/bge-reranker-v2-m3
```

---

## Flow

```text
Top 30 Chunks
      ↓
Reranker
      ↓
Top 10 Chunks
```

---

# 14. Source-to-Topic Traceability

## Table

```sql
source_to_topic_mapping

id
source_id
chunk_id
topic_id
vector_score
reranker_score
is_active
created_at
```

---

Purpose:

- Selective reprocessing
- Source provenance
- Auditability

---

# 15. Structured Extraction

## Principle

Only extract information explicitly present in the source.

---

## Extraction Rules

1. Never infer.
2. Never fill missing fields.
3. Return null when unsupported.
4. Output must match schema exactly.

---

# 16. Topic Schemas

## Concept Topic

```json
{
  "definition": "",
  "purpose": "",
  "key_properties": [],
  "benefits": [],
  "limitations": [],
  "common_misconceptions": [],
  "related_topics": []
}
```

---

## Command Topic

```json
{
  "syntax": "",
  "parameters": [
    {
      "name": "",
      "description": "",
      "required": false
    }
  ],
  "examples": [
    {
      "command": "",
      "description": ""
    }
  ],
  "expected_output": "",
  "common_errors": []
}
```

---

## Tool Topic

```json
{
  "overview": "",
  "features": [],
  "use_cases": [],
  "advantages": [],
  "limitations": []
}
```

---

## Architecture Topic

```json
{
  "overview": "",
  "components": [],
  "interactions": [],
  "tradeoffs": []
}
```

---

## Process Topic

```json
{
  "overview": "",
  "steps": [],
  "inputs": [],
  "outputs": [],
  "benefits": [],
  "limitations": []
}
```

---

# 17. Schema Validation

## Tool

Pydantic

---

Flow:

```text
Extraction
     ↓
Validation
     ↓
Storage
```

---

Validation Failure:

```text
Retry
  ↓
Log Error
```

---

# 18. Source-Level Knowledge Storage

## Table

```sql
fact_extractions

id
topic_id
source_id
chunk_id
field_name
field_value JSONB
schema_version
prompt_version
extraction_model
extraction_confidence
status
created_at
```

---

## Principle

Store all source-level extractions.

Never discard information during extraction.

---

# 19. Conflict Resolution

## Scalar Fields

Examples:

- definition
- purpose
- overview
- syntax

---

Resolution:

```text
Highest Trust Source
         ↓
Canonical Value
```

Alternatives remain stored.

---

## Array Fields

Examples:

- benefits
- limitations
- features
- examples

---

Resolution:

```text
Merge
   ↓
Semantic Deduplication
   ↓
Canonical Array
```

No information discarded.

---

# 20. Canonical Knowledge Base

## Table

```sql
topic_knowledge

id
topic_id
schema_version
knowledge JSONB
sources_used
confidence
created_at
updated_at
```

---

Example:

```json
{
  "definition": {
    "canonical_value": "...",
    "confidence": 92,
    "sources": ["IBM", "Atlassian"],
    "alternative_values": [...]
  }
}
```

---

# 21. Confidence Scoring

## Formula

```text
Confidence =
0.35 × SourceAuthority
+
0.35 × AgreementScore
+
0.15 × ExtractionCompleteness
+
0.15 × RecencyScore
```

---

## Agreement Score

For text fields:

```text
Embedding Similarity
```

Threshold:

```text
0.80
```

---

## Review Thresholds

```text
90 - 100
High Confidence

75 - 89
Standard Review

Below 75
Priority Review
```

---

## Mandatory Review Conditions

Always review if:

- Single-source topic
- Confidence below 75
- Consistency check fails
- Alternative values exist from similarly trusted sources

---

# 22. Content Generation

Generate only from canonical knowledge.

Never generate from raw chunks.

---

Flow:

```text
Canonical Knowledge
        ↓
Template
        ↓
Educational Content
```

---

# 23. Post-Generation Consistency Check

## Purpose

Detect hallucinations.

---

Input:

```text
Canonical Knowledge
Generated Content
```

---

Output:

```text
PASS
or
FLAG
```

---

Any flagged topic requires human review.

---

# 24. Content Storage

## Table

```sql
topic_content

id
topic_id
content_json
schema_version
generation_model
sources_used
confidence_score
consistency_check_status
consistency_check_flags
review_status
reviewer_id
reviewed_at
review_notes
published_at
created_at
```

---

# 25. Human Review

## Reviewer Actions

- Approve
- Reject
- Request Regeneration

Field-level corrections deferred to Phase 2.

---

Reviewer sees:

```text
Generated Content
Confidence Score
Sources Used
Canonical Knowledge
```

---

# 26. Reviewer Override Storage

## Table

```sql
knowledge_overrides

id
topic_id
field_name
original_value
corrected_value
correction_note
reviewer_id
created_at
is_active
```

---

Phase 2 feature.

Schema created now for future compatibility.

---

# 27. Versioning

All major artifacts must be versioned.

---

Track:

```text
Schema Version
Prompt Version
Extraction Model
Generation Model
```

---

# 28. Operational Monitoring

## Table

```sql
pipeline_runs

id
started_at
completed_at
status
topics_processed
topics_failed
total_llm_calls
estimated_cost
error_log
```

---

## Table

```sql
llm_call_log

id
call_type
topic_id
model
prompt_tokens
completion_tokens
latency_ms
estimated_cost
success
error_message
created_at
```

---

# 29. Error Tracking

## Table

```sql
extraction_errors

id
topic_id
source_id
chunk_id
error_type
error_detail
retry_count
resolved
created_at
```

---

# 30. Source Update Handling

When source hash changes:

```text
Source Updated
      ↓
Lookup source_to_topic_mapping
      ↓
Affected Topics
      ↓
Selective Reprocessing
```

---

MVP:

Manual trigger.

Automation deferred.

---

# 31. Queue System

## MVP

```text
RQ
+
Redis
```

---

Future:

```text
Celery
```

if scale requires.

---

# 32. Explicit Deferrals

Not part of MVP:

- GraphRAG
- Neo4j
- Knowledge Graphs
- Agentic Systems
- Airflow
- Dagster
- Fine-Tuning
- Automated Source Discovery
- MinHash Deduplication
- Hybrid BM25 Retrieval
- Advanced Reviewer Corrections

---

# 33. MVP Scope

## Topics

10 Topics

---

## Sources

3 Trusted Sources Per Topic

---

## Topic Types

Only:

- Concept
- Command

---

## Build Order

### Week 1

- Extraction Prompt Design
- Schema Finalization
- Source Registration
- Supabase Setup

### Week 2

- Ingestion
- Chunking
- Embeddings

### Week 3

- Retrieval
- Reranking
- Structured Extraction

### Week 4

- Canonicalization
- Confidence Scoring
- Content Generation

### Week 5

- Review Dashboard
- End-to-End Testing

### Week 6

- Bug Fixes
- Tuning
- Documentation

### Weeks 7–8

- Buffer
- Stabilization
- Optional Improvements

---

# Success Criteria

The MVP succeeds if:

1. Content is generated for all 10 topics.
2. Every generated statement is traceable to sources.
3. Reviewers can verify source provenance.
4. Confidence scores are meaningful.
5. Selective reprocessing works.
6. Content quality requires only minor reviewer edits.
7. The architecture can scale from 10 topics to 82 topics without redesign.

---

<!-- # Final Verdict

This architecture is considered **implementation-ready**, pending the creation of the following specification documents:

1. Extraction Prompt Specification
2. Conflict Resolution Specification
3. Final Database Schema Reference
4. Reviewer Workflow Specification
5. Source Management & Operations Specification

Once these five documents are completed, development can begin with minimal architectural uncertainty. -->
