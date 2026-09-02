"""Execution and regression orchestration for reproducible evaluation cases."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .models import AgentRunOutput, EvalCase, EvalResult, EvalTask, EvaluationReport, EvaluationStatus, SpanKind, TraceStatus
from .scorers import p95, pass_at_k, score_run
from .store import EvaluationStore
from .trace import TraceRecorder

Executor = Callable[[EvalCase, TraceRecorder], AgentRunOutput | dict[str, Any] | Awaitable[AgentRunOutput | dict[str, Any]]]


class EvaluationRunner:
    def __init__(self, store: EvaluationStore | None = None, executor: Executor | None = None):
        self.store = store or EvaluationStore()
        self.executor = executor

    async def run_case(self, task: EvalTask, case: EvalCase, *, run_index: int = 1) -> EvalResult:
        if not self.executor:
            raise RuntimeError("no evaluation executor configured")
        recorder = TraceRecorder(name=f"eval:{task.name}", metadata={"prompt": case.prompt, "case_id": case.case_id, "task_id": task.task_id})
        workflow_span = recorder.start_span(
            f"workflow:{task.name}", SpanKind.WORKFLOW,
            input_messages=[{"role": "user", "content": case.prompt}],
            attributes={"case_id": case.case_id},
        )
        started = time.perf_counter()
        try:
            with recorder:
                value = self.executor(case, recorder)
                value = await value if inspect.isawaitable(value) else value
            output = value if isinstance(value, AgentRunOutput) else AgentRunOutput.model_validate(value or {})
        except Exception as exc:
            recorder.finish_span(workflow_span, status=TraceStatus.ERROR, error=f"{type(exc).__name__}: {exc}")
            output = AgentRunOutput(trace=recorder.to_envelope(), metadata={"exception": f"{type(exc).__name__}: {exc}"})
        else:
            recorder.finish_span(workflow_span, attributes={"duration_ms": (time.perf_counter() - started) * 1000})
        if output.trace is None:
            output.trace = recorder.to_envelope()
        result = score_run(task.task_id, case, output, latency_ms=(time.perf_counter() - started) * 1000, run_index=run_index)
        if output.metadata.get("exception"):
            result.status = EvaluationStatus.FAILED
            result.task_success = False
            result.failure_reason = output.metadata["exception"]
        self.store.upsert("results", result)
        self.store.upsert("traces", output.trace)
        return result

    async def run_task(self, task: EvalTask, cases: list[EvalCase]) -> EvaluationReport:
        task.status = EvaluationStatus.RUNNING
        self.store.upsert("tasks", task)
        semaphore = asyncio.Semaphore(task.generation_config.concurrency)

        async def one(case: EvalCase, run_index: int) -> EvalResult:
            async with semaphore:
                return await self.run_case(task, case, run_index=run_index)

        results: list[EvalResult] = []
        repeats = int(task.metadata.get("repeats", 1))
        for run_index in range(1, repeats + 1):
            results.extend(await asyncio.gather(*(one(case, run_index) for case in cases)))
        latencies = [row.latency_ms for row in results if row.latency_ms is not None]
        supported = [row.citation_support_rate for row in results if row.citation_support_rate is not None]
        precisions = [row.tool_precision for row in results if row.tool_precision is not None]
        recalls = [row.tool_recall for row in results if row.tool_recall is not None]
        report = EvaluationReport(
            task_id=task.task_id,
            result_count=len(results),
            task_success_rate=sum(row.task_success for row in results) / len(results) if results else 0.0,
            average_latency_ms=sum(latencies) / len(latencies) if latencies else None,
            p95_latency_ms=p95(latencies),
            average_outline_coverage=sum(row.outline_coverage for row in results) / len(results) if results else 0.0,
            average_citation_support_rate=sum(supported) / len(supported) if supported else None,
            average_tool_precision=sum(precisions) / len(precisions) if precisions else None,
            average_tool_recall=sum(recalls) / len(recalls) if recalls else None,
            pass_k=pass_at_k(results, repeats) if repeats > 1 else None,
            results=results,
        )
        task.status = EvaluationStatus.COMPLETED
        self.store.upsert("tasks", task)
        self.store.upsert("reports", report)
        return report
