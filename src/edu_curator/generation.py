"""Content generation from canonical topic knowledge.

Architecture rule (Section 22):
  Generate ONLY from canonical knowledge.
  Never generate from raw source chunks.

The LLM receives a clean, structured summary of the resolved canonical
knowledge (canonical values + merged collection items) and is asked to
write educational content.  Raw chunk text is deliberately withheld.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from edu_curator.config import Settings
from edu_curator.ids import new_id
from edu_curator.llm import ChatResult, chat_json
from edu_curator.schemas import (
    CanonicalField,
    ReviewStatus,
    TopicContent,
    TopicKnowledge,
)

# ---------------------------------------------------------------------------
# Prompt versioning
# ---------------------------------------------------------------------------

GENERATION_PROMPT_VERSION = "gen.concept.v1"
SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Helpers – distil canonical knowledge into a readable summary for the prompt
# ---------------------------------------------------------------------------


def _scalar_summary(field_name: str, cf: CanonicalField) -> str:
    """Return a single-line summary of a resolved scalar field."""
    if cf.status == "missing" or cf.canonical_value is None:
        return f"  {field_name}: (not available)"
    return f"  {field_name}: {cf.canonical_value}"


def _collection_summary(field_name: str, items: list[dict[str, Any]]) -> str:
    """Return a bullet-list summary of a merged collection field."""
    if not items:
        return f"  {field_name}: (none provided)"
    seen = set()
    deduped = []
    for item in items:
        val = item.get("value", item) if isinstance(item, dict) else item
        if val is None:
            continue
        val_str = str(val).strip()
        val_lower = val_str.lower()
        if val_lower not in seen:
            seen.add(val_lower)
            deduped.append(val_str)
    deduped = deduped[:15]
    bullets = "\n".join(f"    - {d}" for d in deduped)
    return f"  {field_name}:\n{bullets}"


def canonical_knowledge_summary(knowledge: dict[str, Any]) -> str:
    """
    Convert the structured knowledge dict into a compact, human-readable
    block that is safe to embed in a generation prompt.

    Each entry is either a CanonicalField (scalar) or a list of dicts
    (collection).  We deliberately omit raw source IDs, alternative values
    and resolution metadata so the model cannot reference them directly.
    """
    from collections import defaultdict
    # Check if there are keys starting with digit + "."
    has_subtopic_keys = any(
        isinstance(k, str) and "." in k and k.split(".")[0].isdigit() for k in knowledge
    )

    if has_subtopic_keys:
        # Group by subtopic index
        by_subtopic = defaultdict(dict)
        flat_fields = {}
        for k, v in knowledge.items():
            if isinstance(k, str) and "." in k:
                parts = k.split(".", 1)
                if parts[0].isdigit():
                    by_subtopic[int(parts[0])][parts[1]] = v
                    continue
            flat_fields[k] = v

        lines = ["Canonical Knowledge Summary (Subtopic-wise):"]
        for sub_idx in sorted(by_subtopic.keys()):
            lines.append(f"\nSubtopic {sub_idx + 1}:")
            sub_k = by_subtopic[sub_idx]
            for field_name, value in sorted(sub_k.items()):
                if isinstance(value, dict) and "canonical_value" in value:
                    cf = CanonicalField.model_validate(value)
                    lines.append(_scalar_summary(field_name, cf))
                elif isinstance(value, list):
                    lines.append(_collection_summary(field_name, value))
                elif value is None:
                    lines.append(f"  {field_name}: (not available)")
                else:
                    lines.append(f"  {field_name}: {value}")

        if flat_fields:
            # Skip _review_triggers as it is internal metadata and should not go to prompt
            filtered_flat = {k: v for k, v in flat_fields.items() if not k.startswith("_")}
            if filtered_flat:
                lines.append("\nGeneral Fields:")
                for field_name, value in sorted(filtered_flat.items()):
                    if isinstance(value, dict) and "canonical_value" in value:
                        cf = CanonicalField.model_validate(value)
                        lines.append(_scalar_summary(field_name, cf))
                    elif isinstance(value, list):
                        lines.append(_collection_summary(field_name, value))
                    elif value is None:
                        lines.append(f"  {field_name}: (not available)")
                    else:
                        lines.append(f"  {field_name}: {value}")

        return "\n".join(lines)

    lines: list[str] = ["Canonical Knowledge Summary:"]

    for field_name, value in sorted(knowledge.items()):
        if field_name.startswith("_"):
            continue
        if isinstance(value, dict) and "canonical_value" in value:
            # Scalar field stored as a CanonicalField-shaped dict
            cf = CanonicalField.model_validate(value)
            lines.append(_scalar_summary(field_name, cf))
        elif isinstance(value, list):
            lines.append(_collection_summary(field_name, value))
        elif value is None:
            lines.append(f"  {field_name}: (not available)")
        else:
            lines.append(f"  {field_name}: {value}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output schema for the generation model
# ---------------------------------------------------------------------------

GENERATION_OUTPUT_SCHEMA = {
    "topic_name": "string - the overall topic name being explained",
    "subtopics": [
        {
            "subtopic_name": "string - the specific subtopic name",
            "summary": "string - A comprehensive, detailed plain-language summary of this specific subtopic. Must run to at least 2-3 paragraphs (minimum 150 words total).",
            "definition": "string - An in-depth, rigorous educational definition of this specific subtopic. Must run to at least 2-3 paragraphs (minimum 200 words total). Use standard LaTeX math delimiters (single '$' for inline, double '$$' for blocks) to format any equations, formulas, mathematical models, metrics, or technical notations. Explain all variables and equations in detail.",
            "purpose": "string - Detailed explanation of why this subtopic exists, what problems it solves, and its real-world utility in software engineering/DevOps. Must run to at least 2-3 paragraphs (minimum 150 words total).",
            "key_properties": [
                "list of strings - Detailed descriptions of key characteristics of this subtopic. Each list item must be a detailed sentence or full paragraph (minimum 50 words per item) explaining the property in depth, rather than a short phrase."
            ],
            "benefits": [
                "list of strings - Concrete benefits of this subtopic. Each list item must be a detailed sentence or full paragraph (minimum 50 words per item) explaining the benefit in depth with context."
            ],
            "limitations": [
                "list of strings - Limitations, caveats, or trade-offs of this subtopic. Each list item must be a detailed sentence or full paragraph (minimum 50 words per item) explaining the limitation in depth with context."
            ],
            "common_misconceptions": [
                "list of strings - Misconceptions or common pitfalls of this subtopic. Each list item must be a detailed sentence or full paragraph (minimum 50 words per item) explaining the misconception in depth."
            ],
            "related_topics": [
                "list of strings - Related concepts of this subtopic. Each item should be a detailed sentence explaining the connection (minimum 30 words per item)."
            ],
        }
    ],
    "faq": [
        {
            "question": "string - A key question a learner might ask about this topic as a whole. Must be grounded in the Canonical Knowledge Summary.",
            "answer": "string - A concise, helpful, and pedagogically sound answer. Must run to at least 1-2 paragraphs (minimum 80 words total). Ground this strictly in facts from the Canonical Knowledge Summary. Use standard LaTeX math delimiters or Markdown backticks as appropriate."
        }
    ],
}

# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------


def generation_messages(
    topic_name: str,
    topic_type: str,
    knowledge_summary: str,
    sources_label: list[str],
    subtopics: list[str],
) -> list[dict[str, str]]:
    sources_str = ", ".join(sources_label) if sources_label else "trusted sources"
    schema_str = json.dumps(GENERATION_OUTPUT_SCHEMA, indent=2)
    subtopics_bulleted = "\n".join(f"- {s}" for s in subtopics)
    return [
        {
            "role": "system",
            "content": (
                "You are an educational content writer. "
                "Your task is to write clear, accurate, and detailed educational content for learners. "
                "\n\nRules:"
                "\n1. Use ONLY the information provided in the Canonical Knowledge Summary."
                "\n2. Do NOT introduce any external facts, examples, or details not present in the summary."
                "\n3. Do NOT mention source names, URLs, or internal IDs."
                "\n4. Write in plain, pedagogically appropriate language. Explain complex ideas clearly."
                "\n5. Write in an organic, humanistic style typical of professional technical authors (such as O'Reilly, Addisson-Wesley, or Pragmatic Bookshelf). Avoid robotic AI tropes, such as repetitive transition phrases ('furthermore', 'moreover', 'indeed', 'it is important to note'), generic opening sentences, and excessive formatting."
                "\n6. Do NOT use em-dashes ('—') to join clauses or construct sentences. Use standard punctuation (periods, commas, colons, or parentheses) instead."
                "\n7. Output must be valid JSON matching the provided schema exactly."
                "\n8. If a field has no information, return null for strings or [] for arrays."
                "\n9. Do not add fields beyond those in the schema."
                "\n10. Avoid short summaries or brief bullet points. Expand each section into a detailed, comprehensive textbook-style explanation. For every bullet point/list item, write a full explanatory paragraph (minimum 50 words)."
                "\n11. Format all mathematical equations, variables, and formulas using clean LaTeX syntax (enclose inline equations in '$' like '$E=mc^2$' and block equations in '$$' like '$$E=mc^2$$'). Explain every variable in the equations clearly."
                "\n12. Format all code snippets, terminal commands, Git commands, variables, and file paths using standard Markdown backticks (enclose inline commands/variables/paths in single backticks like `git commit`, and block code snippets in triple backticks with a language specifier like ```bash\\n...\\n```)."
                "\n13. Generate 3 to 5 key FAQs under the 'faq' list, capturing top-level frequently asked questions about the topic as a whole. Each FAQ must consist of a 'question' and a detailed 'answer' (minimum 80 words per answer) strictly grounded in the Canonical Knowledge Summary."
                f"\n\nOutput schema (return only this JSON object):\n{schema_str}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic_name}\n"
                f"Topic Type: {topic_type}\n\n"
                f"This topic is divided into the following subtopics:\n{subtopics_bulleted}\n\n"
                "Your output JSON must contain exactly one entry in the 'subtopics' list for each of the subtopics listed above, in the exact same order.\n"
                "Make sure that for each sub-topic, the 'subtopic_name' field matches the name above exactly.\n\n"
                f"{knowledge_summary}\n\n"
                f"Synthesised from: {sources_str}\n\n"
                "Write educational content for a student learning this topic. "
                "Base every statement strictly on the Canonical Knowledge Summary above."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Validation of generated output
# ---------------------------------------------------------------------------

REQUIRED_SUBTOPIC_STRING_FIELDS = {"subtopic_name", "summary", "definition", "purpose"}
REQUIRED_SUBTOPIC_ARRAY_FIELDS = {
    "key_properties",
    "benefits",
    "limitations",
    "common_misconceptions",
    "related_topics",
}
ALL_SUBTOPIC_FIELDS = REQUIRED_SUBTOPIC_STRING_FIELDS | REQUIRED_SUBTOPIC_ARRAY_FIELDS


def validate_generated_content(payload: dict[str, Any], expected_subtopics: list[str] | None = None) -> list[str]:
    """
    Return a list of validation issue descriptions.
    Empty list means the payload is acceptable.
    """
    issues: list[str] = []
    if "topic_name" not in payload:
        issues.append("missing required field: topic_name")
    elif payload["topic_name"] is not None and not isinstance(payload["topic_name"], str):
        issues.append("field 'topic_name' must be a string or null")

    if "subtopics" not in payload:
        issues.append("missing required field: subtopics")
    elif not isinstance(payload["subtopics"], list):
        issues.append("field 'subtopics' must be a list")
    else:
        for idx, sub in enumerate(payload["subtopics"]):
            if not isinstance(sub, dict):
                issues.append(f"subtopic at index {idx} must be a JSON object")
                continue
            for field in REQUIRED_SUBTOPIC_STRING_FIELDS:
                if field not in sub:
                    issues.append(f"subtopic {idx} missing required field: {field}")
                elif sub[field] is not None and not isinstance(sub[field], str):
                    issues.append(f"subtopic {idx} field '{field}' must be a string or null")
            for field in REQUIRED_SUBTOPIC_ARRAY_FIELDS:
                if field not in sub:
                    issues.append(f"subtopic {idx} missing required field: {field}")
                elif not isinstance(sub[field], list):
                    issues.append(f"subtopic {idx} field '{field}' must be a list")
            extra = set(sub.keys()) - ALL_SUBTOPIC_FIELDS
            if extra:
                issues.append(f"subtopic {idx} unexpected fields: {sorted(extra)}")

        if expected_subtopics:
            import re
            def clean_name(name: str) -> str:
                # Remove leading numbers, dots and spaces, e.g. "1.11 Pull Requests" -> "pull requests"
                cleaned = re.sub(r'^\d+(\.\d+)*\s*', '', name)
                return cleaned.strip().lower()

            actual_subtopics = payload["subtopics"]
            if len(actual_subtopics) != len(expected_subtopics):
                issues.append(
                    f"subtopic count mismatch: expected {len(expected_subtopics)} subtopics ({expected_subtopics}), "
                    f"got {len(actual_subtopics)} ({[s.get('subtopic_name') for s in actual_subtopics if isinstance(s, dict)]})"
                )
            else:
                for idx, expected in enumerate(expected_subtopics):
                    actual_sub = actual_subtopics[idx]
                    if isinstance(actual_sub, dict):
                        actual_name = actual_sub.get("subtopic_name") or ""
                        if clean_name(actual_name) != clean_name(expected):
                            issues.append(
                                f"subtopic name mismatch at index {idx}: expected '{expected}', "
                                f"got '{actual_name}'"
                            )

    if "faq" in payload:
        if not isinstance(payload["faq"], list):
            issues.append("field 'faq' must be a list")
        else:
            for idx, faq_item in enumerate(payload["faq"]):
                if not isinstance(faq_item, dict):
                    issues.append(f"faq at index {idx} must be a JSON object")
                    continue
                for ffield in ["question", "answer"]:
                    if ffield not in faq_item:
                        issues.append(f"faq item {idx} missing required field: {ffield}")
                    elif faq_item[ffield] is not None and not isinstance(faq_item[ffield], str):
                        issues.append(f"faq item {idx} field '{ffield}' must be a string or null")
                fextra = set(faq_item.keys()) - {"question", "answer"}
                if fextra:
                    issues.append(f"faq item {idx} unexpected fields: {sorted(fextra)}")

    extra = set(payload.keys()) - {"topic_name", "subtopics", "faq"}
    if extra:
        issues.append(f"unexpected top-level fields: {sorted(extra)}")
    return issues


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_topic_content(
    settings: Settings,
    topic_knowledge: TopicKnowledge,
    topic_name: str,
    topic_type: str,
    source_labels: list[str],
    topic_sn: int | None = None,
) -> tuple[TopicContent, ChatResult]:
    """
    Generate educational content from canonical topic knowledge.

    Returns
    -------
    (TopicContent, ChatResult)
      TopicContent: the generated record (review_status=pending).
      ChatResult:   raw LLM result (used by caller for token logging).

    Raises RuntimeError on LLM failure or repeated validation failure.
    """

    subtopics = [s.strip() for s in topic_name.split(",") if s.strip()]
    knowledge_summary = canonical_knowledge_summary(topic_knowledge.knowledge)
    messages = generation_messages(
        topic_name=topic_name,
        topic_type=topic_type,
        knowledge_summary=knowledge_summary,
        sources_label=source_labels,
        subtopics=subtopics,
    )

    result = chat_json(
        settings=settings,
        messages=messages,
        model=settings.generation_model,
        stage="generate",
        topic_sn=topic_sn,
    )

    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Generation model returned invalid JSON: {exc}\nRaw output: {result.content[:500]}"
        ) from exc

    issues = validate_generated_content(payload, expected_subtopics=subtopics)
    if issues:
        if result.cached:
            logger.warning("Cached generation result failed schema validation. Retrying with fresh LLM call...")
            result = chat_json(
                settings=settings,
                messages=messages,
                model=settings.generation_model,
                stage="generate",
                topic_sn=topic_sn,
                bypass_cache=True,
            )
            try:
                payload = json.loads(result.content)
                issues = validate_generated_content(payload, expected_subtopics=subtopics)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Generation model returned invalid JSON on retry: {exc}\nRaw output: {result.content[:500]}"
                ) from exc

        if issues:
            raise RuntimeError(
                "Generated content failed schema validation:\n"
                + "\n".join(f"  - {i}" for i in issues)
                + f"\nRaw output: {result.content[:500]}"
            )

    now = datetime.now(UTC)
    topic_content = TopicContent(
        id=new_id(),
        topic_id=topic_knowledge.topic_id,
        content_json=payload,
        schema_version=SCHEMA_VERSION,
        generation_model=settings.generation_model,
        sources_used=list(topic_knowledge.sources_used),
        confidence_score=topic_knowledge.confidence,
        # Consistency check fields are filled by a separate step
        consistency_check_status=None,
        consistency_check_flags=None,
        review_status=ReviewStatus.pending,
        reviewer_id=None,
        reviewed_at=None,
        review_notes=None,
        published_at=None,
        created_at=now,
    )
    return topic_content, result
