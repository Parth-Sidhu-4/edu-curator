import os
import sys
import json
import uuid
import pytest
import psycopg2
from pathlib import Path
from datetime import datetime, timezone

workspace_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace_root / "src"))
sys.path.insert(0, str(workspace_root))


from edu_curator.config import load_settings
from edu_curator.storage import get_table, JsonTable
from edu_curator.schemas import (
    SyllabusTopic, TopicType, Source, SourceType, ContentChunk,
    SourceToTopicMapping, FactExtraction, TopicKnowledge, TopicContent,
    KnowledgeOverride, ExtractionError, CurationJob, ReviewerActivity,
    EvaluationJob, KnowledgeOverrideHistory
)
from dashboard.serve import save_knowledge_overrides

db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgresql+psycopg2://"):
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")


def test_local_json_cascading_and_file_cleanup(tmp_path, monkeypatch):
    """Test Local JSON Cascading Deletes (DI-03) and Local Source File Cleanup (DI-08)."""
    # 1. Setup mock paths using monkeypatch to redirect JSON storage to tmp_path
    topic_path = tmp_path / "syllabus_topics.json"
    source_path = tmp_path / "sources.json"
    chunk_path = tmp_path / "content_chunks.json"
    mapping_path = tmp_path / "source_to_topic_mapping.json"
    fact_path = tmp_path / "fact_extractions.json"
    knowledge_path = tmp_path / "topic_knowledge.json"
    content_path = tmp_path / "topic_content.json"
    override_path = tmp_path / "knowledge_overrides.json"
    error_path = tmp_path / "extraction_errors.json"
    curation_path = tmp_path / "curation_jobs.json"
    evaluation_path = tmp_path / "evaluation_jobs.json"
    reviewer_activity_path = tmp_path / "reviewer_activity.json"

    # Define a custom get_table that returns tables pointing to tmp_path
    def mock_get_table(name, model, settings=None):
        path_map = {
            "syllabus_topics": topic_path,
            "sources": source_path,
            "content_chunks": chunk_path,
            "source_to_topic_mapping": mapping_path,
            "fact_extractions": fact_path,
            "topic_knowledge": knowledge_path,
            "topic_content": content_path,
            "knowledge_overrides": override_path,
            "extraction_errors": error_path,
            "curation_jobs": curation_path,
            "evaluation_jobs": evaluation_path,
            "reviewer_activity": reviewer_activity_path,
        }
        return JsonTable(path_map[name], model, name=name)

    monkeypatch.setattr("edu_curator.storage.get_table", mock_get_table)

    # Initialize tables
    tbl_topics = mock_get_table("syllabus_topics", SyllabusTopic)
    tbl_sources = mock_get_table("sources", Source)
    tbl_chunks = mock_get_table("content_chunks", ContentChunk)
    tbl_mappings = mock_get_table("source_to_topic_mapping", SourceToTopicMapping)
    tbl_facts = mock_get_table("fact_extractions", FactExtraction)
    tbl_knowledge = mock_get_table("topic_knowledge", TopicKnowledge)
    tbl_content = mock_get_table("topic_content", TopicContent)
    tbl_overrides = mock_get_table("knowledge_overrides", KnowledgeOverride)
    tbl_errors = mock_get_table("extraction_errors", ExtractionError)
    tbl_curation = mock_get_table("curation_jobs", CurationJob)
    tbl_evaluation = mock_get_table("evaluation_jobs", EvaluationJob)
    tbl_reviewer = mock_get_table("reviewer_activity", ReviewerActivity)

    # 2. Insert test topic & dependents
    topic_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    tbl_topics.write([
        SyllabusTopic(id=topic_id, chapter="Ch 1", topic_name="T 1", topic_type=TopicType.concept)
    ])
    
    # Create local source file
    dummy_filename = f"test_dummy_{uuid.uuid4().hex}.pdf"
    dummy_filepath = workspace_root / dummy_filename
    dummy_filepath.write_text("dummy PDF content", encoding="utf-8")
    assert dummy_filepath.exists()

    tbl_sources.write([
        Source(id=source_id, title="Src 1", source_type=SourceType.pdf, local_path=dummy_filename, trust_score=5.0)
    ])
    tbl_chunks.write([
        ContentChunk(id=chunk_id, source_id=source_id, chunk_text="Chunk text", chunk_number=1)
    ])
    tbl_mappings.write([
        SourceToTopicMapping(id=str(uuid.uuid4()), source_id=source_id, chunk_id=chunk_id, topic_id=topic_id)
    ])
    tbl_facts.write([
        FactExtraction(
            id=str(uuid.uuid4()), topic_id=topic_id, source_id=source_id, chunk_id=chunk_id,
            field_name="definition", field_value={"definition": "def"},
            schema_version="1", prompt_version="1", extraction_model="model"
        )
    ])
    tbl_knowledge.write([
        TopicKnowledge(id=str(uuid.uuid4()), topic_id=topic_id, schema_version="1", knowledge={})
    ])
    tbl_content.write([
        TopicContent(id=str(uuid.uuid4()), topic_id=topic_id, content_json={})
    ])
    tbl_overrides.write([
        KnowledgeOverride(id=str(uuid.uuid4()), topic_id=topic_id, field_name="definition", corrected_value="new_def")
    ])
    tbl_errors.write([
        ExtractionError(id=str(uuid.uuid4()), topic_id=topic_id, source_id=source_id, chunk_id=chunk_id, error_type="ERR", error_detail="detail")
    ])
    tbl_curation.write([
        CurationJob(id=str(uuid.uuid4()), topic_id=topic_id)
    ])
    tbl_evaluation.write([
        EvaluationJob(id=str(uuid.uuid4()), topic_id=topic_id)
    ])
    tbl_reviewer.write([
        ReviewerActivity(id=str(uuid.uuid4()), topic_id=topic_id, action="review")
    ])

    # Assert inserts were written
    assert len(tbl_topics.read()) == 1
    assert len(tbl_sources.read()) == 1
    assert len(tbl_chunks.read()) == 1
    assert len(tbl_mappings.read()) == 1
    assert len(tbl_facts.read()) == 1
    assert len(tbl_knowledge.read()) == 1
    assert len(tbl_content.read()) == 1
    assert len(tbl_overrides.read()) == 1
    assert len(tbl_errors.read()) == 1
    assert len(tbl_curation.read()) == 1
    assert len(tbl_evaluation.read()) == 1
    assert len(tbl_reviewer.read()) == 1

    # Test Source delete triggers Chunk, Mapping, Fact, Error cascades, and local file cleanup
    print("Testing delete of Source...")
    tbl_sources.delete("id", source_id)
    
    # Verify local file is unlinked
    assert not dummy_filepath.exists()
    
    # Verify cascades
    assert len(tbl_sources.read()) == 0
    assert len(tbl_chunks.read()) == 0
    assert len(tbl_mappings.read()) == 0
    assert len(tbl_facts.read()) == 0
    assert len(tbl_errors.read()) == 0

    # Clean up and re-insert for topic cascade testing
    tbl_sources.write([
        Source(id=source_id, title="Src 1", source_type=SourceType.pdf, local_path=dummy_filename, trust_score=5.0)
    ])
    tbl_chunks.write([
        ContentChunk(id=chunk_id, source_id=source_id, chunk_text="Chunk text", chunk_number=1)
    ])
    tbl_mappings.write([
        SourceToTopicMapping(id=str(uuid.uuid4()), source_id=source_id, chunk_id=chunk_id, topic_id=topic_id)
    ])
    tbl_facts.write([
        FactExtraction(
            id=str(uuid.uuid4()), topic_id=topic_id, source_id=source_id, chunk_id=chunk_id,
            field_name="definition", field_value={"definition": "def"},
            schema_version="1", prompt_version="1", extraction_model="model"
        )
    ])
    tbl_errors.write([
        ExtractionError(id=str(uuid.uuid4()), topic_id=topic_id, source_id=source_id, chunk_id=chunk_id, error_type="ERR", error_detail="detail")
    ])

    # Test Topic delete triggers cascades across all 9 dependent tables
    print("Testing delete of SyllabusTopic...")
    tbl_topics.delete("id", topic_id)
    
    assert len(tbl_topics.read()) == 0
    assert len(tbl_mappings.read()) == 0
    assert len(tbl_facts.read()) == 0
    assert len(tbl_knowledge.read()) == 0
    assert len(tbl_content.read()) == 0
    assert len(tbl_overrides.read()) == 0
    assert len(tbl_errors.read()) == 0
    assert len(tbl_curation.read()) == 0
    assert len(tbl_evaluation.read()) == 0
    assert len(tbl_reviewer.read()) == 0


