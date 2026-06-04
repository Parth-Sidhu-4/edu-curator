# Specification Document 2

# Conflict Resolution Specification (CRS)

**Version:** 1.0
**Status:** Required Before Implementation
**Priority:** Critical

---

# 1. Purpose

The Conflict Resolution Layer transforms multiple source-level extractions into a single canonical knowledge representation.

Input:

```text
fact_extractions
```

Output:

```text
topic_knowledge
```

This layer determines:

- Which source becomes canonical
- How disagreements are handled
- When human review is required
- How confidence scores are computed

---

# 2. Core Philosophy

## Preserve First, Merge Later

Never discard extracted information.

Incorrect:

```text
IBM Definition
Microsoft Definition
Atlassian Definition
        ↓
Keep Only One
```

Correct:

```text
IBM Definition
Microsoft Definition
Atlassian Definition
        ↓
Store All
        ↓
Resolve
        ↓
Canonical Knowledge
```

---

# 3. Knowledge Lifecycle

```text
Source Chunks
      ↓
Extraction
      ↓
fact_extractions
      ↓
Grouping By Topic
      ↓
Field-Level Resolution
      ↓
Canonical Knowledge
      ↓
topic_knowledge
```

---

# 4. Resolution Scope

Conflict resolution occurs at the field level.

Example:

```json
{
  "definition": "...",
  "purpose": "...",
  "benefits": [...]
}
```

Each field is resolved independently.

---

# 5. Field Categories

Two categories exist:

## Scalar Fields

Single value.

Examples:

```text
definition
purpose
overview
syntax
expected_output
```

---

## Collection Fields

Multiple values.

Examples:

```text
benefits
limitations
features
examples
steps
components
```

---

# 6. Scalar Field Resolution

Example:

### IBM

```json
{
  "definition": "SDLC is a structured process for software development."
}
```

---

### Microsoft

```json
{
  "definition": "SDLC is a framework used to develop software systems."
}
```

---

### Atlassian

```json
{
  "definition": "SDLC is a structured process for software development."
}
```

---

# Resolution Strategy

Step 1:

Group candidate values.

---

Step 2:

Compute semantic similarity.

Example:

```text
IBM ↔ Atlassian
0.95
```

```text
IBM ↔ Microsoft
0.82
```

---

Step 3:

Create clusters.

Example:

```text
Cluster A
IBM
Atlassian

Cluster B
Microsoft
```

---

Step 4:

Calculate cluster confidence.

Formula:

```text
Cluster Score =
0.6 × Agreement
+
0.4 × Average Source Authority
```

---

Step 5:

Select highest-scoring cluster.

---

Step 6:

Within winning cluster choose:

```text
Highest Trust Source
```

as canonical wording.

---

# Example Result

```json
{
  "canonical_value": "SDLC is a structured process for software development.",
  "sources": ["IBM", "Atlassian"],
  "alternative_values": [
    {
      "value": "SDLC is a framework used to develop software systems.",
      "source": "Microsoft"
    }
  ]
}
```

---

# 7. Collection Field Resolution

Example:

### Source A

```json
{
  "benefits": ["Improves quality", "Reduces risk"]
}
```

---

### Source B

```json
{
  "benefits": ["Improves software quality", "Reduces risk"]
}
```

---

# Resolution Process

Step 1:

Merge all values.

---

Step 2:

Semantic Deduplication.

Example:

```text
Improves quality
Improves software quality
```

↓

```text
Single Canonical Benefit
```

---

Step 3:

Preserve provenance.

---

## FAQ (QA Collection) Resolution

For complex collection fields like `faq` (which are arrays of `{question, answer}` objects):

1. **Semantic Question Clustering**: Group QA entries by running semantic similarity comparisons on the `question` text.
2. **Canonical Answer Election**: For each question cluster, elect the wording and answer text from the candidate with the highest **Source Authority**.
3. **Traceability Mapping**: Group and attach all source IDs that contributed to the resolved QA node.

---

# Example Result

```json
{
  "benefits": [
    {
      "value": "Improves software quality",
      "sources": ["IBM", "Microsoft"]
    },
    {
      "value": "Reduces risk",
      "sources": ["IBM", "Microsoft"]
    }
  ],
  "faq": [
    {
      "question": "What is the primary benefit of CI?",
      "answer": "Continuous Integration reduces integration friction and increases stability by integrating code changes daily.",
      "sources": ["IBM", "Microsoft"]
    }
  ]
}
```

---

# 8. Source Authority

Every source has a trust score.

Defined in:

```sql
sources.trust_score
```

---

