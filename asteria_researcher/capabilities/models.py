"""Provider-neutral contracts for task intent, skills, agents, and tools."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskIntent(str, Enum):
    """High-level intent inferred from the user's natural-language request."""

    ACADEMIC_RESEARCH = "academic_research"
    OFFLINE_RAG = "offline_rag"
    EXPERIMENT = "experiment"
    DATA_ANALYSIS = "data_analysis"
    COMPANY_RESEARCH = "company_research"


class SourceMode(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    HYBRID = "hybrid"


class CapabilityModel(BaseModel):
    """Shared validation policy for capability declarations."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ToolSpec(CapabilityModel):
    """A declarative description of a tool exposed to an Agent or Skill."""

    id: str
    name: str
    description: str = ""
    transport: Literal["in_process", "mcp", "worker"] = "in_process"
    permission: Literal["read", "write", "execute", "network"] = "read"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1, le=86_400)
    supports_retry: bool = True


class AgentProfile(CapabilityModel):
    """Role, delegation boundary, and allowed capabilities of a Sub-Agent."""

    id: str
    name: str
    role: str
    implementation: str
    description: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_skills: list[str] = Field(default_factory=list)
    can_delegate: bool = False
    max_iterations: int = Field(default=3, ge=1, le=100)
    timeout_seconds: int = Field(default=600, ge=1, le=86_400)
    status: Literal["active", "partial", "planned"] = "partial"


class SkillManifest(CapabilityModel):
    """Method-level contract for a reusable capability."""

    id: str
    name: str
    version: str = "0.1.0"
    description: str
    implementation: str
    intents: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    validators: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = Field(default=3, ge=1, le=100)
    status: Literal["active", "partial", "planned"] = "partial"

    @field_validator("intents", "capabilities", "allowed_agents", "allowed_tools", "validators")
    @classmethod
    def reject_blank_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("capability identifiers cannot be blank")
        return value


class IntentResult(CapabilityModel):
    """Structured result returned by an intent classifier or fallback router."""

    intent: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    deliverable: str = "research_report"
    source_mode: SourceMode = SourceMode.ONLINE
    required_skills: list[str] = Field(default_factory=list)
    rationale: str = ""
    needs_clarification: bool = False


class TaskSpec(CapabilityModel):
    """Canonical task input passed from the API to an execution runtime."""

    task_id: str = Field(default_factory=lambda: uuid4().hex)
    user_request: str = Field(min_length=1)
    intent: str = TaskIntent.ACADEMIC_RESEARCH.value
    deliverable: str = "research_report"
    source_mode: SourceMode = SourceMode.ONLINE
    required_skills: list[str] = Field(default_factory=list)
    project_id: str | None = None
    workspace_id: str | None = None
    host_profile_id: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_intent(
        cls,
        user_request: str,
        result: IntentResult,
        **kwargs: Any,
    ) -> "TaskSpec":
        """Build a task without exposing intent selection to the user."""

        return cls(
            user_request=user_request,
            intent=result.intent,
            deliverable=result.deliverable,
            source_mode=result.source_mode,
            required_skills=list(dict.fromkeys(result.required_skills)),
            metadata={"intent_confidence": result.confidence, "intent_rationale": result.rationale},
            **kwargs,
        )
