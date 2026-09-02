"""Evaluation primitives for reproducible research-agent runs.

The package deliberately keeps the evaluation boundary independent from the
research workflow.  Asteria can emit native traces, while the same models can
also ingest OpenTelemetry-style JSONL exported by another agent runtime.
"""

from .badcase import BadCaseAnalyzer, DimensionCatalog, trace_to_seed
from .models import (
    AgentRunOutput,
    BadCase,
    EvalCase,
    EvalResult,
    EvalTask,
    GeneratedCase,
    SeedCase,
    TraceEnvelope,
    TraceSpan,
)
from .runner import EvaluationRunner
from .store import EvaluationStore
from .trace import TraceIngestor, TraceRecorder
from .asteria_executor import build_asteria_executor

__all__ = [
    "AgentRunOutput",
    "BadCase",
    "BadCaseAnalyzer",
    "DimensionCatalog",
    "EvalCase",
    "EvalResult",
    "EvalTask",
    "EvaluationRunner",
    "EvaluationStore",
    "build_asteria_executor",
    "GeneratedCase",
    "SeedCase",
    "TraceEnvelope",
    "TraceIngestor",
    "TraceRecorder",
    "TraceSpan",
    "trace_to_seed",
]
