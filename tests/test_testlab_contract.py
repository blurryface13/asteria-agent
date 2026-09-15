"""Stable, no-provider contracts executed by the Agent TestLab adapter.

These checks intentionally exercise public Asteria contracts without starting a
research run, touching PostgreSQL, or making a model call.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException


def test_coordinator_and_evaluation_routes_are_registered():
    from backend.server.app import app

    paths = []
    for route in app.router.routes:
        if hasattr(route, "effective_route_contexts"):
            paths.extend(context.path for context in route.effective_route_contexts())
        elif getattr(route, "path", None):
            paths.append(route.path)
    assert "/api/coordinator/route" in paths
    assert "/api/workspace/runs" in paths
    assert "/api/evaluation/quality/judge" in paths
    assert "/api/evaluation/monitor" in paths


def test_research_payload_rejects_client_credentials_and_accepts_capability():
    from backend.runs.routes import validate_request

    valid = validate_request({
        "task": "梳理视觉语言模型水印研究进展",
        "report_type": "research_report",
        "report_source": "web",
        "tone": "academic",
        "headers": {"retrievers": ""},
        "online_rag": False,
        "coordinator_capability": "literature_review",
    })
    assert valid["coordinator_capability"] == "literature_review"

    with pytest.raises(HTTPException, match="凭据"):
        validate_request({**valid, "headers": {"authorization": "Bearer secret"}})


def test_judge_output_is_strict_and_monitor_is_observation_only():
    from asteria_researcher.evaluation.monitor import aggregate_monitor
    from asteria_researcher.evaluation.quality_judge import evaluate_provider_output

    scored = evaluate_provider_output(
        "比较两种方法", "回答内容", '{"relevance":0.9,"accuracy":0.8,"completeness":0.8,"helpfulness":0.9}',
        case_id="test-case",
    )
    assert scored.status == "scored"
    assert scored.scores and round(scored.scores.overall, 2) == 0.85

    malformed = evaluate_provider_output("问题", "回答", "not-json")
    assert malformed.status == "judge_error"
    snapshot = aggregate_monitor([], [])
    assert snapshot["routing_state"] == "unknown"
    assert snapshot["monitor_penalty"] is None


def test_coordinator_intent_contract_is_async_and_structured():
    from asteria_researcher.agentic.intent import analyze_intent

    async def fake_model(_system: str, _payload: str) -> str:
        return '{"capability":"experiment_design","reason":"用户要求制定实验方案"}'

    intent = asyncio.run(analyze_intent("设计一个消融实验", fake_model))
    assert intent.capability == "experiment_design"
    assert intent.reason
