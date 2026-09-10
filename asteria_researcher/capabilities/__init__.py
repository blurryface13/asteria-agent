"""Capability contracts for intent-driven research tasks.

The capability layer deliberately contains no provider or web-runtime imports.
It is safe to use from the API, CLI, tests, and future workers.
"""

from .models import (
    AgentProfile,
    IntentResult,
    SkillManifest,
    SourceMode,
    TaskIntent,
    TaskSpec,
    ToolSpec,
)
from .registry import CapabilityRegistry, build_default_registry
from .router import IntentRouter

__all__ = [
    "AgentProfile",
    "CapabilityRegistry",
    "IntentResult",
    "IntentRouter",
    "SkillManifest",
    "SourceMode",
    "TaskIntent",
    "TaskSpec",
    "ToolSpec",
    "build_default_registry",
]
