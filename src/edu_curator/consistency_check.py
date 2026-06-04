"""Post-generation consistency check.

Architecture Section 23:
  Input:  Canonical Knowledge + Generated Content
  Output: PASS or FLAG

Purpose: Detect hallucinations – statements in the generated content that
are not supported by the canonical knowledge.

The check is performed by a second LLM call.  The model is asked to list
any claim in the generated content that contradicts or goes beyond what the
canonical knowledge provides.

Results are stored directly on the TopicContent record:
  consistency_check_status: True (pass) | False (flag)
  consistency_check_flags:  {"flags": [...list of issue strings...]}
"""

from __future__ import annotations

import json
from typing import Any

from edu_curator.config import Settings
from edu_curator.llm import ChatResult, chat_json
from edu_curator.schemas import Source, TopicContent, TopicKnowledge

# ---------------------------------------------------------------------------
# Prompt versioning
# ---------------------------------------------------------------------------

CONSISTENCY_PROMPT_VERSION = "consistency.v1"

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

CONSISTENCY_OUTPUT_SCHEMA = {
    "verdict": "PASS or FLAG",
    "flags": [
        "list of strings – each item is a specific claim in the generated content "
        "that is not supported by or contradicts the canonical knowledge"
    ],
    "summary": "string – one sentence explaining the overall verdict",
}


def _compact_content_summary(generated_content: dict[str, Any], max_chars: int = 2500) -> str:
    """Flatten generated content into a compact readable string for LLM consumption.

    Only extracts scalar strings and the first item of list fields to keep token
    count low while preserving enough information for a meaningful hallucination check.
    Supports both flat structure and nested subtopics structure.
    """
    lines: list[str] = []
    
    if "subtopics" in generated_content and isinstance(generated_content["subtopics"], list):
        lines.append(f"topic_name: {generated_content.get('topic_name') or ''}")
        for idx, sub in enumerate(generated_content["subtopics"]):
            lines.append(f"\n--- Subtopic {idx+1}: {sub.get('subtopic_name') or ''} ---")
            for key, val in sub.items():
                if key == "subtopic_name":
                    continue
                if isinstance(val, str) and val.strip():
                    lines.append(f"  {key}: {val.strip()}")
                elif isinstance(val, list) and val:
                    items = [str(v).strip() for v in val[:3] if v]
                    if items:
                        lines.append(f"  {key}: {'; '.join(items)}")
    else:
        for key, val in generated_content.items():
            if isinstance(val, str) and val.strip():
                lines.append(f"{key}: {val.strip()}")
            elif isinstance(val, list) and val:
                # Take up to 3 items from lists
                items = [str(v).strip() for v in val[:3] if v]
                if items:
                    lines.append(f"{key}: {'; '.join(items)}")
            elif isinstance(val, dict):
                # Flatten one level of nested dict
                sub = "; ".join(f"{k}={v}" for k, v in val.items() if isinstance(v, (str, int, float)) and str(v).strip())
                if sub:
                    lines.append(f"{key}: {sub}")
                    
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... [truncated for brevity]"
    return result


def consistency_messages(
    topic_name: str,
    knowledge_summary: str,
    generated_content: dict[str, Any],
) -> list[dict[str, str]]:
    content_text = _compact_content_summary(generated_content)
    return [
        {
            "role": "system",
            "content": (
                "You are a fact-checking engine for an educational content platform. "
                "Your task is to compare generated educational content against the "
                "canonical knowledge from which it was produced.\n\n"
                "Rules:\n"
                "1. Flag any claim in the generated content that is NOT supported by "
                "the canonical knowledge.\n"
                "2. Flag any claim that CONTRADICTS the canonical knowledge.\n"
                "3. Do NOT flag claims that are reasonable pedagogical paraphrases "
                "of canonical content.\n"
                "4. Do NOT flag omissions – only flag additions or contradictions.\n"
                "5. Return verdict=PASS if no flags are found.\n"
                "6. Return verdict=FLAG if one or more issues are found.\n"
                "7. Output valid JSON only, matching the schema exactly."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic_name}\n\n"
                f"=== Canonical Knowledge ===\n{knowledge_summary}\n\n"
                f"=== Generated Content (summary) ===\n{content_text}\n\n"
                "Check whether the generated content is fully supported by the "
                "canonical knowledge. Return only this JSON:\n"
                f"{json.dumps(CONSISTENCY_OUTPUT_SCHEMA, indent=2)}"
            ),
        },
    ]


