from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class JsonTable(Generic[T]):
    def __init__(self, path: Path, model: type[T], name: str = "") -> None:
        self.path = path
        self.model = model
        self.name = name

    def read(self, limit: int | None = None, offset: int | None = None, filters: dict[str, Any] | None = None) -> list[T]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        rows = [self.model.model_validate(item) for item in data]
        if filters:
            filtered_rows = []
            for r in rows:
                match = True
                for col, val in filters.items():
                    if str(getattr(r, col, "")) != str(val):
                        match = False
                        break
                if match:
                    filtered_rows.append(r)
            rows = filtered_rows
        start = offset or 0
        end = (start + limit) if limit is not None else None
        return rows[start:end]

    def write(self, rows: list[T]) -> list[T]:
        import os
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [row.model_dump(mode="json") for row in rows]
        tmp_path = self.path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(str(tmp_path), str(self.path))
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        return rows

    def delete(self, field: str, value: Any) -> None:
        existing = self.read()
        to_delete = [r for r in existing if str(getattr(r, field, "")) == str(value)]
        updated = [r for r in existing if str(getattr(r, field, "")) != str(value)]
        self.write(updated)

        for r in to_delete:
            # 1. Local File Cleanup for Sources
            if self.name == "sources":
                local_path_val = getattr(r, "local_path", None)
                if local_path_val and not str(local_path_val).startswith("supabase://"):
                    workspace_root = Path(__file__).resolve().parents[2]
                    file_path = workspace_root / local_path_val
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                        except Exception as e:
                            print(f"[JsonTable.delete] Error deleting file {file_path}: {e}")

            # 2. Cascading deletes
            if self.name == "syllabus_topics":
                topic_id = getattr(r, "id", None)
                if topic_id:
                    from edu_curator.storage import get_table
                    from edu_curator.schemas import (
                        SourceToTopicMapping, FactExtraction, TopicKnowledge, TopicContent,
                        KnowledgeOverride, ExtractionError, CurationJob, ReviewerActivity,
                        EvaluationJob
                    )
                    for sub_name, sub_model in [
                        ("source_to_topic_mapping", SourceToTopicMapping),
                        ("fact_extractions", FactExtraction),
                        ("topic_knowledge", TopicKnowledge),
                        ("topic_content", TopicContent),
                        ("knowledge_overrides", KnowledgeOverride),
                        ("extraction_errors", ExtractionError),
                        ("curation_jobs", CurationJob),
                        ("evaluation_jobs", EvaluationJob),
                        ("reviewer_activity", ReviewerActivity)
                    ]:
                        try:
                            tbl = get_table(sub_name, sub_model)
                            tbl.delete("topic_id", topic_id)
                        except Exception as e:
                            print(f"[JsonTable.delete] Cascade topic_id={topic_id} to {sub_name} failed: {e}")

            elif self.name == "sources":
                source_id = getattr(r, "id", None)
                if source_id:
                    from edu_curator.storage import get_table
                    from edu_curator.schemas import (
                        ContentChunk, SourceToTopicMapping, FactExtraction, ExtractionError
                    )
                    for sub_name, sub_model in [
                        ("content_chunks", ContentChunk),
                        ("source_to_topic_mapping", SourceToTopicMapping),
                        ("fact_extractions", FactExtraction),
                        ("extraction_errors", ExtractionError)
                    ]:
                        try:
                            tbl = get_table(sub_name, sub_model)
                            tbl.delete("source_id", source_id)
                        except Exception as e:
                            print(f"[JsonTable.delete] Cascade source_id={source_id} to {sub_name} failed: {e}")

            elif self.name == "content_chunks":
                chunk_id = getattr(r, "id", None)
                if chunk_id:
                    from edu_curator.storage import get_table
                    from edu_curator.schemas import (
                        SourceToTopicMapping, FactExtraction, ExtractionError
                    )
                    for sub_name, sub_model in [
                        ("source_to_topic_mapping", SourceToTopicMapping),
                        ("fact_extractions", FactExtraction),
                        ("extraction_errors", ExtractionError)
                    ]:
                        try:
                            tbl = get_table(sub_name, sub_model)
                            tbl.delete("chunk_id", chunk_id)
                        except Exception as e:
                            print(f"[JsonTable.delete] Cascade chunk_id={chunk_id} to {sub_name} failed: {e}")



