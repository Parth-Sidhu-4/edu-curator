"""Self-correcting RAG curation feedback loop module.

Refines educational content by feeding evaluation criticisms back to the generator LLM.
Protects faithfulness via strict constraints and a rollback guard.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edu_curator.config import Settings
from edu_curator.evaluation import evaluate_topic
from edu_curator.generation import (
    GENERATION_OUTPUT_SCHEMA,
    canonical_knowledge_summary,
    validate_generated_content,
)
from edu_curator.ids import new_id
from edu_curator.llm import chat_json
from edu_curator.schemas import (
    ReviewStatus,
    SyllabusTopic,
    TopicContent,
    TopicKnowledge,
)


def revision_messages(
    topic_name: str,
    topic_type: str,
    knowledge_summary: str,
    previous_content: dict[str, Any],
    faithfulness_score: float,
    faithfulness_criticism: str,
    completeness_score: float,
    completeness_criticism: str,
) -> list[dict[str, str]]:
    """Build the message sequence instructing the LLM to revise the curriculum JSON."""
    schema_str = json.dumps(GENERATION_OUTPUT_SCHEMA, indent=2)
    previous_content_str = json.dumps(previous_content, indent=2)
    subtopics = [s.strip() for s in topic_name.split(",") if s.strip()]
    subtopics_bulleted = "\n".join(f"- {s}" for s in subtopics)

    system_content = (
        "You are an expert technical editor. "
        "Your task is to revise a previously generated curriculum JSON payload to improve its quality "
        "based on criticisms from a RAG auditor.\n\n"
        "Rules:\n"
        "1. Use ONLY the information provided in the Canonical Knowledge Summary. "
        "Do NOT introduce any external facts, examples, or details not present in the summary.\n"
        "2. Address the criticisms directly:\n"
        "   - If Completeness is low: add the missing details from the Canonical Knowledge Summary.\n"
        "   - If Faithfulness is low: correct or remove any statements that contradict or are not supported by the Canonical Knowledge Summary.\n"
        "3. Keep all other generated sections intact. Maintain the high-quality, textbook-style detailed paragraphs (minimum 50 words per item).\n"
        "4. CRITICAL: Faithfulness to the Canonical Knowledge Summary is the highest priority. Under no circumstances "
        "should you add speculative details, external explanations, or hallucinated facts, even if the auditor criticizes "
        "the content for missing details. If a detail requested by the critic is not in the Canonical Knowledge Summary, "
        "you must ignore that criticism and keep the facts accurate.\n"
        "5. Do NOT use em-dashes ('—') to join clauses or construct sentences.\n"
        "6. Output MUST be valid JSON matching the schema exactly. No markdown wrappers or additional text.\n\n"
        f"Output schema:\n{schema_str}"
    )

    user_content = (
        f"Topic: {topic_name}\n"
        f"Topic Type: {topic_type}\n\n"
        f"This topic is divided into the following subtopics:\n{subtopics_bulleted}\n\n"
        "Your output JSON must contain exactly one entry in the 'subtopics' list for each of the subtopics listed above, in the exact same order.\n"
        "Make sure that for each sub-topic, the 'subtopic_name' field matches the name above exactly.\n\n"
        f"=== CANONICAL KNOWLEDGE SUMMARY ===\n{knowledge_summary}\n\n"
        f"=== PREVIOUS GENERATED CURRICULUM ===\n{previous_content_str}\n\n"
        f"=== AUDITOR CRITICISMS ===\n"
        f"- Faithfulness Score: {faithfulness_score}/10\n"
        f"  Feedback: {faithfulness_criticism}\n"
        f"- Completeness Score: {completeness_score}/10\n"
        f"  Feedback: {completeness_criticism}\n\n"
        "Generate the revised JSON payload resolving the auditor criticisms while strictly maintaining faithfulness to the canonical summary."
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def refine_curriculum(
    settings: Settings,
    topic_knowledge: TopicKnowledge,
    topic: SyllabusTopic,
    source_labels: list[str],
    max_iterations: int = 3,
    target_threshold: float = 9.0,
) -> tuple[TopicContent, dict[str, Any]]:
    """Execute the curation self-correction loop.

    Generates initial content, runs evaluations, and iteratively revises the content
    if scores are below target_threshold. If a revision lowers faithfulness,
    the loop halts and rolls back to the previous best content.

    Returns
    -------
    (TopicContent, dict)
      TopicContent: the finalized generated content record.
      dict: the final evaluation result dictionary (saved to DB).
    """
    from edu_curator.generation import generate_topic_content
    from edu_curator.token_logger import log_usage

    logger = logging.getLogger(__name__)
    logger.info(f"Starting self-correction loop for '{topic.topic_name}' (max iterations: {max_iterations})")

    # --- Iteration 1: Initial Generation ---
    logger.info("Iteration 1: Generating initial curriculum...")
    content, initial_gen_result = generate_topic_content(
        settings=settings,
        topic_knowledge=topic_knowledge,
        topic_name=topic.topic_name,
        topic_type=topic.topic_type,
        source_labels=source_labels,
        topic_sn=None,
    )
    # Log initial token usage
    try:
        ROOT = Path(__file__).resolve().parents[2]
        log_usage(
            ROOT / "data" / "logs",
            initial_gen_result,
            stage="generate",
            model=settings.generation_model,
            topic_sn=None
        )
    except Exception as e:
        logger.error(f"Failed to log initial token usage: {e}")

    # Evaluate initial generation
    eval_result = evaluate_topic(settings, topic, content, topic_knowledge)
    if "error" in eval_result:
        logger.error(f"Evaluation error on initial pass: {eval_result['error']}. Exiting loop.")
        return content, eval_result

    f_score = eval_result.get("faithfulness_score", 0)
    c_score = eval_result.get("completeness_score", 0)
    logger.info(f"Initial scores: Faithfulness = {f_score}/10, Completeness = {c_score}/10")

    # Define score weight: faithfulness is primary (x10), completeness is secondary
    best_score = f_score * 10 + c_score
    best_content = content
    best_eval = eval_result

    if f_score >= target_threshold and c_score >= target_threshold:
        logger.info("Initial generation meets quality thresholds. Refinement complete.")
        return best_content, best_eval

    # --- Iteration 2+ : Critique & Correction ---
    knowledge_summary = canonical_knowledge_summary(topic_knowledge.knowledge)

    for i in range(2, max_iterations + 1):
        logger.info(f"Iteration {i}: Refining content based on criticisms...")

        messages = revision_messages(
            topic_name=topic.topic_name,
            topic_type=topic.topic_type,
            knowledge_summary=knowledge_summary,
            previous_content=best_content.content_json,
            faithfulness_score=best_eval.get("faithfulness_score", 0),
            faithfulness_criticism=best_eval.get("faithfulness_reason", ""),
            completeness_score=best_eval.get("completeness_score", 0),
            completeness_criticism=best_eval.get("completeness_reason", ""),
        )

        # Call generator LLM for revision
        result = chat_json(
            settings=settings,
            messages=messages,
            model=settings.generation_model,
            stage="generate",
            topic_sn=None,
        )

        # Log revision token usage
        try:
            ROOT = Path(__file__).resolve().parents[2]
            log_usage(
                ROOT / "data" / "logs",
                result,
                stage="generate_revision",
                model=settings.generation_model,
                topic_sn=None
            )
        except Exception as e:
            logger.error(f"Failed to log revision token usage: {e}")

        try:
            payload = json.loads(result.content)
        except json.JSONDecodeError as exc:
            logger.warning(f"LLM returned invalid JSON: {exc}. Reverting to previous best.")
            break

        expected_subs = [s.strip() for s in topic.topic_name.split(",") if s.strip()]
        issues = validate_generated_content(payload, expected_subtopics=expected_subs)
        if issues:
            if result.cached:
                logger.warning("Cached revision result failed schema validation. Retrying with fresh LLM call...")
                result = chat_json(
                    settings=settings,
                    messages=messages,
                    model=settings.generation_model,
                    stage="generate",
                    topic_sn=None,
                    bypass_cache=True,
                )
                try:
                    payload = json.loads(result.content)
                    issues = validate_generated_content(payload, expected_subtopics=expected_subs)
                except json.JSONDecodeError as exc:
                    logger.warning(f"LLM returned invalid JSON on fresh retry: {exc}. Reverting.")
                    break
            
            if issues:
                logger.warning(f"Validation errors: {issues}. Reverting to previous best.")
                break

        # Construct temporary content record
        now = datetime.now(UTC)
        temp_content = TopicContent(
            id=new_id(),
            topic_id=topic_knowledge.topic_id,
            content_json=payload,
            schema_version="1.0",
            generation_model=settings.generation_model,
            sources_used=list(topic_knowledge.sources_used),
            confidence_score=topic_knowledge.confidence,
            consistency_check_status=None,
            consistency_check_flags=None,
            review_status=ReviewStatus.pending,
            reviewer_id=None,
            reviewed_at=None,
            review_notes=None,
            published_at=None,
            created_at=now,
        )

        # Evaluate revised content
        new_eval = evaluate_topic(settings, topic, temp_content, topic_knowledge)
        if "error" in new_eval:
            logger.warning(f"Revision evaluation failed: {new_eval['error']}. Reverting.")
            break

        new_f = new_eval.get("faithfulness_score", 0)
        new_c = new_eval.get("completeness_score", 0)
        logger.info(f"Revision scores: Faithfulness = {new_f}/10, Completeness = {new_c}/10")

        # Rollback Guard: If faithfulness drops, discard revision and stop
        old_f = best_eval.get("faithfulness_score", 0)
        if new_f < old_f:
            logger.warning(f"Rollback triggered: Faithfulness decreased from {old_f}/10 to {new_f}/10. Reverting.")
            break

        new_score = new_f * 10 + new_c
        if new_score > best_score:
            best_score = new_score
            best_content = temp_content
            best_eval = new_eval

        # Stop early if threshold achieved
        if new_f >= target_threshold and new_c >= target_threshold:
            logger.info(f"Achieved target thresholds (F={new_f}, C={new_c}). Stopping refinement loop.")
            break

    logger.info(f"Curation refinement finalized. Final scores: F={best_eval.get('faithfulness_score')}, C={best_eval.get('completeness_score')}")
    return best_content, best_eval
