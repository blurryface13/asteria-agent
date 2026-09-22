"""Production contracts for the real missing-evidence / repeated-read BadCase."""
import asyncio
import json

import pytest

from asteria_researcher.agentic.coding import run_coding
from asteria_researcher.agentic.collaboration import Assignment
from asteria_researcher.agentic.coding_contract import needs_source_evidence
from asteria_researcher.agentic.code_diagnostics import source_observation

SOURCE = "https://arxiv.org/abs/1706.03762"
PASSAGE = {"source": SOURCE, "page": 4, "offset": 0, "text": "Synthetic formula evidence"}
READ = {"tool": "read_workspace_file", "arguments": {"name": "attention.py"}}
HELP = {"tool": "request_research", "arguments": {
    "question": "请核对论文中缩放因子的具体位置",
    "observed_problem": "已读取实现，当前代码没有缩放，需要核对方法定义",
    "expected_answer": "给出真实原文片段与适用条件"}}
FINISH = {"tool": "finish", "summary": "已根据本次论文材料核对；未运行代码。"}


def exercise(actions, *, scientific=True, extra_tools=None, help_result=None, file_result=None):
    seen, events, reads = [], [], []
    async def model(system, payload):
        seen.append(payload)
        action = actions[min(len(seen)-1, len(actions)-1)]
        if callable(action):
            action = action(payload)
        return json.dumps({"purpose": "test observation contract", **action})
    async def read(arguments):
        reads.append(arguments)
        return file_result if file_result is not None else {"content": "x = 1", "name": arguments.get("name")}
    async def help(*args):
        return help_result or {"status": "completed", "summary": "模型仅给出一段回答，无证据"}
    async def emit(agent, tool, status, purpose, **data):
        events.append({"tool": tool, "status": status, **data})
    task = Assignment(name="核对实现", role="coding",
        objective="对照论文检查代码实现" if scientific else "读取并解释这个文件",
        expected_output="修改建议与未验证项")
    tools = {"read_workspace_file": ({}, read), **(extra_tools or {})}
    result = asyncio.run(run_coding(task, model, tools, help, emit, max_turns=len(actions)))
    return result, seen, events, reads


def test_original_badcase_six_reads_and_plausible_diff_cannot_complete():
    def preview(data):
        first = next(o["observation_id"] for o in data["observations"] if o.get("tool") == "read_workspace_file" and "result" in o)
        return {"tool": "preview_code_diff", "arguments": {"observation_id": first, "proposed_content": "x = 2\n"}}
    result, seen, events, reads = exercise([READ] * 6 + [preview, FINISH])
    assert result["status"] == "incomplete"
    assert len(reads) == 2
    assert result["completion_check"]["passed"] is False
    assert not result["evidence_index"]
    assert result["tool_results"][-1]["result"]["proposed_syntax"]["valid_syntax"]
    blocked = [t for t in result["tool_traces"] if t.get("rejected") == "duplicate_tool_request"]
    assert len(blocked) == 4 and all(not t["executed"] for t in blocked)
    assert any(e["tool"] == "finish" and e["status"] == "failed" for e in events)
    assert all(t["latency_ms"] >= 0 for t in result["tool_traces"])


@pytest.mark.parametrize("kind,text", [("download_preview", "preview text"), ("read_passage", "")])
def test_preview_or_empty_passage_cannot_satisfy_completion(kind,text):
    async def read(_): return {**PASSAGE, "text": text, "evidence_kind": kind}
    tool = "read_paper" if kind == "download_preview" else "read_paper_passage"
    result, *_ = exercise([READ, {"tool": tool}, FINISH], extra_tools={tool: ({}, read)})
    assert result["status"] == "incomplete" and not result["evidence_index"]


def test_direct_evidence_allows_completion_without_any_handoff():
    async def read(_): return {**PASSAGE, "source_url": SOURCE, "evidence_kind": "read_passage"}
    result, seen, *_ = exercise([READ, {"tool": "read_paper_passage"}, FINISH],
        extra_tools={"read_paper_passage": ({}, read)})
    assert result["status"] == "completed" and result["completion_check"]["passed"]
    assert not result["research_requests"]
    assert seen[-1]["evidence_index"][0]["source"] == SOURCE
    assert result["evidence_index"][0]["observation_id"] == result["tool_results"][1]["id"]


def test_research_summary_alone_downgrades_to_incomplete():
    result, *_ = exercise([READ, HELP, FINISH])
    assert result["status"] == "incomplete"
    request = result["research_requests"][0]
    assert request["status"] == "incomplete" and "evidence_gap" in request["response"]
    assert result["tool_traces"][-1]["success"] is True
    assert result["tool_traces"][-1]["result_success"] is False


def test_handoff_accepts_actual_passages_not_just_summary_urls():
    result, *_ = exercise([READ, HELP, FINISH], help_result={
        "status": "completed", "summary": "已读取冻结材料", "evidence": [PASSAGE]})
    assert result["status"] == "completed"
    assert result["evidence_index"][0]["via"] == "research"
    assert result["evidence_index"][0]["observation_id"] == result["research_requests"][0]["request_id"]


def test_ordinary_code_explanation_does_not_require_paper_reading():
    result, *_ = exercise([READ, {"tool": "finish", "summary": "文件将x赋值为1"}], scientific=False)
    assert result["status"] == "completed"
    assert result["completion_check"]["source_evidence_required"] is False


def test_business_failure_is_not_successful_file_evidence():
    result, _, events, _ = exercise([READ, FINISH], scientific=False,
        file_result={"success": False, "error": "not readable", "content": "cached non-authoritative content"})
    assert result["status"] == "incomplete"
    trace = result["tool_traces"][0]
    assert trace["success"] is True and trace["result_success"] is False
    assert any(e["tool"] == "read_workspace_file" and e["status"] == "failed" for e in events)


def test_a_changed_file_parameter_is_not_a_duplicate():
    result, _, _, reads = exercise([READ, READ, {**READ, "arguments": {"name": "other.py"}},
        {"tool": "finish", "summary": "已读取两个文件"}], scientific=False)
    assert len(reads) == 3 and result["status"] == "completed"


def test_explicit_knowledge_base_task_requires_source_evidence():
    assert needs_source_evidence(Assignment(name="实现核查", role="coding", objective="依据知识库核对实现"))


def test_failed_read_content_is_not_allowed_into_diff_or_syntax_checks():
    with pytest.raises(ValueError, match="读取失败"):
        source_observation([{"id": "failed", "tool": "read_workspace_file", "result": {
            "success": False, "content": "x=1", "name": "fixture.py"}}], "failed")


def test_incomplete_response_shows_runtime_evidence_gap():
    result, *_ = exercise([READ, {**FINISH, "outcome": "incomplete"}])
    assert result["status"] == "incomplete"
    assert "运行核验：尚未取得" in result["summary"]
