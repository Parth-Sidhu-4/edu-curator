# Specification Document 5

# Source Management & Operations Specification (SMOS)

**Version:** 1.0
**Status:** Required Before Implementation
**Priority:** Critical

---

# 1. Purpose

This document defines how sources are:

- Discovered
- Approved
- Registered
- Ingested
- Updated
- Monitored
- Retired

The goal is to ensure that the knowledge base is built only from trusted, maintainable, and auditable sources.

---

# 2. Core Philosophy

The quality of the knowledge base cannot exceed the quality of its sources.

Therefore:

```text
Source Quality
      ↓
Knowledge Quality
      ↓
Content Quality
```

Poor sources must be filtered before entering the system.

---

# 3. Source Lifecycle

```text
Candidate Source
        ↓
Evaluation
        ↓
Approval
        ↓
Registration
        ↓
Ingestion
        ↓
Monitoring
        ↓
Update Detection
        ↓
Reprocessing
        ↓
Retirement (if necessary)
```

---

# 4. Approved Source Categories

## Tier 1: Official Sources

Examples:

```text
Docker Documentation
Kubernetes Documentation
Git Documentation
Microsoft Learn
AWS Documentation
Google Cloud Documentation
```

Trust Score:

```text
9-10
```

---

## Tier 2: Educational Institutions

Examples:

```text
MIT
Stanford
NPTEL
University Course Material
```

Trust Score:

```text
7-8
```

---

## Tier 3: Reputable Books

Examples:

```text
The DevOps Handbook
Kubernetes Up & Running
Docker Deep Dive
```

Trust Score:

```text
6-8
```

---

## Tier 4: Community Resources

Examples:

```text
Medium Articles
Personal Blogs
Community Tutorials
```

Trust Score:

```text
3-5
```

Use only when authoritative sources are unavailable.

---

# 5. Source Approval Rules

A source may be approved only if:

---

## Rule 1

Content is relevant to the syllabus.

---

## Rule 2

Content is technically accurate.

---

## Rule 3

Source is publicly accessible or legally licensed.

---

## Rule 4

Source has identifiable authorship or organizational ownership.

---

## Rule 5

Source does not significantly duplicate existing approved sources.

---

# 6. Source Registration Process

For every approved source:

---

## Required Metadata

```json
{
  "title": "",
  "source_type": "",
  "url": "",
  "trust_score": 0,
  "publication_date": "",
  "license_type": "",
  "owner": ""
}
```

---

## Stored In

```sql
sources
```

---

# 7. Trust Score Assignment

Trust score is assigned during onboarding.

---

## Scoring Guide

| Score | Meaning                                           |
| ----- | ------------------------------------------------- |
| 10    | Official standard or vendor documentation         |
| 9     | Official educational platform                     |
| 8     | University or highly respected educational source |
| 7     | Published technical book                          |
| 6     | Reputable training platform                       |
| 5     | Established technical blog                        |
| 4     | Community-written content                         |
| 3     | Limited verification                              |
| 1-2   | Avoid unless absolutely necessary                 |

---

# 8. Source Ownership

Every source must have an owner.

Owner may be:

```text
System Admin
Content Team
Subject Matter Expert
```

Responsibilities:

- Source approval
- Source removal
- Trust score maintenance

---

# 9. Website Ingestion Policy

## Supported

Documentation sites

Examples:

```text
docs.docker.com
kubernetes.io/docs
learn.microsoft.com
```

---

## Ingestion Frequency

MVP:

```text
Manual
```

---

Future:

```text
Weekly
```

or

```text
Monthly
```

depending on source volatility.

---

# 10. PDF Ingestion Policy

Supported:

```text
Books
Whitepapers
Technical Guides
Course Material
```

---

Requirements:

```text
Readable Text Layer Preferred
```

---

OCR only when necessary.

---

# 11. Book Ingestion Policy

Before ingestion:

Verify:

```text
License
Copyright
Permission
```

---

Store metadata:

```text
Edition
Publication Date
Publisher
```

---

# 12. Content Hashing

Every source receives:

```text
content_hash
```

stored in:

```sql
sources
```

---

Purpose:

```text
Detect Changes
```

---

Example

```text
Source Version A
Hash = abc123

Source Version B
Hash = xyz456
```

Change detected.

---

# 13. Source Update Detection

When source is re-ingested:

```text
Compute Hash
      ↓
Compare With Existing
```

---

## No Change

```text
Skip Processing
```

---

## Change Detected

```text
Mark Source Updated
```

Proceed to reprocessing.

---

# 14. Reprocessing Workflow

When source changes:

```text
Updated Source
        ↓
Find Related Topics
        ↓
Invalidate Knowledge
        ↓
Re-extract
        ↓
Re-resolve
        ↓
Regenerate Content
```

---

## Uses

```sql
source_to_topic_mapping
```