def test_local_json_override_history_logging(tmp_path, monkeypatch):
    """Test Reviewer Override History (DI-10) Local JSON Fallback logging."""
    overrides_path = tmp_path / "knowledge_overrides.json"
    history_path = tmp_path / "knowledge_override_history.json"

    def mock_get_table(name, model, settings=None):
        if name == "knowledge_overrides":
            return JsonTable(overrides_path, model, name=name)
        elif name == "knowledge_override_history":
            return JsonTable(history_path, model, name=name)
        raise ValueError(f"Unknown mock table name: {name}")

    monkeypatch.setattr("dashboard.serve.get_table", mock_get_table)

    topic_id = str(uuid.uuid4())
    reviewer_id = "tester_reviewer"

    # Step 1: Save new override
    save_knowledge_overrides(
        topic_id=topic_id,
        reviewer_id=reviewer_id,
        edited_content={"definition": "Updated Definition"},
        raw_content={"definition": "Original Definition"},
        note="Setting definition override"
    )

    # Assert override is written
    tbl_overrides = mock_get_table("knowledge_overrides", KnowledgeOverride)
    overrides = tbl_overrides.read()
    assert len(overrides) == 1
    assert overrides[0].corrected_value == "Updated Definition"

    # Assert history record is written
    tbl_history = mock_get_table("knowledge_override_history", KnowledgeOverrideHistory)
    history = tbl_history.read()
    assert len(history) == 1
    assert history[0].override_id == overrides[0].id
    assert history[0].field_name == "definition"
    assert history[0].old_value == "Original Definition"
    assert history[0].new_value == "Updated Definition"
    assert history[0].reviewer_id == reviewer_id

    # Step 2: Edit/update existing override
    save_knowledge_overrides(
        topic_id=topic_id,
        reviewer_id=reviewer_id,
        edited_content={"definition": "Second Update Definition"},
        raw_content={"definition": "Original Definition"},
        note="Updating definition override again"
    )

    overrides = tbl_overrides.read()
    assert len(overrides) == 1
    assert overrides[0].corrected_value == "Second Update Definition"

    history = tbl_history.read()
    assert len(history) == 2
    assert history[1].old_value == "Updated Definition"
    assert history[1].new_value == "Second Update Definition"

    # Step 3: Deactivate override (revert back to original value)
    save_knowledge_overrides(
        topic_id=topic_id,
        reviewer_id=reviewer_id,
        edited_content={"definition": "Original Definition"},
        raw_content={"definition": "Original Definition"},
        note="Reverting override"
    )

    overrides = tbl_overrides.read()
    assert len(overrides) == 1
    assert overrides[0].is_active is False

    history = tbl_history.read()
    assert len(history) == 3
    assert history[2].old_value == "Second Update Definition"
    assert history[2].new_value is None  # None represents deactivation


