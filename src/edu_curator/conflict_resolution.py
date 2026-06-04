"""Conflict resolution layer.

resolve_scalar() uses sentence-transformer embeddings to cluster semantically
similar candidate values and select the winning cluster via a Confidence Score:

    Cluster Score = 0.6 * Agreement + 0.4 * SourceAuthority

where:
    Agreement      = (sources_in_cluster / total_sources) * 100
    SourceAuthority = avg(trust_score * 10)  of sources in cluster

If sentence_transformers is not installed, falls back to trust-score sort
(previous behaviour), so the module degrades gracefully.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from edu_curator.ids import new_id
from edu_curator.schemas import CanonicalField, FactExtraction, Source, TopicKnowledge
from edu_curator.embeddings import compute_embeddings, cosine_similarity

SCALAR_FIELDS = {"definition", "purpose", "overview", "syntax", "expected_output"}
COLLECTION_FIELDS = {
    "key_properties",
    "benefits",
    "limitations",
    "common_misconceptions",
    "related_topics",
    "features",
    "examples",
    "steps",
    "components",
    "use_cases",
    "advantages",
    "inputs",
    "outputs",
    "interactions",
    "tradeoffs",
    "related_tools",
    "parameters",
    "common_errors",
}

# Cosine-similarity threshold for merging candidates into the same cluster
CLUSTER_SIM_THRESHOLD = 0.80


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def is_missing(value: Any) -> bool:
    return value is None or value == "" or value == []


def source_authority(source_ids: list[str], source_by_id: dict[str, Source]) -> float:
    if not source_ids:
        return 0
    scores = [source_by_id[source_id].trust_score * 10 for source_id in source_ids]
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Semantic clustering helpers
# ---------------------------------------------------------------------------


def _try_embed(texts: list[str]) -> list[list[float]] | None:
    """Try to embed texts using embeddings.compute_embeddings.

    Returns None if sentence_transformers is not available.
    """
    try:
        return compute_embeddings(texts)
    except Exception:
        return None


def _cosine(v1: list[float], v2: list[float]) -> float:
    import numpy as np

    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _cluster_candidates(
    candidates: list[FactExtraction],
    embeddings: list[list[float]],
) -> list[list[int]]:
    """Greedy single-linkage clustering by cosine similarity using vectorized NumPy operations.

    Returns a list of clusters; each cluster is a list of candidate indices.
    """
    n = len(candidates)
    if n == 0:
        return []

    import numpy as np

    embs = np.array(embeddings)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized_embs = embs / norms
    similarity_matrix = np.dot(normalized_embs, normalized_embs.T)

    assigned = [-1] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if assigned[i] != -1:
            continue
        cid = len(clusters)
        clusters.append([i])
        assigned[i] = cid
        for j in range(i + 1, n):
            if assigned[j] != -1:
                continue
            cluster_members = clusters[cid]
            sims = similarity_matrix[j, cluster_members]
            if np.max(sims) >= CLUSTER_SIM_THRESHOLD:
                clusters[cid].append(j)
                assigned[j] = cid

    return clusters


def _cluster_score(
    cluster_indices: list[int],
    candidates: list[FactExtraction],
    total_sources: int,
    source_by_id: dict[str, Source],
) -> float:
    """Compute the Cluster Confidence Score."""
    cluster_source_ids = list({candidates[i].source_id for i in cluster_indices})
    agreement = (len(cluster_source_ids) / max(total_sources, 1)) * 100
    authority = source_authority(cluster_source_ids, source_by_id)
    return 0.6 * agreement + 0.4 * authority


def _status_for_resolution(confidence: float, all_sources_disagree: bool) -> str:
    if all_sources_disagree:
        return "conflict_detected"
    if confidence < 75:
        return "needs_review"
    return "resolved"


# ---------------------------------------------------------------------------
# resolve_scalar — semantic clustering with trust-score fallback
# ---------------------------------------------------------------------------


def resolve_scalar(
    field_name: str,
    rows: list[FactExtraction],
    source_by_id: dict[str, Source],
) -> CanonicalField:
    candidates = [row for row in rows if not is_missing(row.field_value.get("value"))]
    if not candidates:
        return CanonicalField(
            status="missing", confidence=0, resolution_reason="no_supported_values"
        )

    # --- Attempt semantic clustering ---
    texts = [str(row.field_value.get("value", "")) for row in candidates]
    embeddings = _try_embed(texts)

    if embeddings is not None and len(embeddings) == len(candidates):
        clusters = _cluster_candidates(candidates, embeddings)
        total_sources = len({row.source_id for row in candidates})
        scored = [
            (
                _cluster_score(cl, candidates, total_sources, source_by_id),
                cl,
            )
            for cl in clusters
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_cluster = scored[0]
        losing_clusters = [cl for _, cl in scored[1:]]
        cluster_source_counts = [
            len({candidates[i].source_id for i in cl}) for _, cl in scored
        ]
        all_sources_disagree = (
            total_sources > 1 and len(clusters) > 1 and max(cluster_source_counts) == 1
        )

        # Within the winning cluster, pick the candidate from the highest-trust source
        winner_idx = max(
            best_cluster,
            key=lambda i: (
                source_by_id[candidates[i].source_id].trust_score,
                candidates[i].extraction_confidence or 0,
            ),
        )
        winner = candidates[winner_idx]

        alternatives = []
        for cl in losing_clusters:
            # Representative of each losing cluster = highest-trust candidate in it
            rep_idx = max(
                cl,
                key=lambda i: source_by_id[candidates[i].source_id].trust_score,
            )
            rep = candidates[rep_idx]
            alternatives.append(
                {
                    "value": rep.field_value.get("value"),
                    "source": rep.source_id,
                    "reason_not_selected": "lower_cluster_confidence_score",
                }
            )

        source_ids = sorted({row.source_id for row in candidates})
        confidence = min(100, best_score)
        resolution_reason = f"semantic_cluster_winner (score={best_score:.1f})"
        print(
            f"  [CR] {field_name}: {len(clusters)} cluster(s), "
            f"winning score={best_score:.1f}, "
            f"value='{str(winner.field_value.get('value', ''))[:60]}'"
        )
    else:
        # --- Fallback: trust-score sort (no sentence_transformers) ---
        candidates.sort(
            key=lambda row: (
                source_by_id[row.source_id].trust_score,
                row.extraction_confidence or 0,
            ),
            reverse=True,
        )
        winner = candidates[0]
        alternatives = [
            {
                "value": row.field_value.get("value"),
                "source": row.source_id,
                "reason_not_selected": "lower_trust_or_duplicate_candidate",
            }
            for row in candidates[1:]
            if row.field_value.get("value") != winner.field_value.get("value")
        ]
        source_ids = sorted({row.source_id for row in candidates})
        sources_by_value: dict[str, set[str]] = defaultdict(set)
        for row in candidates:
            sources_by_value[normalize_text(str(row.field_value.get("value")))].add(
                row.source_id
            )
        all_sources_disagree = (
            len(source_ids) > 1
            and len(sources_by_value) > 1
            and max(len(ids) for ids in sources_by_value.values()) == 1
        )
        confidence = min(
            100, source_authority(source_ids, source_by_id) + 5 * (len(source_ids) - 1)
        )
        resolution_reason = "highest_trust_source (fallback — embeddings unavailable)"

    status = _status_for_resolution(confidence, all_sources_disagree)

    return CanonicalField(
        canonical_value=winner.field_value.get("value"),
        confidence=round(confidence, 2),
        sources=[winner.source_id],
        alternative_values=alternatives,
        resolution_reason=resolution_reason,
        status=status,
    )


# ---------------------------------------------------------------------------
# resolve_collection — trust-sorted de-duplication
# ---------------------------------------------------------------------------


def resolve_collection(
    rows: list[FactExtraction],
    source_by_id: dict[str, Source],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        values = row.field_value.get("value") or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            if is_missing(value):
                continue
            key = normalize_text(str(value))
            if key not in merged:
                merged[key] = {"value": value, "sources": [row.source_id]}
            elif row.source_id not in merged[key]["sources"]:
                merged[key]["sources"].append(row.source_id)

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        best_trust = max(source_by_id[source_id].trust_score for source_id in item["sources"])
        return (-best_trust, str(item["value"]))

    return sorted(merged.values(), key=sort_key)


# ---------------------------------------------------------------------------
# resolve_topic_knowledge — main orchestrator
# ---------------------------------------------------------------------------

FIELD_WEIGHTS: dict[str, float] = {
    "definition": 3.0,
    "syntax": 3.0,
    "overview": 3.0,
    "purpose": 2.0,
    "key_properties": 2.0,
    "features": 2.0,
    "components": 2.0,
    "steps": 2.0,
    "parameters": 2.0,
    "inputs": 2.0,
    "outputs": 2.0,
    "interactions": 2.0,
}

CRITICAL_FIELDS: dict[str, str] = {
    "concept": "definition",
    "command": "syntax",
    "tool": "overview",
    "architecture": "overview",
    "process": "overview",
}


def resolve_topic_knowledge(
    topic_id: str,
    facts: list[FactExtraction],
    sources: list[Source],
    schema_version: str = "1.0",
    topic_type: str | None = None,
    topic_name: str | None = None,
) -> TopicKnowledge:
    source_by_id = {source.id: source for source in sources}
    by_field: dict[str, list[FactExtraction]] = defaultdict(list)
    for fact in facts:
        if fact.topic_id == topic_id:
            by_field[fact.field_name].append(fact)

    # Infer topic type if not provided
    if not topic_type and by_field:
        if "definition" in by_field:
            topic_type = "concept"
        elif "syntax" in by_field:
            topic_type = "command"
        elif "related_tools" in by_field:
            topic_type = "tool"
        elif "components" in by_field:
            topic_type = "architecture"
        elif "steps" in by_field:
            topic_type = "process"

    subtopics = [s.strip() for s in topic_name.split(",") if s.strip()] if topic_name else []

    knowledge: dict[str, Any] = {}
    weighted_sum = 0.0
    total_weight = 0.0
    sources_used: set[str] = set()

    if len(subtopics) > 1:
        # ── Subtopic-wise resolution ───────────────────────────────────────────
        topic_facts = [f for f in facts if f.topic_id == topic_id]
        
        # Gather all unique texts from non-empty fact values to embed in a single batch
        texts_to_embed = []
        text_to_idx = {}
        for fact in topic_facts:
            val = fact.field_value.get("value")
            if not is_missing(val):
                if isinstance(val, list):
                    for item in val:
                        txt = str(item).strip()
                        if txt and txt not in text_to_idx:
                            text_to_idx[txt] = len(texts_to_embed)
                            texts_to_embed.append(txt)
                else:
                    txt = str(val).strip()
                    if txt and txt not in text_to_idx:
                        text_to_idx[txt] = len(texts_to_embed)
                        texts_to_embed.append(txt)

        text_to_subtopic = {}
        if texts_to_embed:
            try:
                all_embeddings = compute_embeddings(subtopics + texts_to_embed)
                sub_embs = all_embeddings[:len(subtopics)]
                val_embs = all_embeddings[len(subtopics):]
                
                for txt, idx in text_to_idx.items():
                    v_emb = val_embs[idx]
                    best_sub_idx = 0
                    best_sim = -1.0
                    for s_idx, s_emb in enumerate(sub_embs):
                        sim = cosine_similarity(v_emb, s_emb)
                        if sim > best_sim:
                            best_sim = sim
                            best_sub_idx = s_idx
                    text_to_subtopic[txt] = best_sub_idx
            except Exception as e:
                print(f"Error embedding facts for subtopic matching: {e}")

        # Distribute the facts by subtopic index
        subtopic_facts: dict[int, list[FactExtraction]] = defaultdict(list)
        for fact in topic_facts:
            val = fact.field_value.get("value")
            if is_missing(val):
                for s_idx in range(len(subtopics)):
                    subtopic_facts[s_idx].append(fact)
                continue
                
            if fact.field_name in COLLECTION_FIELDS:
                by_sub: dict[int, list[Any]] = defaultdict(list)
                val_list = val if isinstance(val, list) else [val]
                for item in val_list:
                    txt = str(item).strip()
                    sub_idx = text_to_subtopic.get(txt, 0)
                    by_sub[sub_idx].append(item)
                
                for s_idx, items in by_sub.items():
                    sub_fact = fact.model_copy(update={
                        "field_value": {"value": items}
                    })
                    subtopic_facts[s_idx].append(sub_fact)
            else:
                txt = str(val).strip()
                sub_idx = text_to_subtopic.get(txt, 0)
                subtopic_facts[sub_idx].append(fact)

        for s_idx in range(len(subtopics)):
            s_facts = subtopic_facts[s_idx]
            s_by_field = defaultdict(list)
            for f in s_facts:
                s_by_field[f.field_name].append(f)
                
            for field_name in sorted(by_field.keys()):
                rows = s_by_field[field_name]
                weight = FIELD_WEIGHTS.get(field_name, 1.0)
                sub_key = f"{s_idx}.{field_name}"
                
                for row in rows:
                    if not is_missing(row.field_value.get("value")):
                        sources_used.add(row.source_id)
                        
                if field_name in COLLECTION_FIELDS:
                    resolved = resolve_collection(rows, source_by_id)
                    knowledge[sub_key] = resolved
                    if resolved:
                        field_conf = source_authority(
                            sorted({source_id for item in resolved for source_id in item["sources"]}),
                            source_by_id,
                        )
                        weighted_sum += field_conf * weight
                        total_weight += weight
                else:
                    resolved_field = resolve_scalar(field_name, rows, source_by_id)
                    knowledge[sub_key] = resolved_field
                    field_conf = resolved_field.confidence or 0.0
                    weighted_sum += field_conf * weight
                    total_weight += weight

    else:
        # ── Original flat resolution ───────────────────────────────────────────
        for field_name, rows in sorted(by_field.items()):
            for row in rows:
                if not is_missing(row.field_value.get("value")):
                    sources_used.add(row.source_id)

            weight = FIELD_WEIGHTS.get(field_name, 1.0)

            if field_name in COLLECTION_FIELDS:
                resolved = resolve_collection(rows, source_by_id)
                knowledge[field_name] = resolved
                if resolved:
                    field_conf = source_authority(
                        sorted({source_id for item in resolved for source_id in item["sources"]}),
                        source_by_id,
                    )
                    weighted_sum += field_conf * weight
                    total_weight += weight
            else:
                resolved_field = resolve_scalar(field_name, rows, source_by_id)
                knowledge[field_name] = resolved_field
                field_conf = resolved_field.confidence or 0.0
                weighted_sum += field_conf * weight
                total_weight += weight

    # Trigger Flags computation
    is_single_source = len(sources_used) == 1
    is_contradictory = any(
        isinstance(val, CanonicalField) and val.status == "conflict_detected"
        for val in knowledge.values()
    )

    crit_field = CRITICAL_FIELDS.get(str(topic_type).lower()) if topic_type else None
    critical_field_missing = False
    missing_details = []
    if crit_field:
        if len(subtopics) > 1:
            all_missing = True
            for s_idx in range(len(subtopics)):
                sub_key = f"{s_idx}.{crit_field}"
                field_val = knowledge.get(sub_key)
                sub_missing = False
                if field_val is None:
                    sub_missing = True
                elif isinstance(field_val, CanonicalField):
                    sub_missing = (
                        field_val.status == "missing" or is_missing(field_val.canonical_value)
                    )
                if not sub_missing:
                    all_missing = False
                    break
            if all_missing:
                critical_field_missing = True
                missing_details.append(f"All subtopics are missing critical field '{crit_field}'")
        else:
            field_val = knowledge.get(crit_field)
            if field_val is None:
                critical_field_missing = True
            elif isinstance(field_val, CanonicalField):
                critical_field_missing = (
                    field_val.status == "missing" or is_missing(field_val.canonical_value)
                )
            if critical_field_missing:
                missing_details.append(f"Critical Field '{crit_field}' is missing")

    contradictory_details = []
    for f_name, f_val in sorted(knowledge.items()):
        if isinstance(f_val, CanonicalField) and f_val.status == "conflict_detected":
            involved_source_ids = set()
            if f_val.sources:
                involved_source_ids.update(f_val.sources)
            for alt in f_val.alternative_values:
                if "source" in alt:
                    involved_source_ids.add(alt["source"])

            source_titles = []
            for s_id in sorted(involved_source_ids):
                s_obj = source_by_id.get(s_id)
                if s_obj and s_obj.title:
                    source_titles.append(s_obj.title)
                else:
                    source_titles.append(s_id)

            if len(source_titles) > 1:
                sources_str = ", ".join(source_titles[:-1]) + " and " + source_titles[-1]
            elif source_titles:
                sources_str = source_titles[0]
            else:
                sources_str = "unknown sources"

            human_name = f_name
            if "." in f_name:
                parts = f_name.split(".", 1)
                if parts[0].isdigit():
                    s_idx = int(parts[0])
                    human_name = f"Subtopic {s_idx + 1} ('{subtopics[s_idx]}') — {parts[1]}"

            contradictory_details.append(f"Conflict on '{human_name}' between {sources_str}")

    knowledge["_review_triggers"] = {
        "is_single_source": is_single_source,
        "is_contradictory": is_contradictory,
        "critical_field_missing": critical_field_missing,
        "contradictory_details": contradictory_details,
        "missing_details": missing_details,
    }

    now = datetime.now(UTC)
    confidence = (weighted_sum / total_weight) if total_weight > 0 else 0.0
    return TopicKnowledge(
        id=new_id(),
        topic_id=topic_id,
        schema_version=schema_version,
        knowledge=knowledge,
        sources_used=sorted(sources_used),
        confidence=round(confidence, 2),
        created_at=now,
        updated_at=now,
    )
