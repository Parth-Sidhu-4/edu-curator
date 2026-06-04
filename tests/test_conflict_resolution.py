from datetime import UTC, datetime

import edu_curator.conflict_resolution as cr
from edu_curator.conflict_resolution import resolve_collection, resolve_scalar
from edu_curator.ids import new_id
from edu_curator.schemas import FactExtraction, Source


def make_fact(source_id: str, value, field_name: str = "definition") -> FactExtraction:
    return FactExtraction(
        id=new_id(),
        topic_id="t1",
        source_id=source_id,
        chunk_id=f"c-{source_id}",
        field_name=field_name,
        field_value={"value": value},
        schema_version="1.0",
        prompt_version="1",
        extraction_model="model",
        status="completed",
        created_at=datetime.now(UTC),
    )


def test_resolve_scalar(monkeypatch):
    monkeypatch.setattr(cr, "_try_embed", lambda texts: None)
    source1 = Source(id="s1", source_type="website", title="S1", trust_score=10)
    source2 = Source(id="s2", source_type="website", title="S2", trust_score=2)

    source_by_id = {"s1": source1, "s2": source2}

    fact1 = FactExtraction(
        id=new_id(),
        topic_id="t1",
        source_id="s1",
        chunk_id="c1",
        field_name="definition",
        field_value={"value": "High trust definition"},
        schema_version="1.0",
        prompt_version="1",
        extraction_model="model",
        status="completed",
        created_at=datetime.now(UTC),
    )
    fact2 = FactExtraction(
        id=new_id(),
        topic_id="t1",
        source_id="s2",
        chunk_id="c2",
        field_name="definition",
        field_value={"value": "Low trust definition"},
        schema_version="1.0",
        prompt_version="1",
        extraction_model="model",
        status="completed",
        created_at=datetime.now(UTC),
    )

    result = resolve_scalar("definition", [fact1, fact2], source_by_id)
    assert result.canonical_value == "High trust definition"
    assert "Low trust definition" in [alt["value"] for alt in result.alternative_values]


def test_resolve_scalar_marks_needs_review_for_low_confidence_agreement(monkeypatch):
    monkeypatch.setattr(cr, "_try_embed", lambda texts: None)

    source1 = Source(id="s1", source_type="website", title="S1", trust_score=4)
    source2 = Source(id="s2", source_type="website", title="S2", trust_score=4)
    source_by_id = {"s1": source1, "s2": source2}

    result = resolve_scalar(
        "definition",
        [make_fact("s1", "Same definition"), make_fact("s2", "Same definition")],
        source_by_id,
    )

    assert result.status == "needs_review"
    assert result.confidence < 75


def test_resolve_scalar_marks_conflict_when_all_sources_disagree(monkeypatch):
    monkeypatch.setattr(
        cr,
        "_try_embed",
        lambda texts: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    )

    sources = [
        Source(id="s1", source_type="website", title="S1", trust_score=10),
        Source(id="s2", source_type="website", title="S2", trust_score=10),
        Source(id="s3", source_type="website", title="S3", trust_score=10),
    ]
    source_by_id = {source.id: source for source in sources}

    result = resolve_scalar(
        "definition",
        [
            make_fact("s1", "Docker packages applications in containers."),
            make_fact("s2", "Kubernetes orchestrates container clusters."),
            make_fact("s3", "Terraform provisions infrastructure as code."),
        ],
        source_by_id,
    )

    assert result.status == "conflict_detected"
    assert result.alternative_values


def test_resolve_collection():
    source1 = Source(id="s1", source_type="website", title="S1", trust_score=10)
    source2 = Source(id="s2", source_type="website", title="S2", trust_score=5)

    source_by_id = {"s1": source1, "s2": source2}

    fact1 = FactExtraction(
        id=new_id(),
        topic_id="t1",
        source_id="s1",
        chunk_id="c1",
        field_name="benefits",
        field_value={"value": ["Fast", "Secure"]},
        schema_version="1.0",
        prompt_version="1",
        extraction_model="model",
        status="completed",
        created_at=datetime.now(UTC),
    )
    fact2 = FactExtraction(
        id=new_id(),
        topic_id="t1",
        source_id="s2",
        chunk_id="c2",
        field_name="benefits",
        field_value={"value": ["Fast", "Cheap"]},
        schema_version="1.0",
        prompt_version="1",
        extraction_model="model",
        status="completed",
        created_at=datetime.now(UTC),
    )

    result = resolve_collection([fact1, fact2], source_by_id)
    # Deduplication and normalization should mean "Fast" is merged
    values = [item["value"] for item in result]
    assert "Fast" in values
    assert "Secure" in values
    assert "Cheap" in values

    # "Fast" should have both sources
    fast_item = next(item for item in result if item["value"] == "Fast")
    assert "s1" in fast_item["sources"] and "s2" in fast_item["sources"]


