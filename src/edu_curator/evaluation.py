from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from edu_curator.config import Settings
from edu_curator.llm import chat_json
from edu_curator.schemas import SyllabusTopic, TopicContent, TopicKnowledge

EVALUATION_SCHEMA = {
    "faithfulness_score": "int (1-10)",
    "faithfulness_reason": "str",
    "completeness_score": "int (1-10)",
    "completeness_reason": "str",
}


def _parse_score(val: Any) -> float:
    """Parse a score value into a float, handling strings like '9/10', '9.5', or '9'."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if "/" in val_str:
        try:
            parts = val_str.split("/")
            num = float(parts[0].strip())
            den = float(parts[1].strip())
            if den != 0:
                if den == 10.0:
                    return num
                return (num / den) * 10.0
        except Exception:
            pass
    try:
        return float(val_str)
    except Exception:
        return 0.0


def evaluate_topic(
    settings: Settings, topic: SyllabusTopic, content: TopicContent, knowledge: TopicKnowledge
) -> dict:
    """Evaluates generated content using LLM-as-a-Judge."""

    from edu_curator.generation import canonical_knowledge_summary
    reference_facts = canonical_knowledge_summary(knowledge.knowledge)
    generated_json = content.content_json
    
    has_subtopics = isinstance(generated_json, dict) and "subtopics" in generated_json and isinstance(generated_json["subtopics"], list)

    if has_subtopics:
        schema = {
            "faithfulness_score": "float (1-10) - Overall faithfulness score, representing the average or minimum of the subtopics' scores.",
            "faithfulness_reason": "string - Detailed summary reasoning explaining the overall faithfulness, including highlights from specific subtopics.",
            "completeness_score": "float (1-10) - Overall completeness score, representing the average or minimum of the subtopics' scores.",
            "completeness_reason": "string - Detailed summary reasoning explaining the overall completeness, including highlights from specific subtopics.",
            "subtopics": [
                {
                    "subtopic_name": "string - Name of the subtopic being evaluated.",
                    "faithfulness_score": "int (1-10) - Faithfulness score for this specific subtopic. Grade how well this subtopic adheres strictly to the reference facts and avoids hallucinated information.",
                    "faithfulness_reason": "string - Detailed reasoning for the faithfulness score of this subtopic.",
                    "completeness_score": "int (1-10) - Completeness score for this specific subtopic. Grade how thoroughly this subtopic covers all relevant aspects from reference facts (definitions, properties, benefits, limitations, etc.).",
                    "completeness_reason": "string - Detailed reasoning for the completeness score of this subtopic."
                }
            ]
        }
        
        system_content = (
            "You are an expert curriculum auditor and RAG evaluator. Your job is to grade the Generated Curriculum against the strict Reference Facts.\n\n"
            "The curriculum is divided into multiple subtopics. You must evaluate each subtopic individually:\n"
            "1. Compare each subtopic's content in the Generated Curriculum against the Reference Facts relevant to that subtopic.\n"
            "2. Grade Faithfulness (1 to 10) for each subtopic: does it contain hallucinations or information not supported by the Reference Facts? (10 = perfect adherence, 1 = total hallucination)\n"
            "3. Grade Completeness (1 to 10) for each subtopic: does it completely and accurately cover all relevant definitions, purposes, properties, benefits, and limitations mentioned in the Reference Facts for this specific subtopic? (10 = fully complete, 1 = missed major facts)\n\n"
            f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        )
    else:
        system_content = (
            "You are an expert curriculum auditor and RAG evaluator. Your job is to grade the Generated Curriculum against the strict Reference Facts.\n\n"
            "Score the curriculum from 1 to 10 on two metrics:\n"
            "1. Faithfulness: Does the generated text contradict the reference facts or hallucinate external information? (10 = perfect adherence, 1 = total hallucination)\n"
            "2. Completeness: Does the generated text cover the definition, properties, and benefits listed in the reference facts? (10 = fully complete, 1 = missed major facts)\n\n"
            f"Output ONLY valid JSON matching this schema:\n{json.dumps(EVALUATION_SCHEMA, indent=2)}"
        )

    messages = [
        {
            "role": "system",
            "content": system_content,
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic.topic_name}\n\n"
                f"=== REFERENCE FACTS ===\n{reference_facts}\n\n"
                f"=== GENERATED CURRICULUM ===\n{json.dumps(generated_json, indent=2)}\n"
            ),
        },
    ]

    print("  [eval] Requesting evaluation from LLM-as-a-Judge...")
    result = chat_json(
        settings=settings,
        messages=messages,
        model=settings.extraction_model,  # We can use extraction model or generation model
        stage="evaluation",
        topic_sn=None,
    )

    try:
        from edu_curator.extraction import parse_json_robust
        eval_dict = parse_json_robust(result.content)
        
        # Sanitize overall scores to always be float
        eval_dict["faithfulness_score"] = _parse_score(eval_dict.get("faithfulness_score", 0))
        eval_dict["completeness_score"] = _parse_score(eval_dict.get("completeness_score", 0))
        
        # Format subtopic breakdowns into overall reasons
        if has_subtopics and "subtopics" in eval_dict and isinstance(eval_dict["subtopics"], list):
            f_reasons = [eval_dict.get("faithfulness_reason") or "No overall faithfulness feedback provided."]
            c_reasons = [eval_dict.get("completeness_reason") or "No overall completeness feedback provided."]
            
            f_reasons.append("\n\n### Subtopic Breakdowns (Faithfulness):")
            c_reasons.append("\n\n### Subtopic Breakdowns (Completeness):")
            
            for sub in eval_dict["subtopics"]:
                sub_name = sub.get("subtopic_name", "Unknown Subtopic")
                
                # Sanitize subtopic scores
                sub_f_score = _parse_score(sub.get("faithfulness_score", 0))
                sub["faithfulness_score"] = sub_f_score
                sub_f_reason = sub.get("faithfulness_reason", "No feedback provided.")
                f_reasons.append(f"- **{sub_name}** (Score: {sub_f_score}/10): {sub_f_reason}")
                
                sub_c_score = _parse_score(sub.get("completeness_score", 0))
                sub["completeness_score"] = sub_c_score
                sub_c_reason = sub.get("completeness_reason", "No feedback provided.")
                c_reasons.append(f"- **{sub_name}** (Score: {sub_c_score}/10): {sub_c_reason}")
                
            eval_dict["faithfulness_reason"] = "\n".join(f_reasons)
            eval_dict["completeness_reason"] = "\n".join(c_reasons)
            
        return eval_dict
    except Exception as e:
        print(f"  [eval] Failed to parse evaluation JSON: {e}")
        return {"error": str(e), "raw": result.content}


def print_evaluation_scorecard(topic_name: str, eval_result: dict):
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    console = Console()

    if "error" in eval_result:
        console.print(f"[red]Evaluation failed: {eval_result['error']}[/red]")
        return

    f_score = eval_result.get("faithfulness_score", 0)
    c_score = eval_result.get("completeness_score", 0)

    f_color = "green" if f_score >= 8 else "yellow" if f_score >= 5 else "red"
    c_color = "green" if c_score >= 8 else "yellow" if c_score >= 5 else "red"

    table = Table(
        title=f"RAG Evaluation: {topic_name}", show_header=True, header_style="bold magenta"
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Reasoning", style="dim")

    table.add_row(
        "Faithfulness",
        f"[{f_color}]{f_score}/10[/{f_color}]",
        eval_result.get("faithfulness_reason", ""),
    )
    table.add_row(
        "Completeness",
        f"[{c_color}]{c_score}/10[/{c_color}]",
        eval_result.get("completeness_reason", ""),
    )

    console.print()
    console.print(Panel(table, expand=False))
    console.print()
