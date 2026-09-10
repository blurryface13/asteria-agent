import asyncio
import pytest
from asteria_researcher.agentic.intent import analyze_intent


def test_routes_deliverable_without_review_keyword():
    async def model(system, user):
        assert user == "比较几篇论文的方法与局限，写相关工作"
        assert "semantically" in system
        return '{"capability":"literature_review","reason":"综合论文方法"}'
    result = asyncio.run(analyze_intent("比较几篇论文的方法与局限，写相关工作", model))
    assert result.capability == "literature_review"


def test_invalid_router_result_is_not_silently_defaulted():
    async def model(*args):
        return '{"capability":"run_shell","reason":"invalid"}'
    with pytest.raises(ValueError):
        asyncio.run(analyze_intent("question", model))