def calculate_hybrid_confidence(
    knowledge: dict[str, Any],
    sources: list[Source],
    passed: bool,
    flags_count: int,
) -> float:
    """Compute an automated confidence score (0-100) based on source trust, consensus, and verification."""
    # 1. Authority Component (40%)
    if not sources:
        auth_score = 0.0
    else:
        # Scale trust_score from 1-10 to 0-100
        auth_score = sum((s.trust_score or 5) * 10 for s in sources) / len(sources)

    # 2. Consensus Component (40%)
    total_scalar_fields = 0
    conflict_count = 0
    for _field, val in knowledge.items():
        if isinstance(val, dict):
            alt_vals = val.get("alternative_values", [])
            total_scalar_fields += 1
            if len(alt_vals) > 0:
                conflict_count += 1
        elif hasattr(val, "alternative_values"):
            alt_vals = val.alternative_values or []
            total_scalar_fields += 1
            if len(alt_vals) > 0:
                conflict_count += 1

    conflict_ratio = conflict_count / total_scalar_fields if total_scalar_fields > 0 else 0
    consensus_score = max(0.0, 100.0 - (conflict_ratio * 100.0))

    # 3. Verification Component (20%)
    if not passed:
        ver_score = 0.0
    else:
        # Deduct 20% from verification score for each flag raised
        ver_score = max(0.0, 100.0 - (flags_count * 20.0))

    final_score = (0.40 * auth_score) + (0.40 * consensus_score) + (0.20 * ver_score)
    return round(final_score, 2)


def run_consistency_check(
    settings: Settings,
    topic_content: TopicContent,
    topic_knowledge: TopicKnowledge,
    topic_name: str,
    knowledge_summary: str,
    topic_sn: int | None = None,
    sources: list[Source] | None = None,
) -> tuple[TopicContent, ChatResult]:
    """
    Run the post-generation consistency check and update the TopicContent record.

    Returns
    -------
    (updated_TopicContent, ChatResult)
      updated_TopicContent: record with consistency_check_status and flags set.
      ChatResult:           raw LLM result (used by caller for token logging).
    """

    messages = consistency_messages(
        topic_name=topic_name,
        knowledge_summary=knowledge_summary,
        generated_content=topic_content.content_json,
    )

    result = chat_json(
        settings=settings,
        messages=messages,
        model=settings.generation_model,
        stage="consistency",
        topic_sn=topic_sn,
    )

    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError as exc:
        # If the LLM fails to return valid JSON, treat as an unknown flag
        payload = {
            "verdict": "FLAG",
            "flags": [f"Consistency check model returned invalid JSON: {exc}"],
            "summary": "Consistency check could not be completed.",
        }

    verdict = str(payload.get("verdict", "FLAG")).upper().strip()
    passed = verdict == "PASS"
    flags_count = len(payload.get("flags", []))

    if sources is None:
        confidence_score = topic_content.confidence_score or 50.0
    else:
        active_source_ids = set(topic_knowledge.sources_used)
        active_sources = [s for s in sources if s.id in active_source_ids]
        confidence_score = calculate_hybrid_confidence(
            topic_knowledge.knowledge, active_sources, passed, flags_count
        )

    # Use model_copy to update immutable fields cleanly
    updated = topic_content.model_copy(
        update={
            "consistency_check_status": passed,
            "consistency_check_flags": payload,
            "confidence_score": confidence_score,
        }
    )
    return updated, result
