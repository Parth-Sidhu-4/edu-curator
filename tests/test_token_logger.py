"""Unit tests for token_logger and batch extraction (no real LLM calls)."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from edu_curator.extraction import extract_concept_batch, extract_topic_batched
from edu_curator.llm import ChatResult
from edu_curator.schemas import (
    ContentChunk,
    ProcessingStatus,
    Source,
    SourceType,
    SyllabusTopic,
    TopicType,
)
from edu_curator.token_logger import log_usage, summarise_usage


def _now():
    return datetime.now(UTC)


def _make_objects():
    topic = SyllabusTopic(
        id="t1",
        chapter="Test",
        topic_name="Test Topic",
        topic_type=TopicType.concept,
        status=ProcessingStatus.pending,
    )
    source = Source(
        id="s1",
        title="Test Source",
        source_type=SourceType.website,
        trust_score=8,
        topic_ids=["t1"],
        created_at=_now(),
    )
    chunks = [
        ContentChunk(
            id="c1", source_id="s1", chunk_text="Chunk one.", chunk_number=1, created_at=_now()
        ),
        ContentChunk(
            id="c2", source_id="s1", chunk_text="Chunk two.", chunk_number=2, created_at=_now()
        ),
    ]
    return topic, source, chunks


# ---------------------------------------------------------------------------
# Token logger tests
# ---------------------------------------------------------------------------


@patch("edu_curator.config.load_settings")
def test_log_and_summarise(mock_load_settings):
    mock_settings = MagicMock()
    mock_settings.supabase_url = None
    mock_settings.supabase_key = None
    mock_load_settings.return_value = mock_settings

    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)

        r1 = ChatResult(content="{}", prompt_tokens=300, completion_tokens=60)
        r2 = ChatResult(content="{}", prompt_tokens=500, completion_tokens=120)
        r3 = ChatResult(content="{}", prompt_tokens=200, completion_tokens=40)

        log_usage(log_dir, r1, stage="extract_batch", model="llama3-8b", topic_sn=3)
        log_usage(log_dir, r2, stage="generate", model="gpt-oss-120b", topic_sn=3)
        log_usage(log_dir, r3, stage="consistency", model="gpt-oss-120b", topic_sn=3)

        lines = (log_dir / "token_usage.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"

        first = json.loads(lines[0])
        assert first["stage"] == "extract_batch"
        assert first["prompt_tokens"] == 300
        assert first["total_tokens"] == 360

        s = summarise_usage(log_dir)
        assert s["total_calls"] == 3
        assert s["total_prompt"] == 1000
        assert s["total_completion"] == 220
        assert s["total_tokens"] == 1220
        assert "extract_batch" in s["by_stage"]
        assert "generate" in s["by_stage"]
        assert "3" in s["by_topic_sn"]

        print("PASS: test_log_and_summarise")


@patch("edu_curator.config.load_settings")
def test_summarise_empty(mock_load_settings):
    mock_settings = MagicMock()
    mock_settings.supabase_url = None
    mock_settings.supabase_key = None
    mock_load_settings.return_value = mock_settings

    with tempfile.TemporaryDirectory() as tmp:
        s = summarise_usage(Path(tmp))
        assert s["total_calls"] == 0
        assert s["total_tokens"] == 0
        print("PASS: test_summarise_empty")


@patch("edu_curator.config.load_settings")
def test_no_log_when_tokens_none(mock_load_settings):
    """If provider returns no token info, nothing is logged."""
    mock_settings = MagicMock()
    mock_settings.supabase_url = None
    mock_settings.supabase_key = None
    mock_load_settings.return_value = mock_settings

    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        r = ChatResult(content="{}", prompt_tokens=None, completion_tokens=None)
        log_usage(log_dir, r, stage="extract", model="m", topic_sn=1)
        assert not (log_dir / "token_usage.jsonl").exists()
        print("PASS: test_no_log_when_tokens_none")


# ---------------------------------------------------------------------------
# Batch extraction tests
# ---------------------------------------------------------------------------


def test_batch_two_chunks():
    topic, source, chunks = _make_objects()
    fake_response = {
        "results": {
            "c1": {
                "definition": "Def 1",
                "purpose": "P 1",
                "key_properties": ["A"],
                "benefits": ["B"],
                "limitations": [],
                "common_misconceptions": [],
                "related_topics": [],
            },
            "c2": {
                "definition": "Def 2",
                "purpose": "P 2",
                "key_properties": [],
                "benefits": [],
                "limitations": ["L"],
                "common_misconceptions": [],
                "related_topics": ["R"],
            },
        }
    }
    mock_result = ChatResult(
        content=json.dumps(fake_response), prompt_tokens=400, completion_tokens=80
    )
    settings = MagicMock()
    settings.extraction_model = "test-model"

    with patch("edu_curator.extraction.chat_json", return_value=mock_result):
        facts, failed = extract_concept_batch(settings, topic, source, chunks)

    assert len(facts) == 14, f"Expected 14 (7 fields x 2 chunks), got {len(facts)}"
    assert failed == []
    print("PASS: test_batch_two_chunks")


def test_batch_partial_failure_fallback():
    """If c2 has bad data, extract_topic_batched should fall back to single for c2."""
    topic, source, chunks = _make_objects()

    # First call: batch — c2 has invalid schema (missing required type)
    batch_response = {
        "results": {
            "c1": {
                "definition": "Def 1",
                "purpose": "P 1",
                "key_properties": [],
                "benefits": [],
                "limitations": [],
                "common_misconceptions": [],
                "related_topics": [],
            },
            "c2": "not a dict at all",  # invalid — triggers fallback
        }
    }
    # Second call: single for c2
    single_response = {
        "definition": "Def 2 fallback",
        "purpose": "P 2",
        "key_properties": [],
        "benefits": [],
        "limitations": [],
        "common_misconceptions": [],
        "related_topics": [],
    }

    call_responses = [
        ChatResult(content=json.dumps(batch_response), prompt_tokens=500, completion_tokens=90),
        ChatResult(content=json.dumps(single_response), prompt_tokens=200, completion_tokens=40),
    ]
    settings = MagicMock()
    settings.extraction_model = "test-model"
    source_by_id = {source.id: source}

    with patch("edu_curator.extraction.chat_json", side_effect=call_responses):
        facts, errors = extract_topic_batched(
            settings=settings,
            topic=topic,
            chunks_to_extract=chunks,
            source_by_id=source_by_id,
            batch_size=5,
        )

    # c1 -> 7 facts, c2 fallback -> 7 facts = 14 total
    assert len(facts) == 14, f"Expected 14 facts, got {len(facts)}"
    assert len(errors) == 0, f"Expected 0 errors, got {len(errors)}"
    print("PASS: test_batch_partial_failure_fallback")


if __name__ == "__main__":
    test_log_and_summarise()
    test_summarise_empty()
    test_no_log_when_tokens_none()
    test_batch_two_chunks()
    test_batch_partial_failure_fallback()
    print("\nAll tests passed!")
