import pytest
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, UTC

from edu_curator.config import load_settings
from edu_curator.schemas import (
    SyllabusTopic, Source, ContentChunk, SourceToTopicMapping, FactExtraction,
    TopicKnowledge, TopicContent, TopicType, ReviewStatus, ExtractionError,
    NormalizedDocument
)
import edu_curator.storage
import edu_curator.pipeline
from edu_curator.pipeline import (
    run_chunk, run_map_topic, run_extract, run_resolve,
    run_generate_content, run_check_consistency, run_full_pipeline,
    _topic_uuid
)

class MockSettings:
    def __init__(self):
        self.supabase_url = ""
        self.supabase_key = ""
        self.use_batch_api = False
        self.extraction_model = "mock-extract-model"
        self.generation_model = "mock-gen-model"

@pytest.fixture
def test_env(tmp_path, monkeypatch):
    # Mock settings
    settings = MockSettings()
    monkeypatch.setattr(edu_curator.pipeline, "DATA", tmp_path / "data")
    
    # Mock get_table to write to temporary paths
    def mocked_get_table(name, model, settings=None):
        return edu_curator.storage.JsonTable(tmp_path / f"{name}.json", model, name=name)
        
    monkeypatch.setattr(edu_curator.storage, "get_table", mocked_get_table)
    monkeypatch.setattr(edu_curator.pipeline, "get_table", mocked_get_table)
    
    # Seed syllabus_topics and sources
    topics_tbl = mocked_get_table("syllabus_topics", SyllabusTopic)
    topic = SyllabusTopic(
        id=_topic_uuid(1),
        chapter="1",
        topic_name="Introduction to DevOps",
        topic_type=TopicType.concept
    )
    topics_tbl.write([topic])
    
    sources_tbl = mocked_get_table("sources", Source)
    source = Source(
        id="source_1",
        title="DevOps Manual",
        source_type="website",
        topic_ids=[topic.id]
    )
    sources_tbl.write([source])
    
    return settings, topic, source

def test_run_chunk_stage(test_env):
    settings, topic, source = test_env
    
    # 1. Chunking fails if no normalized documents
    with pytest.raises(ValueError, match="No normalized documents"):
        run_chunk(settings)
        
    # Seed normalized documents using the mocked table
    docs_tbl = edu_curator.storage.get_table("documents", NormalizedDocument)
    doc = NormalizedDocument(
        source_id=source.id,
        title=source.title,
        content="DevOps is a set of practices that combines software development and IT operations."
    )
    docs_tbl.write([doc])
    
    # Run chunking
    added, total = run_chunk(settings, chunk_size=10, overlap=2)
    assert added > 0
    assert total == added
    
    # Second run should be additive and skip
    added2, total2 = run_chunk(settings)
    assert added2 == 0
    assert total2 == total

def test_run_map_topic_stage(test_env, monkeypatch):
    settings, topic, source = test_env
    
    # Seed docs and chunks using the mocked table
    docs_tbl = edu_curator.storage.get_table("documents", NormalizedDocument)
    doc = NormalizedDocument(source_id=source.id, title=source.title, content="DevOps definition")
    docs_tbl.write([doc])
    
    run_chunk(settings)
    
    # Mock semantic mapper
    mock_mapping = SourceToTopicMapping(
        id="map_1",
        source_id=source.id,
        chunk_id="chunk_1",
        topic_id=topic.id,
        vector_score=0.8
    )
    monkeypatch.setattr(
        "edu_curator.mapping.map_chunks_semantically",
        lambda *args, **kwargs: ([mock_mapping], [])
    )
    
    # Run mapping
    mapped, total, name = run_map_topic(settings, sn=1, threshold=0.40)
    assert mapped == 1
    assert name == "Introduction to DevOps"
    
    mappings_tbl = edu_curator.storage.get_table("source_to_topic_mapping", SourceToTopicMapping)
    mappings = mappings_tbl.read()
    assert len(mappings) == 1
    assert mappings[0].id == "map_1"