# Authority Levels

| Score | Type                          |
| ----- | ----------------------------- |
| 9-10  | Official Documentation        |
| 7-8   | Universities, Microsoft Learn |
| 5-6   | Established Books             |
| 3-4   | Community Sources             |
| 1-2   | Unverified Sources            |

---

# Authority Rule

When conflicts exist:

```text
Trust Score
      ↓
Agreement
      ↓
Extraction Confidence
```

in that order.

---

# 9. Single Source Topics

Example:

Only IBM available.

---

Result:

```json
{
  "definition": {
    "canonical_value": "...",
    "source_count": 1
  }
}
```

---

# Rule

Single-source topics are always flagged.

Reason:

No agreement signal exists.

---

# 10. Contradictory Information

Example:

Source A

```text
6 phases
```

Source B

```text
7 phases
```

---

Similarity:

```text
Low
```

---

Result:

```json
{
  "status": "conflict_detected"
}
```

---

# Rule

Human review required.

No automatic resolution.

---

# 11. Missing Values

Example:

IBM:

```json
{
  "benefits": null
}
```

Microsoft:

```json
{
  "benefits": ["Improves quality"]
}
```

---

Resolution:

Use available information.

Missing values are ignored.

---

# 12. Alternative Values

Canonical values do not erase alternatives.

Example:

```json
{
  "definition": {
    "canonical_value": "...",
    "alternative_values": [
      ...
    ]
  }
}
```

---

Purpose:

- Auditing
- Reviewer inspection
- Future reprocessing

---

# 13. Confidence Scoring

Each resolved field receives confidence.

---

## Formula

```text
Field Confidence =
0.35 × SourceAuthority
+
0.35 × AgreementScore
+
0.15 × ExtractionConfidence
+
0.15 × SourceRecency
```

---

## Components

### SourceAuthority

Average trust score.

Normalized:

```text
0-100
```

---

### AgreementScore

Based on semantic similarity.

Normalized:

```text
0-100
```

---

### ExtractionConfidence

Average extraction confidence.

Normalized:

```text
0-100
```

---

### SourceRecency

Based on publication/update dates.

Normalized:

```text
0-100
```

---

# 14. Topic Confidence

Topic confidence is derived from all fields.

Formula:

```text
Average(Field Confidence)
```

weighted by field importance.

---

Example:

```text
Definition
Weight = 3

Purpose
Weight = 2

Benefits
Weight = 1
```

---

# 15. Human Review Triggers

Mandatory review if:

---

## Trigger 1

```text
Single Source
```

---

## Trigger 2

```text
Field Confidence < 75
```

---

## Trigger 3

```text
Contradictory Clusters
```

---

## Trigger 4

```text
Multiple High-Authority Sources Disagree
```

Example:

```text
IBM
Microsoft
```

Conflict.

---

## Trigger 5

```text
Critical Fields Missing
```

Example:

```text
Definition = null
```

---

# 16. Canonical Knowledge Output

Example:

```json
{
  "definition": {
    "canonical_value": "SDLC is a structured process for software development.",
    "confidence": 94,
    "sources": ["IBM", "Atlassian"],
    "alternative_values": [
      {
        "value": "SDLC is a framework used to develop software systems.",
        "source": "Microsoft"
      }
    ]
  }
}
```

Stored in:

```sql
topic_knowledge
```

---

# 17. Source Update Handling

If a source changes:

```text
Source Updated
      ↓
Affected fact_extractions
      ↓
Affected topic_knowledge
      ↓
Re-run Resolution
```

No full-system reprocessing required.

---

# 18. Auditability Requirements

For every canonical field, reviewers must be able to see:

```text
Canonical Value
All Source Values
Source Trust Scores
Field Confidence
Resolution Reason
```

---

# 19. Failure Conditions

Conflict resolution fails if:

### No valid extractions

---

### All sources disagree completely

---

### Confidence calculation unavailable

---

### Required field unresolved

---

Result:

```text
Human Review Required
```

---

# 20. MVP Acceptance Criteria

The Conflict Resolution Layer is considered successful if:

1. No source-level data is lost.
2. Canonical values remain traceable to sources.
3. Conflicts are explainable.
4. Reviewers can inspect all alternatives.
5. Confidence scores correlate with reviewer approval.
6. Source updates trigger selective recomputation.
7. Contradictory information is never silently discarded.

---

## Relationship to Other Documents

### Input

Extraction Prompt Specification (EPS)

Produces:

```sql
fact_extractions
```

---

### Output

Canonical Knowledge Base

Produces:

```sql
topic_knowledge
```

---
