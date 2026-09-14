"""Durable-result Monitor adapter inspired by EchoMind's feedback contract."""

from __future__ import annotations

import math
from statistics import mean
from typing import Any


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


def _penalty(success_rate: float, latency_ms: float) -> float:
    value = 0.0
    if success_rate < 0.90:
        value += min(0.5, (0.90 - success_rate) * 2)
    if latency_ms > 3000:
        value += min(0.4, (latency_ms - 3000) / 10000)
    return round(min(value, 0.9), 4)


def aggregate_monitor(results: list[dict[str, Any]], traces: list[dict[str, Any]], *, minimum_samples: int = 10) -> dict[str, Any]:
    """Aggregate persisted evaluation records without assuming live objects.

    The returned ``monitor_penalty`` is exposed for a future same-capability
    router.  Until there are enough comparable samples, routing stays
    ``unknown`` and the adapter remains observation-only.
    """
    latencies = [float(row["latency_ms"]) for row in results if row.get("latency_ms") is not None]
    completed = [row for row in results if row.get("status") in {"completed", "failed"}]
    successes = [row for row in completed if row.get("task_success") is True]
    tool_calls = sum(sum(span.get("kind") == "tool" for span in trace.get("spans", [])) for trace in traces)
    agent_calls = sum(sum(span.get("kind") == "agent" for span in trace.get("spans", [])) for trace in traces)
    tool_errors = sum(
        sum(
            bool(span.get("kind") == "tool" and (span.get("status") == "error" or span.get("error")))
            for span in trace.get("spans", [])
        )
        for trace in traces
    )
    success_rate = len(successes) / len(completed) if completed else None
    average_latency = mean(latencies) if latencies else None
    sample_count = len(completed)
    ready = sample_count >= minimum_samples and success_rate is not None and average_latency is not None
    monitor_penalty = _penalty(success_rate, average_latency) if ready else None
    return {
        "sample_count": sample_count,
        "agent_calls": agent_calls,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "agent_success_rate": round(success_rate, 4) if success_rate is not None else None,
        "average_latency_ms": round(average_latency, 2) if average_latency is not None else None,
        "p95_latency_ms": round(_p95(latencies), 2) if _p95(latencies) is not None else None,
        "consecutive_failures": _consecutive_failures(completed),
        "routing_score": round(1 - monitor_penalty, 4) if monitor_penalty is not None else None,
        "monitor_penalty": monitor_penalty,
        "routing_state": "observation_only" if ready else "unknown",
        "routing_feedback": "not_applicable_without_comparable_agent_pool",
    }


def _consecutive_failures(results: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(results):
        if row.get("task_success") is True:
            break
        count += 1
    return count