def test_resolve_topic_knowledge_weighted_and_triggers(monkeypatch):
    monkeypatch.setattr(cr, "_try_embed", lambda texts: None)

    source1 = Source(id="s1", source_type="website", title="S1", trust_score=10.0)
    source2 = Source(id="s2", source_type="website", title="S2", trust_score=5.0)

    # 1. Single source topic (definition and purpose present, definition is weight 3.0, purpose is 2.0)
    facts_single = [
        FactExtraction(
            id=new_id(),
            topic_id="t1",
            source_id="s1",
            chunk_id="c1",
            field_name="definition",
            field_value={"value": "A concept"},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
        FactExtraction(
            id=new_id(),
            topic_id="t1",
            source_id="s1",
            chunk_id="c1",
            field_name="purpose",
            field_value={"value": "To do stuff"},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
    ]

    res_single = cr.resolve_topic_knowledge(
        topic_id="t1",
        facts=facts_single,
        sources=[source1],
        topic_type="concept"
    )

    triggers = res_single.knowledge.get("_review_triggers")
    assert triggers is not None
    assert triggers["is_single_source"] is True
    assert triggers["is_contradictory"] is False
    assert triggers["critical_field_missing"] is False
    assert res_single.confidence == 100.0

    # 2. Multi-source topic, missing critical field (definition) for a concept
    facts_missing = [
        FactExtraction(
            id=new_id(),
            topic_id="t2",
            source_id="s1",
            chunk_id="c1",
            field_name="purpose",
            field_value={"value": "To serve purpose"},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
        FactExtraction(
            id=new_id(),
            topic_id="t2",
            source_id="s2",
            chunk_id="c2",
            field_name="purpose",
            field_value={"value": "To do more things"},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
        FactExtraction(
            id=new_id(),
            topic_id="t2",
            source_id="s2",
            chunk_id="c2",
            field_name="definition",
            field_value={"value": None},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
    ]

    res_missing = cr.resolve_topic_knowledge(
        topic_id="t2",
        facts=facts_missing,
        sources=[source1, source2],
        topic_type="concept"
    )

    triggers_missing = res_missing.knowledge.get("_review_triggers")
    assert triggers_missing["is_single_source"] is False
    assert triggers_missing["critical_field_missing"] is True
    # "purpose" (weight 2.0) has s1 (trust 10.0) and s2 (trust 5.0).
    # Since they disagree, purpose confidence resolves to 80.0.
    # "definition" (weight 3.0) is missing (confidence 0.0).
    # Weighted average = (80.0 * 2.0 + 0.0 * 3.0) / (2.0 + 3.0) = 32.0
    assert res_missing.confidence == 32.0


def test_resolve_topic_knowledge_subtopics(monkeypatch):
    def mock_compute_embeddings(texts):
        res = []
        for t in texts:
            if "Pull Requests" in t or "PR" in t:
                res.append([1.0, 0.0])
            elif "Forking" in t or "Fork" in t:
                res.append([0.0, 1.0])
            else:
                res.append([0.5, 0.5])
        return res

    monkeypatch.setattr(cr, "compute_embeddings", mock_compute_embeddings)

    source1 = Source(id="s1", source_type="website", title="S1", trust_score=10.0)
    source2 = Source(id="s2", source_type="website", title="S2", trust_score=5.0)

    facts = [
        FactExtraction(
            id=new_id(),
            topic_id="t_sub",
            source_id="s1",
            chunk_id="c1",
            field_name="overview",
            field_value={"value": "PR overview text"},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
        FactExtraction(
            id=new_id(),
            topic_id="t_sub",
            source_id="s2",
            chunk_id="c2",
            field_name="overview",
            field_value={"value": "Fork overview text"},
            schema_version="1.0",
            prompt_version="1",
            extraction_model="m",
            status="completed",
            created_at=datetime.now(UTC),
        ),
    ]

    res = cr.resolve_topic_knowledge(
        topic_id="t_sub",
        facts=facts,
        sources=[source1, source2],
        topic_type="concept",
        topic_name="Pull Requests, Forking"
    )

    # Subtopic 0 (Pull Requests) should get "PR overview text"
    assert "0.overview" in res.knowledge
    assert res.knowledge["0.overview"].canonical_value == "PR overview text"

    # Subtopic 1 (Forking) should get "Fork overview text"
    assert "1.overview" in res.knowledge
    assert res.knowledge["1.overview"].canonical_value == "Fork overview text"

    # No conflict detected because they were resolved independently!
    assert res.knowledge["0.overview"].status == "resolved"
    assert res.knowledge["1.overview"].status == "resolved"