def test_database_override_history_trigger():
    """Test Postgres triggers for Reviewer Override History (DI-10)."""
    if not db_url:
        pytest.skip("Database checks skipped: no DATABASE_URL configured.")

    print("\nConnecting to database...")
    try:
        conn = psycopg2.connect(db_url)
    except psycopg2.OperationalError as e:
        pytest.skip(f"Database checks skipped: connection failed: {e}")
    conn.autocommit = True
    cursor = conn.cursor()

    topic_id = str(uuid.uuid4())
    override_id = str(uuid.uuid4())
    reviewer_id = "db_tester"

    try:
        # Create a syllabus topic to avoid FK issues
        cursor.execute(
            "INSERT INTO syllabus_topics (id, chapter, topic_name, topic_type, status) "
            "VALUES (%s, 'Chapter 1', 'DB Trigger Topic', 'concept', 'completed');",
            (topic_id,)
        )

        # 1. Test insertion trigger
        cursor.execute(
            "INSERT INTO knowledge_overrides (id, topic_id, field_name, original_value, corrected_value, correction_note, reviewer_id, is_active) "
            "VALUES (%s, %s, 'definition', '\"old_def\"'::jsonb, '\"new_def\"'::jsonb, 'Note 1', %s, true);",
            (override_id, topic_id, reviewer_id)
        )

        cursor.execute("SELECT * FROM knowledge_override_history WHERE override_id = %s;", (override_id,))
        rows = cursor.fetchall()
        assert len(rows) == 1, "Override history record was not created on insert!"
        
        # Check values: columns: id, override_id, topic_id, field_name, old_value, new_value, reviewer_id, changed_at
        # Let's query matching values
        cursor.execute(
            "SELECT old_value, new_value, reviewer_id FROM knowledge_override_history WHERE override_id = %s;",
            (override_id,)
        )
        old_val, new_val, rev_id = cursor.fetchone()
        assert old_val == "old_def"
        assert new_val == "new_def"
        assert rev_id == reviewer_id

        # 2. Test update trigger
        cursor.execute(
            "UPDATE knowledge_overrides SET corrected_value = '\"updated_def\"'::jsonb WHERE id = %s;",
            (override_id,)
        )

        cursor.execute("SELECT old_value, new_value FROM knowledge_override_history WHERE override_id = %s ORDER BY changed_at DESC;", (override_id,))
        history_rows = cursor.fetchall()
        assert len(history_rows) == 2, "Second history record was not created on update!"
        
        # The latest one should be first or last based on ORDER BY changed_at DESC (latest is first)
        assert history_rows[0][0] == "new_def"
        assert history_rows[0][1] == "updated_def"

        # 3. Test deactivation trigger
        cursor.execute(
            "UPDATE knowledge_overrides SET is_active = false WHERE id = %s;",
            (override_id,)
        )

        cursor.execute("SELECT old_value, new_value FROM knowledge_override_history WHERE override_id = %s ORDER BY changed_at DESC;", (override_id,))
        history_rows = cursor.fetchall()
        assert len(history_rows) == 3, "Third history record was not created on deactivation!"
        
        assert history_rows[0][0] == "updated_def"
        assert history_rows[0][1] is None  # None represents deactivation

    finally:
        # Cleanup
        cursor.execute("DELETE FROM knowledge_override_history WHERE topic_id = %s;", (topic_id,))
        cursor.execute("DELETE FROM knowledge_overrides WHERE topic_id = %s;", (topic_id,))
        cursor.execute("DELETE FROM syllabus_topics WHERE id = %s;", (topic_id,))
        cursor.close()
        conn.close()
