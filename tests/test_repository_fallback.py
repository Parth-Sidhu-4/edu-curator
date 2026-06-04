import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from pydantic import BaseModel

from edu_curator.config import load_settings
from edu_curator.storage import get_table, JsonTable, SupabaseTable
from edu_curator.schemas import LLMTrace, EvaluationResult

class MockSettings:
    def __init__(self, supabase_url=None, supabase_key=None):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key

def test_repository_fallback_to_json(tmp_path):
    # Setup mock config settings with empty supabase credentials
    settings = MockSettings(supabase_url="", supabase_key="")
    
    # 1. Retrieve the tables using factory
    # Use custom path redirection by patching the path mappings in storage or testing JsonTable directly
    trace_file = tmp_path / "llm_traces.json"
    eval_file = tmp_path / "evaluation_results.json"
    
    trace_table = JsonTable(trace_file, LLMTrace, name="llm_traces")
    eval_table = JsonTable(eval_file, EvaluationResult, name="evaluation_results")
    
    # 2. Write an LLMTrace record
    trace_id = str(uuid.uuid4())
    trace_rec = LLMTrace(
        id=trace_id,
        ts=datetime.now(timezone.utc),
        stage="curation",
        topic_sn=42,
        model="gpt-4o",
        prompt=[{"role": "user", "content": "hello"}],
        response="world",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        latency_ms=120
    )
    
    trace_table.write([trace_rec])
    assert trace_file.exists()
    
    # Verify contents of JSON file
    file_data = json.loads(trace_file.read_text(encoding="utf-8"))
    assert len(file_data) == 1
    assert file_data[0]["id"] == trace_id
    assert file_data[0]["model"] == "gpt-4o"
    assert file_data[0]["prompt"] == [{"role": "user", "content": "hello"}]
    
    # Read back and validate
    read_traces = trace_table.read()
    assert len(read_traces) == 1
    assert isinstance(read_traces[0], LLMTrace)
    assert read_traces[0].id == trace_id
    assert read_traces[0].response == "world"

    # 3. Write an EvaluationResult record
    eval_id = str(uuid.uuid4())
    eval_rec = EvaluationResult(
        id=eval_id,
        topic_id=str(uuid.uuid4()),
        faithfulness_score=0.9,
        completeness_score=0.85,
        faithfulness_reasoning="Very faithful",
        completeness_reasoning="Mostly complete",
        created_at=datetime.now(timezone.utc)
    )
    
    eval_table.write([eval_rec])
    assert eval_file.exists()
    
    # Verify contents of JSON file
    file_data_eval = json.loads(eval_file.read_text(encoding="utf-8"))
    assert len(file_data_eval) == 1
    assert file_data_eval[0]["id"] == eval_id
    assert file_data_eval[0]["faithfulness_score"] == 0.9
    
    # Read back and validate
    read_evals = eval_table.read()
    assert len(read_evals) == 1
    assert isinstance(read_evals[0], EvaluationResult)
    assert read_evals[0].id == eval_id
    assert read_evals[0].completeness_score == 0.85


def test_get_table_returns_json_table_when_credentials_missing():
    # If no supabase config is provided, get_table must return JsonTable pointing to paths
    settings = MockSettings(supabase_url=None, supabase_key=None)
    
    trace_table = get_table("llm_traces", LLMTrace, settings)
    eval_table = get_table("evaluation_results", EvaluationResult, settings)
    
    assert isinstance(trace_table, JsonTable)
    assert isinstance(eval_table, JsonTable)
    assert trace_table.name == "llm_traces"
    assert eval_table.name == "evaluation_results"