to identify affected topics.

---

# 15. Selective Reprocessing

Never rebuild everything.

---

Correct:

```text
Updated Docker Source
        ↓
Docker Topics Only
```

---

Incorrect:

```text
Updated Docker Source
        ↓
Rebuild Entire Knowledge Base
```

---

# 16. Source Retirement

A source may be retired if:

---

## Reason 1

No longer accessible.

---

## Reason 2

Information obsolete.

---

## Reason 3

Trust score downgraded.

---

## Reason 4

License restrictions change.

---

# 17. Retirement Workflow

```text
Retire Source
      ↓
Deactivate Source
      ↓
Retain Historical Records
```

---

Never delete historical knowledge.

---

# 18. Source Deduplication Policy

Before ingestion:

---

## Exact Duplicate

Detected using:

```text
SHA256
```

---

Result:

```text
Skip Ingestion
```

---

## Near Duplicate

Deferred to Phase 2.

---

# 19. Monitoring Requirements

Track:

---

## Sources Added

```text
Count Per Month
```

---

## Sources Updated

```text
Count Per Month
```

---

## Sources Retired

```text
Count Per Month
```

---

## Failed Ingestion Jobs

```text
Count Per Month
```

---

# 20. Operational Dashboards

MVP dashboard should show:

---

### Source Health

```text
Total Sources
Active Sources
Retired Sources
```

---

### Processing Health

```text
Successful Ingestions
Failed Ingestions
Pending Reprocessing
```

---

### Cost Metrics

```text
Estimated LLM Cost
Extraction Cost
Generation Cost
```

---

# 21. Error Handling

## Ingestion Failure

Example:

```text
Website Unreachable
```

---

Action:

```text
Retry 3 Times
```

---

Still failing:

```text
Create Error Record
Notify Admin
```

---

## Parsing Failure

Example:

```text
PDF Corrupted
```

---

Action:

```text
Flag Source
Require Manual Review
```

---

# 22. Security & Compliance

Only ingest content that:

---

## Allowed

```text
Public Documentation
Licensed Books
Approved Internal Material
Uploaded Local/Supabase Media Assets (Images, PDFs)
```

---

## Not Allowed

```text
Pirated Books
Copyright-Infringing Material
Unauthorized Content
Unsafe paths (Path traversal attempts outside /data/uploads/)
```

---

## Media Asset Ingestion Hardening

All uploaded assets (e.g. via curation reviewers) must be checked for traversal exploits:
- Ingestion routes must strictly resolve absolute paths and verify they reside in the designated static upload directory.
- The server Content Security Policy (CSP) headers must be strictly configured to allow image loading (`img-src`) only from `'self'` and the verified Supabase remote storage subdomain (`https://*.supabase.co`).

---

# 23. Backup & Recovery

Source metadata:

```text
Daily Backup
```

---

Knowledge base:

```text
Daily Backup
```

---

Retention:

```text
30 Days Minimum
```

---

# 24. Operational Roles

## Reviewer

Can:

```text
View Sources
View Provenance
Upload and insert images into textbooks
```

---

## Admin

Can:

```text
Approve Sources
Retire Sources
Modify Trust Scores
Trigger Reprocessing
```

---

# 25. MVP Scope

Supported:

```text
Websites
PDFs (Local & Remote Upload)
DOCX (Local & Remote Upload)
Images (Local Upload /data/uploads/ and remote Supabase Storage supabase://uploads/)
```

---

Deferred:

```text
Automated Source Discovery
Scheduled Crawling
Near-Duplicate Detection
Advanced OCR Pipelines
```

---

# 26. Success Criteria

The source management system is successful if:

1. Every source has metadata and a trust score.
2. Every topic can be traced to contributing sources.
3. Source updates trigger selective reprocessing.
4. Duplicate sources are not ingested repeatedly.
5. Source retirement does not break historical traceability.
6. Operational failures are visible and auditable.
7. The source repository remains trustworthy over time.

---

# 27. Relationship to Other Documents

### Works With

**DSR**

Uses:

```sql
sources
content_chunks
source_to_topic_mapping
pipeline_runs
extraction_errors
```

---

### Feeds

**EPS**

Provides:

```text
Source Chunks
Metadata
Trust Scores
```

---

### Supports

**CRS**

Provides:

```text
Source Authority
Recency Information
Provenance
```

---

### Supports

**RWS**

Provides:

```text
Source Inspection
Source Traceability
Alternative Source Views
```

---

# Final Documentation Set Complete

At this point, the architecture is supported by:

1. ✅ **Extraction Prompt Specification (EPS)**
2. ✅ **Conflict Resolution Specification (CRS)**
3. ✅ **Database Schema Reference (DSR)**
4. ✅ **Reviewer Workflow Specification (RWS)**
5. ✅ **Source Management & Operations Specification (SMOS)**
