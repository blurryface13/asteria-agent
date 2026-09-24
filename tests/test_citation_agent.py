"""Post-writing citations are grounded in actual read passages, not a URL list."""
import asyncio
import json

import pytest

from asteria_researcher.agentic.citation_agent import CitationAgent
from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.sufficiency import ReviewPlan


SOURCE = "https://arxiv.org/abs/1706.03762"
REPORT = "# 方法综述\n\n该方法基于注意力机制处理序列建模任务，并在论文中给出了模型结构。\n"
CATALOG = {"e_1": {"source": SOURCE, "page": 1, "offset": 0,
                   "text": "The Transformer is based solely on attention mechanisms."}}


async def emit(*_args, **_kwargs):
    pass


def test_citation_agent_places_source_at_checked_line(tmp_path):
    async def model(_system, payload):
        assert payload["evidence"][0]["id"] == "e_1"
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
                                         "evidence_ids": ["e_1"], "reason": "原文摘要支持"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach(REPORT, CATALOG, {SOURCE: {}}))
    assert f"[来源]({SOURCE})" in result.splitlines()[2]
    assert json.loads((tmp_path / "citation-review.json").read_text())["status"] == "completed"


def test_citation_agent_refuses_unsupported_claim(tmp_path):
    async def model(_system, _payload):
        return json.dumps({"findings": [{"line_id": 2, "supported": False,
                                         "evidence_ids": [], "reason": "无对应原文"}]})
    with pytest.raises(ValueError, match="未获原文支持"):
        asyncio.run(CitationAgent(model, emit, tmp_path).attach(REPORT, CATALOG, {SOURCE: {}}))
    assert json.loads((tmp_path / "citation-review.json").read_text())["status"] == "incomplete"


def test_citation_agent_refuses_invented_evidence_and_wrong_existing_link(tmp_path):
    async def fabricated(_system, _payload):
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
                                         "evidence_ids": ["e_unknown"], "reason": "猜测"}]})
    with pytest.raises(ValueError, match="不存在"):
        asyncio.run(CitationAgent(fabricated, emit, tmp_path).attach(REPORT, CATALOG, {SOURCE: {}}))
    wrong_report = REPORT.rstrip() + " [错误来源](https://arxiv.org/abs/1810.04805)\n"
    async def source_mismatch(_system, _payload):
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
                                         "evidence_ids": ["e_1"], "reason": "原文支持，但旧链接错误"}]})
    with pytest.raises(ValueError, match="未获原文支持"):
        asyncio.run(CitationAgent(source_mismatch, emit, tmp_path).attach(
            wrong_report, CATALOG, {SOURCE: {}, "https://arxiv.org/abs/1810.04805": {}}))


def test_research_route_reaches_postwriting_citation_agent(tmp_path):
    async def approve(_question):
        return None
    runtime = AutonomousReview(None, None, emit, approve, tmp_path, online_rag=False)
    runtime.query = "请综述注意力方法"
    plan = ReviewPlan(scope="注意力方法", perspectives=[{"name": "方法", "query": "注意力机制"}],
                      required_goals=[{"id": "g1", "description": "注意力方法", "user_quote": "注意力方法"}])
    async def plan_step(*_args):
        return plan
    async def loop(*_args, **_kwargs):
        runtime.library.add({"url": SOURCE, "title": "Transformer"})
        runtime.library.papers[SOURCE] = {"text": CATALOG["e_1"]["text"]}
        runtime.evidence.append({"agent": "researcher", "query": "注意力机制",
                                 "passages": [{k: v for k, v in CATALOG["e_1"].items()}]})
        return {"status": "completed", "summary": "注意力机制已有原文支持"}
    async def write(_summary):
        return REPORT
    runtime.plan_with_contract = plan_step
    runtime.partition_with_contract = plan_step
    runtime.loop = loop
    runtime.write_report = write
    # Stable IDs are computed from the passage; use that ID in the scripted judge.
    async def checked_model(system, payload):
        assert "post-writing CitationAgent" in system
        payload = json.loads(payload)
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
                                         "evidence_ids": [payload["evidence"][0]["id"]], "reason": "原文支持"}]})
    runtime.model = checked_model
    result = asyncio.run(runtime.research())
    assert f"[来源]({SOURCE})" in result
    assert (runtime.folder / "report-with-citations.md").read_text() == result
    assert json.loads((runtime.folder / "working-memory.json").read_text())["phase"] == "citations_completed"
