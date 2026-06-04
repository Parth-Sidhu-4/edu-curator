# Specification Document 1

# Extraction Prompt Specification (EPS)

**Version:** 1.0
**Status:** Required Before Implementation
**Priority:** Critical

This document defines exactly how LLMs extract structured knowledge from source content into the `fact_extractions` table defined in the architecture.

---

# 1. Purpose

The extraction layer is responsible for transforming source material into structured, source-traceable knowledge.

Input:

```text
Topic
+
Topic Type
+
Source Chunks
```

Output:

```json
Structured JSON
```

which is later validated and stored in:

```sql
fact_extractions
```

The extraction layer is the foundation of the knowledge base.

Incorrect extraction propagates errors throughout the system.

---

# 2. Design Principles

## Principle 1: Extract, Don't Generate

The model must only extract information explicitly present in the source.

Allowed:

```text
Source:
SDLC is a structured process used to develop software.

Output:
definition = "SDLC is a structured process used to develop software."
```

---

Not Allowed:

```text
Source:
SDLC is a process.

Output:
benefits = [
  "Improves quality",
  "Reduces risk"
]
```

if benefits are not mentioned.

---

## Principle 2: Missing Information Must Remain Missing

If a field is unsupported:

Correct:

```json
{
  "benefits": null
}
```

Incorrect:

```json
{
  "benefits": ["Improves productivity"]
}
```

---

## Principle 3: Preserve Source Wording

Extraction should preserve meaning.

Do not heavily summarize.

Do not reinterpret.

Do not simplify.

The generation stage handles educational rewriting.

---

## Principle 4: Every Extraction Must Be Traceable

Every extracted value must be linked to:

```text
Source
Chunk
Topic
Prompt Version
Model
```

---

# 3. Common Prompt Structure

Every extraction prompt follows the same structure.

---

## System Prompt

```text
You are an information extraction engine.

Your task is to extract structured information from the provided source content.

Rules:

1. Extract only information explicitly stated.
2. Never infer missing information.
3. Never use external knowledge.
4. If information is not present, return null.
5. Output valid JSON only.
6. Follow the schema exactly.
7. Do not add fields.
8. Do not remove fields.
```

---

## User Prompt Template

```text
Topic:
{topic_name}

Topic Type:
{topic_type}

Schema:
{schema_definition}

Source:
{source_name}

Chunk:
{chunk_text}

Extract information according to the schema.

Return valid JSON only.
```

---

# 4. Concept Topic Extraction

Examples:

```text
SDLC
Agile
DevOps
```

---

## Schema

```json
{
  "definition": null,
  "purpose": null,
  "key_properties": [],
  "benefits": [],
  "limitations": [],
  "common_misconceptions": [],
  "related_topics": [],
  "faq": []
}
```

---

## Extraction Rules

### Definition

Must answer:

```text
What is it?
```

Only extract if explicitly stated.

---

### Purpose

Must answer:

```text
Why does it exist?
```

---

### Benefits

Only include benefits explicitly mentioned.

---

### Limitations

Only include limitations explicitly mentioned.

---

### Related Topics

Only include if source explicitly references them.

---

### FAQ (Frequently Asked Questions)

Generate 3-5 QA entries grounded strictly in the source's canonical facts.
Each FAQ entry must follow the format:
```json
{
  "question": "What is ...?",
  "answer": "..."
}
```

---

# 5. Command Topic Extraction

Examples:

```text
git clone
git commit
docker run
```

---

## Schema

```json
{
  "syntax": null,
  "parameters": [],
  "examples": [],
  "expected_output": null,
  "common_errors": []
}
```

---

## Extraction Rules

### Syntax

Must contain official command syntax.

Example:

```text
git clone <repository-url>
```

---

### Parameters

Format:

```json
{
  "name": "--depth",
  "description": "Create shallow clone",
  "required": false
}
```

---

### Examples

Format:

```json
{
  "command": "git clone repo_url",
  "description": "Clone repository"
}
```

---

# 6. Tool Topic Extraction

Examples:

```text
Docker
Jenkins
GitHub
```

---

## Schema

```json
{
  "overview": null,
  "features": [],
  "use_cases": [],
  "advantages": [],
  "limitations": []
}
```

---

## Rules

Features must be explicitly listed or clearly described.

Avoid generic marketing language.

---

# 7. Architecture Topic Extraction

Examples:

```text
Docker Architecture
Kubernetes Architecture
```

---

## Schema

```json
{
  "overview": null,
  "components": [],
  "interactions": [],
  "tradeoffs": []
}
```

---

## Components

Extract named architecture elements.

Example:

```text
API Server
Scheduler
Controller Manager
```

---

## Interactions

Capture relationships.

Example:

```text
Scheduler communicates with API Server.
```

---

# 8. Process Topic Extraction

Examples:

```text
CI/CD Pipeline
Deployment Workflow
```

---

## Schema

```json
{
  "overview": null,
  "steps": [],
  "inputs": [],
  "outputs": [],
  "benefits": [],
  "limitations": []
}
```

---

## Steps

Maintain order.

Example:

```json
["Build", "Test", "Deploy"]
```

---

# 9. Output Validation Rules

Before storing:

### Rule 1

Valid JSON required.

---

### Rule 2

Schema must match exactly.

---

### Rule 3

No extra fields allowed.

---

### Rule 4

Required arrays must remain arrays.

Incorrect:

```json
{
  "benefits": "Improves quality"
}
```

Correct:

```json
{
  "benefits": ["Improves quality"]
}
```

---

# 10. Confidence Estimation

Extraction model should estimate confidence.

Range:

```text
0.0 – 1.0
```

Example:

```json
{
  "field": "definition",
  "value": "...",
  "confidence": 0.92
}
```

---

# 11. Failure Conditions

Extraction must fail if:

### Invalid JSON

---

### Missing Required Fields

---

### Hallucinated Information Detected

---

### Schema Violation

---

Result:

```text
Retry
```

If retries exceed threshold:

```text
Store in extraction_errors
```

---

# 12. Prompt Versioning

Every extraction run must record:

```text
prompt_version
schema_version
model_name
model_version
```

Example:

```json
{
  "prompt_version": "1.0",
  "schema_version": "1.0",
  "model": "gemini-2.5-pro"
}
```

---

# 13. MVP Acceptance Criteria

The extraction system is considered successful if:

1. Same source produces consistent extraction across runs.
2. JSON validates successfully >95% of the time.
3. Hallucinated fields are rare (<2%).
4. Human reviewers agree with extracted values in >90% of samples.
5. Extracted data can be directly inserted into `fact_extractions`.
6. Content generation can operate without reading raw source chunks.

---
