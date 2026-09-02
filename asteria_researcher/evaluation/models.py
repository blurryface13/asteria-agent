"""Pydantic models used by the evaluation and BadCase pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SpanKind(str, Enum):
    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    WORKFLOW = "workflow"
    UNKNOWN = "unknown"


class TraceStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class BadCaseStatus(str, Enum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FailureType(str, Enum):
    TOOL_ERROR = "tool_error"
    TIMEOUT = "timeout"
    LLM_ERROR = "llm_error"
    RETRIEVAL_MISS = "retrieval_miss"
    TOOL_SELECTION = "tool_selection"
    PLANNING = "planning"
    GROUNDING = "grounding"
    OUTPUT_INCOMPLETE = "output_incomplete"
    UNKNOWN = "unknown"


class EvaluationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TraceSpan(BaseModel):
    """A normalized span, compatible with native and OTel-like traces."""

    model_config = ConfigDict(extra="allow")

    trace_id: str
    span_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    parent_span_id: str | None = None
    name: str
    kind: SpanKind = SpanKind.UNKNOWN
    status: TraceStatus = TraceStatus.UNSET
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: float | None = None
    input_messages: list[dict[str, Any]] = Field(default_factory=list)
    output_messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_result: Any | None = None
    error: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


class TraceEnvelope(BaseModel):
    """One executable Agent trace and its reconstructed parent-child tree."""

    model_config = ConfigDict(extra="allow")

    trace_id: str
    name: str = "agent-run"
    root_span_id: str | None = None
    source_batch_id: str | None = None
    source_system: str | None = None
    spans: list[TraceSpan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    imported_at: datetime = Field(default_factory=utc_now)

    @property
    def roots(self) -> list[TraceSpan]:
        known = {span.span_id for span in self.spans}
        return [
            span for span in self.spans
            if not span.parent_span_id or span.parent_span_id not in known
        ]

    @property
    def agent_count(self) -> int:
        return sum(span.kind == SpanKind.AGENT for span in self.spans)

    @property
    def llm_count(self) -> int:
        return sum(span.kind == SpanKind.LLM for span in self.spans)

    @property
    def tool_count(self) -> int:
        return sum(span.kind == SpanKind.TOOL for span in self.spans)

    def children_of(self, span_id: str) -> list[TraceSpan]:
        return [span for span in self.spans if span.parent_span_id == span_id]

    def actual_tool_names(self) -> list[str]:
        return [
            span.tool_name or span.name
            for span in self.spans
            if span.kind == SpanKind.TOOL
        ]

    def user_prompt(self) -> str:
        candidates = [
            self.metadata.get("prompt"),
            self.metadata.get("query"),
            self.metadata.get("user_query"),
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value.strip()
        for span in sorted(self.spans, key=lambda item: item.start_time or utc_now()):
            for message in span.input_messages:
                if message.get("role") in {"user", "human"} and message.get("content"):
                    return str(message["content"])
        return ""


class EvalCase(BaseModel):
    """A reproducible evaluation case, suitable for a golden or seed set."""

    model_config = ConfigDict(extra="allow")

    case_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str | None = None
    prompt: str
    scenario: str = ""
    expected_sections: list[str] = Field(default_factory=list)
    expected_behavior: str = ""
    expected_tools: list[str] = Field(default_factory=list)
    required_milestones: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    reference_urls: list[str] = Field(default_factory=list)
    source_trace_id: str | None = None
    source_seed_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class SeedCase(EvalCase):
    """A human-reviewed case used as the basis for dimension expansion."""

    seed_id: str = Field(default_factory=lambda: uuid4().hex)
    library_id: str = "default"
    review_status: BadCaseStatus = BadCaseStatus.CANDIDATE
    reviewer: str | None = None
    review_note: str = ""


class BadCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    badcase_id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str
    prompt: str = ""
    scenario: str = ""
    failure_type: FailureType = FailureType.UNKNOWN
    status: BadCaseStatus = BadCaseStatus.CANDIDATE
    failure_span_ids: list[str] = Field(default_factory=list)
    failure_reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    suggested_dimensions: list[str] = Field(default_factory=list)
    suggested_expected_behavior: str = ""
    source_batch_id: str | None = None
    source_system: str | None = None
    trace_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    review_note: str = ""


class GeneratedCase(EvalCase):
    generated_id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    generation_strategy: str = "dimension_expansion"
    generation_prompt: str = ""
    quality_status: Literal["pending", "passed", "rejected", "needs_review"] = "pending"
    quality_note: str = ""
    attempt: int = 1


class GenerationConfig(BaseModel):
    concurrency: int = Field(default=1, ge=1, le=8)
    quantity_per_dimension: int = Field(default=10, ge=1, le=1000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    generate_scenario: bool = True
    strict_alignment: bool = True
    max_retries: int = Field(default=1, ge=0, le=5)
    model: str | None = None
    know_how_documents: list[str] = Field(default_factory=list)
    inline_know_how: str = ""


class EvalTask(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    case_ids: list[str] = Field(default_factory=list)
    seed_ids: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
    status: EvaluationStatus = EvaluationStatus.PENDING
    generated_case_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRunOutput(BaseModel):
    report: str = ""
    trace: TraceEnvelope | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    result_id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    case_id: str
    run_index: int = 1
    status: EvaluationStatus = EvaluationStatus.COMPLETED
    task_success: bool = False
    outline_coverage: float = 0.0
    citation_count: int = 0
    citation_support_rate: float | None = None
    tool_precision: float | None = None
    tool_recall: float | None = None
    milestone_progress: float | None = None
    latency_ms: float | None = None
    failure_type: FailureType | None = None
    failure_reason: str = ""
    report_excerpt: str = ""
    trace_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationReport(BaseModel):
    task_id: str
    result_count: int
    task_success_rate: float
    average_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    average_outline_coverage: float = 0.0
    average_citation_support_rate: float | None = None
    average_tool_precision: float | None = None
    average_tool_recall: float | None = None
    pass_k: float | None = None
    results: list[EvalResult] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)
