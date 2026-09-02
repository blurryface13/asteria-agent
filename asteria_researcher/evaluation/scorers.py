"""Deterministic and extensible metrics for Agent regression evaluation."""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from statistics import mean
from typing import Any

from .models import AgentRunOutput, EvalCase, EvalResult, FailureType, TraceEnvelope

HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")


def extract_headings(text: str) -> list[str]:
    return [match.group(1).strip() for match in HEADING_RE.finditer(text or "")]


def outline_coverage(report: str, expected: list[str]) -> float:
    if not expected:
        return 0.0
    actual = [_normalize(item) for item in extract_headings(report)]
    return sum(any(_similar(_normalize(item), value) for value in actual) for item in expected) / len(expected)


def citation_count(report: str) -> int:
    return len(set(LINK_RE.findall(report or "")))


def heuristic_citation_support(report: str, reference_urls: list[str]) -> float | None:
    if not reference_urls:
        return None
    links = set(LINK_RE.findall(report or ""))
    return sum(url in links or any(url in link for link in links) for url in reference_urls) / len(reference_urls)


def tool_scores(expected: list[str], actual: list[str]) -> tuple[float | None, float | None, float | None]:
    if not expected and not actual:
        return None, None, None
    expected_set, actual_set = set(expected), set(actual)
    precision = len(expected_set & actual_set) / len(actual_set) if actual_set else 0.0
    recall = len(expected_set & actual_set) / len(expected_set) if expected_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def milestone_progress(required: list[str], trace: TraceEnvelope | None, report: str) -> float | None:
    if not required:
        return None
    haystack = " ".join([report, *(span.name for span in trace.spans)] if trace else [report]).lower()
    return sum(_normalize(item) in _normalize(haystack) for item in required) / len(required)


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[index]


def pass_at_k(results: list[EvalResult], k: int) -> float | None:
    if k <= 0 or not results:
        return None
    groups: dict[str, list[EvalResult]] = {}
    for result in results:
        groups.setdefault(result.case_id, []).append(result)
    eligible = [rows[:k] for rows in groups.values() if len(rows) >= k]
    return mean(any(row.task_success for row in rows) for rows in eligible) if eligible else None


def score_run(task_id: str, case: EvalCase, output: AgentRunOutput, *, latency_ms: float | None = None, run_index: int = 1) -> EvalResult:
    trace = output.trace
    actual_tools = trace.actual_tool_names() if trace else []
    precision, recall, f1 = tool_scores(case.expected_tools, actual_tools)
    success = bool(output.report.strip()) and outline_coverage(output.report, case.expected_sections) >= (0.5 if case.expected_sections else 0.0)
    if case.expected_tools and recall is not None:
        success = success and recall >= 1.0
    failure_type = None if success else FailureType.OUTPUT_INCOMPLETE
    return EvalResult(
        task_id=task_id,
        case_id=case.case_id,
        run_index=run_index,
        task_success=success,
        outline_coverage=outline_coverage(output.report, case.expected_sections),
        citation_count=citation_count(output.report),
        citation_support_rate=heuristic_citation_support(output.report, case.reference_urls),
        tool_precision=precision,
        tool_recall=recall,
        milestone_progress=milestone_progress(case.required_milestones, trace, output.report),
        latency_ms=latency_ms,
        failure_type=failure_type,
        failure_reason="final output missing required sections/tools" if not success else "",
        report_excerpt=output.report[:1000],
        trace_id=trace.trace_id if trace else None,
        metrics={"tool_f1": f1, "heuristic_citation_support": True},
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^\w\s\u4e00-\u9fff]", " ", value.lower()).strip()


def _similar(expected: str, actual: str) -> bool:
    return bool(expected and actual and (expected in actual or actual in expected or SequenceMatcher(None, expected, actual).ratio() >= 0.58))