def test_run_full_pipeline_orchestration(test_env, monkeypatch):
    settings, topic, source = test_env
    
    # Seed docs using the mocked table
    docs_tbl = edu_curator.storage.get_table("documents", NormalizedDocument)
    doc = NormalizedDocument(source_id=source.id, title=source.title, content="DevOps definition")
    docs_tbl.write([doc])
    
    # Mock mapping
    mock_mapping = SourceToTopicMapping(
        id="map_1",
        source_id=source.id,
        chunk_id="chunk_1",
        topic_id=topic.id,
        vector_score=0.8
    )
    monkeypatch.setattr(
        "edu_curator.mapping.map_chunks_semantically",
        lambda *args, **kwargs: ([mock_mapping], [])
    )
    
    # Mock extraction stage
    mock_fact = FactExtraction(
        id="fact_1",
        topic_id=topic.id,
        source_id=source.id,
        chunk_id="chunk_1",
        field_name="definition",
        field_value={"value": "Mocked devops definition"},
        schema_version="1",
        prompt_version="1",
        extraction_model="mock"
    )
    monkeypatch.setattr(
        "edu_curator.pipeline.extract_topic_batched",
        lambda *args, **kwargs: ([mock_fact], [])
    )
    
    # Mock conflict resolution resolve_topic_knowledge
    mock_knowledge = TopicKnowledge(
        id="tk_1",
        topic_id=topic.id,
        schema_version="1",
        knowledge={"definition": {"canonical_value": "DevOps resolved definition"}},
        confidence=90.0
    )
    monkeypatch.setattr(
        "edu_curator.pipeline.resolve_topic_knowledge",
        lambda *args, **kwargs: mock_knowledge
    )
    
    # Mock refine_curriculum
    mock_content = TopicContent(
        id="tc_1",
        topic_id=topic.id,
        content_json={"definition": "DevOps resolved definition"},
        review_status=ReviewStatus.pending,
        version=1
    )
    monkeypatch.setattr(
        "edu_curator.revision.refine_curriculum",
        lambda *args, **kwargs: (mock_content, {"faithfulness_score": 9.5, "completeness_score": 9.0})
    )
    
    # Mock run_consistency_check
    monkeypatch.setattr(
        "edu_curator.pipeline.run_check_consistency",
        lambda *args, **kwargs: (mock_content.model_copy(update={"consistency_check_status": True}), {"status": "ok"})
    )
    monkeypatch.setattr(
        "edu_curator.pipeline.run_consistency_check",
        lambda *args, **kwargs: (mock_content.model_copy(update={"consistency_check_status": True}), {"status": "ok"})
    )
    
    # Run full pipeline sequential runner via pipeline module directly
    echo_msgs = []
    def custom_echo(msg):
        echo_msgs.append(msg)
        
    run_full_pipeline(
        settings,
        sn=1,
        force=True,
        echo_fn=custom_echo
    )
    
    # Check messages and outputs written
    assert any("=== run-topic --sn 1 ===" in m for m in echo_msgs)
    assert any("=== DONE: topic sn=1 complete ===" in m for m in echo_msgs)
    
    # Verify TopicContent is written using the mocked table
    tc_tbl = edu_curator.storage.get_table("topic_content", TopicContent)
    content = tc_tbl.read()
    assert len(content) == 1
    assert content[0].id == "tc_1"


def test_validate_generated_content_subtopics():
    from edu_curator.generation import validate_generated_content

    payload = {
        "topic_name": "Test Topic",
        "subtopics": [
            {
                "subtopic_name": "1.1 Pull Requests",
                "summary": "Summary test",
                "definition": "Definition test",
                "purpose": "Purpose test",
                "key_properties": ["Property 1"],
                "benefits": ["Benefit 1"],
                "limitations": ["Limitation 1"],
                "common_misconceptions": ["Misconception 1"],
                "related_topics": ["Related 1"]
            },
            {
                "subtopic_name": "Forking",
                "summary": "Summary test 2",
                "definition": "Definition test 2",
                "purpose": "Purpose test 2",
                "key_properties": ["Property 2"],
                "benefits": ["Benefit 2"],
                "limitations": ["Limitation 2"],
                "common_misconceptions": ["Misconception 2"],
                "related_topics": ["Related 2"]
            }
        ]
    }

    # 1. Matching counts and names (prefix cleaned)
    expected = ["Pull Requests", "Forking"]
    issues = validate_generated_content(payload, expected_subtopics=expected)
    assert not issues

    # 2. Count mismatch
    issues_mismatch = validate_generated_content(payload, expected_subtopics=["Pull Requests"])
    assert any("subtopic count mismatch" in issue for issue in issues_mismatch)

    # 3. Name mismatch
    issues_name = validate_generated_content(payload, expected_subtopics=["Pull Requests", "Branching"])
    assert any("subtopic name mismatch" in issue for issue in issues_name)

    # 4. Valid FAQ
    payload_faq = payload.copy()
    payload_faq["faq"] = [
        {"question": "What is devops?", "answer": "DevOps combines development and operations."}
    ]
    issues_faq = validate_generated_content(payload_faq, expected_subtopics=expected)
    assert not issues_faq

    # 5. Invalid FAQ structure (not a list)
    payload_faq_invalid = payload.copy()
    payload_faq_invalid["faq"] = "not a list"
    issues_faq_invalid = validate_generated_content(payload_faq_invalid, expected_subtopics=expected)
    assert any("field 'faq' must be a list" in issue for issue in issues_faq_invalid)

