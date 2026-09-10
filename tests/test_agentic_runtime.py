import asyncio
import json
import shutil

import pytest

from asteria_researcher.agentic.runtime import Coordinator, capability_for, urls
from asteria_researcher.agentic.latex import render_tex, publish


PLAN = {"scope": "测试范围", "perspectives": [{"name": "方法", "query": "原始论文方法"}]}
FINISH = {"decision": "finish", "gaps": [], "followups": []}
REPORT = "# 文献综述\n基线、数据、指标、环境与验收。\n[论文](https://example.org/paper)"


def runner(responses, feedback=None, evidence="证据 https://example.org/paper"):
    calls, events = [], []
    async def model(system, user):
        result = responses.pop(0)
        return json.dumps(result) if isinstance(result, dict) else result
    async def research(query):
        calls.append(query)
        return evidence
    async def emit(kind, text):
        events.append((kind, text))
    async def approve(question):
        return feedback.pop(0) if feedback else None
    return Coordinator(model=model, research=research, emit=emit, approve=approve), calls, events


def test_deliverable_routing_is_narrow():
    assert capability_for("写文献综述") == "literature_review"
    assert capability_for("设计复现实验方案") == "experiment_design"
    assert capability_for("vLLM理论基础") is None


def test_url_parser_stops_at_chinese_punctuation():
    assert urls("来源（https://arxiv.org/abs/1706.03762）。后续中文。") == {"https://arxiv.org/abs/1706.03762"}
    assert urls("[论文](https://example.org/paper)。") == {"https://example.org/paper"}
    assert urls(json.dumps({"excerpt": "https://example.org/paper\n引用"})) == {"https://example.org/paper"}


def test_review_delegates_followup_only_for_evidence_gap():
    audit = {"decision": "research", "gaps": ["缺少基线"], "followups": [{"name": "基线", "query": "原始基线"}]}
    runtime, calls, events = runner([PLAN, audit, FINISH, REPORT])
    report = asyncio.run(runtime.run("综述", "literature_review"))
    assert len(calls) == 2
    assert "https://example.org/paper" in report
    assert [k for k, _ in events].count("evidence_audit") == 2


def test_human_revision_changes_plan_before_any_research():
    revised = {"scope": "仅研究公开方法", "perspectives": [{"name": "新方法", "query": "新问题"}]}
    runtime, calls, _ = runner([PLAN, revised, FINISH, REPORT], ["修改范围", None])
    asyncio.run(runtime.run("综述", "literature_review"))
    assert len(calls) == 1 and "仅研究公开方法" in calls[0]


def test_no_auto_approval_on_revision_exhaustion():
    runtime, calls, _ = runner([PLAN, PLAN, PLAN], ["不同意"] * 3)
    with pytest.raises(ValueError, match="未自动批准"):
        asyncio.run(runtime.run("综述", "literature_review"))
    assert not calls


def test_unknown_citation_fails_delivery():
    runtime, _, _ = runner([PLAN, FINISH, "引用 https://invented.invalid/paper", "引用 https://invented.invalid/paper"])
    with pytest.raises(ValueError, match="引用校验"):
        asyncio.run(runtime.run("综述", "literature_review"))


def test_experiment_is_design_not_execution():
    runtime, _, events = runner([PLAN, FINISH, REPORT])
    result = asyncio.run(runtime.run("复现实验", "experiment_design"))
    assert "未执行代码" in result
    assert any(k == "protocol_check" for k, _ in events)


def test_missing_protocol_sections_fail():
    runtime, _, _ = runner([PLAN, FINISH, "报告 https://example.org/paper", "报告 https://example.org/paper"])
    with pytest.raises(ValueError, match="必需部分"):
        asyncio.run(runtime.run("复现实验", "experiment_design"))


def test_latex_does_not_execute_model_tex():
    tex = render_tex(r"\input{/etc/passwd} $100 & 20%")
    assert r"\input{" not in tex
    assert r"\textbackslash{}input\{" in tex
    assert r"\$100" in tex


def test_writer_repairs_citation_before_delivery():
    runtime, _, events = runner([PLAN, FINISH, "https://invented.invalid/paper", REPORT])
    assert asyncio.run(runtime.run("综述", "literature_review")) == REPORT
    assert any(kind == "revision_requested" for kind, _ in events)


def test_writer_repairs_requested_length():
    too_long = "研究" * 300 + " https://example.org/paper"
    runtime, _, events = runner([PLAN, FINISH, too_long, REPORT])
    assert asyncio.run(runtime.run("写约300字综述", "literature_review")) == REPORT
    assert any(kind == "revision_requested" for kind, _ in events)


def test_writer_rejects_persistent_length_violation():
    too_long = "研究" * 300 + " https://example.org/paper"
    runtime, _, _ = runner([PLAN, FINISH, too_long, too_long])
    with pytest.raises(ValueError, match="篇幅"):
        asyncio.run(runtime.run("写约300字综述", "literature_review"))


def test_insufficient_evidence_does_not_publish_after_budget():
    audit = {"decision": "research", "gaps": ["没有原始证据"], "followups": [{"name": "补研", "query": "原始来源"}]}
    runtime, calls, _ = runner([PLAN, audit, audit])
    with pytest.raises(ValueError, match="停止交付"):
        asyncio.run(runtime.run("综述", "literature_review"))
    assert len(calls) == 2


@pytest.mark.skipif(not shutil.which("xelatex"), reason="XeLaTeX not installed")
def test_real_chinese_pdf_compilation(tmp_path):
    paths = asyncio.run(publish(REPORT, tmp_path))
    pdf = next(tmp_path.glob("*/report.pdf"))
    assert pdf.read_bytes().startswith(b"%PDF")
    assert paths["tex"].endswith("/report.tex")