def clean_null_chars(val):
    if isinstance(val, str):
        return val.replace("\u0000", "")
    elif isinstance(val, dict):
        return {k: clean_null_chars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_null_chars(item) for item in val]
    return val


class SupabaseTable(Generic[T]):
    def __init__(self, table_name: str, model: type[T], supabase_client) -> None:
        self.table_name = table_name
        self.model = model
        self.supabase = supabase_client

    def read(self, limit: int | None = None, offset: int | None = None, filters: dict[str, Any] | None = None) -> list[T]:
        if not self.supabase:
            return []
        # Support pagination to prevent memory crashes as rows grow
        query = self.supabase.table(self.table_name).select("*")
        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)
        response = query.execute()
        return [self.model.model_validate(item) for item in response.data]

    def write(self, rows: list[T]) -> list[Any]:
        if not self.supabase or not rows:
            return []
        payload = [row.model_dump(mode="json") for row in rows]
        payload = clean_null_chars(payload)
        # upsert replaces existing rows based on Primary Key
        res = self.supabase.table(self.table_name).upsert(payload).execute()
        return res.data if hasattr(res, "data") else []

    def delete(self, field: str, value: Any) -> None:
        if not self.supabase:
            return
        self.supabase.table(self.table_name).delete().eq(field, str(value)).execute()


_supabase_client_cache = {}


def get_table(name: str, model: type[T], settings=None) -> JsonTable[T] | SupabaseTable[T]:
    """Factory to get the correct storage backend.

    If SUPABASE_URL and SUPABASE_KEY are in settings, returns a SupabaseTable.
    Otherwise, returns a JsonTable pointing to data/.../name.json.
    """
    if settings and settings.supabase_url and settings.supabase_key:
        try:
            from supabase import create_client

            cache_key = (settings.supabase_url, settings.supabase_key)
            if cache_key not in _supabase_client_cache:
                _supabase_client_cache[cache_key] = create_client(settings.supabase_url, settings.supabase_key)
            supabase = _supabase_client_cache[cache_key]
            db_name = "normalized_documents" if name == "documents" else name
            return SupabaseTable(db_name, model, supabase)
        except ImportError:
            pass

    # Fallback to local JSON
    root = Path(__file__).resolve().parents[2] / "data"

    # Map table name to standard local path for MVP
    path_map = {
        "syllabus_topics": root / "seed" / "syllabus_topics.json",
        "sources": root / "seed" / "sources.json",
        "content_chunks": root / "chunks" / "content_chunks.json",
        "source_to_topic_mapping": root / "mappings" / "source_to_topic_mapping.json",
        "fact_extractions": root / "extractions" / "fact_extractions.json",
        "extraction_errors": root / "extractions" / "extraction_errors.json",
        "topic_knowledge": root / "knowledge" / "topic_knowledge.json",
        "topic_content": root / "generated" / "topic_content.json",
        "llm_traces": root / "logs" / "llm_traces.json",
        "evaluation_results": root / "evaluation_results.json",
        "token_usage": root / "token_usage.json",
        "curation_jobs": root / "curation_jobs.json",
        "evaluation_jobs": root / "evaluation_jobs.json",
        "knowledge_overrides": root / "knowledge_overrides.json",
        "reviewer_activity": root / "reviewer_activity.json",
        "knowledge_override_history": root / "knowledge_override_history.json",
    }


    path = path_map.get(name, root / f"{name}.json")
    return JsonTable(path, model, name=name)

