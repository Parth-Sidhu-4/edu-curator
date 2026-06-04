from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TopicType(StrEnum):
    concept = "concept"
    command = "command"
    tool = "tool"
    architecture = "architecture"
    process = "process"


class SourceType(StrEnum):
    website = "website"
    pdf = "pdf"
    image = "image"
    docx = "docx"
    book = "book"
    internal_document = "internal_document"
    text = "text"


class ProcessingStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ReviewStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    needs_regeneration = "needs_regeneration"


class SyllabusTopic(StrictModel):
    id: str
    chapter: str
    topic_name: str
    topic_type: TopicType
    keywords: list[str] = Field(default_factory=list)
    difficulty_level: str | None = None
    status: ProcessingStatus = ProcessingStatus.pending
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Source(StrictModel):
    id: str
    title: str
    source_type: SourceType
    url: str | None = None
    local_path: str | None = None
    trust_score: float = Field(default=5.0, ge=1.0, le=10.0)
    auto_trust_score: float | None = None
    license_type: str | None = None
    publication_date: date | None = None
    owner: str | None = None
    topic_ids: list[str] = Field(default_factory=list)
    is_active: bool = True
    content_hash: str | None = None
    last_crawled: datetime | None = None
    crawl_status: ProcessingStatus | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("local_path", "url")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class NormalizedDocument(StrictModel):
    source_id: str
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentChunk(StrictModel):
    id: str
    source_id: str
    chunk_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    chunk_number: int
    created_at: datetime | None = None

    @field_validator("embedding", mode="before")
    @classmethod
    def parse_vector_string(cls, value: Any) -> list[float] | None:
        if isinstance(value, str):
            cleaned = value.strip("[]")
            if not cleaned:
                return []
            return [float(x) for x in cleaned.split(",")]
        return value


class SourceToTopicMapping(StrictModel):
    id: str
    source_id: str
    chunk_id: str
    topic_id: str
    vector_score: float | None = None
    reranker_score: float | None = None
    is_active: bool = True
    created_at: datetime | None = None


class Parameter(StrictModel):
    name: str
    description: str
    required: bool = False


class CommandExample(StrictModel):
    command: str
    description: str


class ConceptExtraction(StrictModel):
    definition: str | None = None
    purpose: str | None = None
    key_properties: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1.0)


class CommandExtraction(StrictModel):
    syntax: str | None = None
    parameters: list[Parameter] = Field(default_factory=list)
    examples: list[CommandExample] = Field(default_factory=list)
    expected_output: str | None = None
    common_errors: list[str] = Field(default_factory=list)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1.0)


class ToolExtraction(StrictModel):
    overview: str | None = None
    features: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    related_tools: list[str] = Field(default_factory=list)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1.0)


class ArchitectureExtraction(StrictModel):
    overview: str | None = None
    components: list[str] = Field(default_factory=list)
    interactions: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1.0)


class ProcessExtraction(StrictModel):
    overview: str | None = None
    steps: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1.0)


ExtractionValue = (
    ConceptExtraction
    | CommandExtraction
    | ToolExtraction
    | ArchitectureExtraction
    | ProcessExtraction
    | dict[str, Any]
)


class FactExtraction(StrictModel):
    id: str
    topic_id: str
    source_id: str
    chunk_id: str
    field_name: str
    field_value: dict[str, Any]
    schema_version: str
    prompt_version: str
    extraction_model: str
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    status: ProcessingStatus = ProcessingStatus.completed
    created_at: datetime | None = None


class CanonicalField(StrictModel):
    canonical_value: Any = None
    confidence: float | None = Field(default=None, ge=0, le=100)
    sources: list[str] = Field(default_factory=list)
    alternative_values: list[dict[str, Any]] = Field(default_factory=list)
    resolution_reason: str | None = None
    status: Literal["resolved", "needs_review", "conflict_detected", "missing"] = "resolved"


class TopicKnowledge(StrictModel):
    id: str
    topic_id: str
    schema_version: str
    knowledge: dict[str, CanonicalField | list[dict[str, Any]] | Any]
    sources_used: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=100)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TopicContent(StrictModel):
    id: str
    topic_id: str
    content_json: dict[str, Any]
    schema_version: str | None = None
    generation_model: str | None = None
    sources_used: list[str] = Field(default_factory=list)
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    consistency_check_status: bool | None = None
    consistency_check_flags: dict[str, Any] | None = None
    review_status: ReviewStatus = ReviewStatus.pending
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    published_at: datetime | None = None
    inputs_hash: str | None = None
    version: int = 1
    created_at: datetime | None = None


class ExtractionError(StrictModel):
    id: str
    topic_id: str | None = None
    source_id: str | None = None
    chunk_id: str | None = None
    error_type: str
    error_detail: str
    retry_count: int = 0
    resolved: bool = False
    created_at: datetime | None = None


class TokenUsageRecord(StrictModel):
    id: str
    ts: datetime
    stage: str
    topic_sn: int | None = None
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CurationJob(StrictModel):
    id: str
    topic_id: str
    status: str = "pending"
    logs: str = ""
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EvaluationJob(StrictModel):
    id: str
    topic_id: str
    status: str = "pending"
    logs: str = ""
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeOverride(StrictModel):
    id: str
    topic_id: str
    field_name: str
    original_value: Any = None
    corrected_value: Any
    correction_note: str | None = None
    reviewer_id: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewerActivity(StrictModel):
    id: str
    topic_id: str
    content_id: str | None = None
    reviewer_id: str | None = None
    action: str
    review_notes: str | None = None
    created_at: datetime | None = None


class KnowledgeOverrideHistory(StrictModel):
    id: str
    override_id: str
    topic_id: str
    field_name: str
    old_value: Any = None
    new_value: Any
    reviewer_id: str | None = None
    changed_at: datetime | None = None


class LLMTrace(StrictModel):
    id: str
    ts: datetime | None = None
    stage: str | None = None
    topic_sn: int | None = None
    model: str
    prompt: list[dict[str, Any]] | dict[str, Any]
    response: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None


class EvaluationResult(StrictModel):
    id: str
    topic_id: str
    faithfulness_score: float | None = None
    completeness_score: float | None = None
    faithfulness_reasoning: str | None = None
    completeness_reasoning: str | None = None
    created_at: datetime | None = None


