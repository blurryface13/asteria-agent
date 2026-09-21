"""Deterministic user-scenario tests; not a claim of live LLM quality."""
import asyncio
import json

import pytest

from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.collaboration import Assignment, run_parallel
from asteria_researcher.agentic.code_diagnostics import build_diagnostic_tools, syntax_result
from asteria_researcher.agentic.coding_research_tools import build_paper_tools
from backend.server.collaboration_progress import project_event


async def noop(*args, **kwargs):
    pass


def task(name, role="researcher"):
    return Assignment(name=name, objective="调查 " + name, role=role, focus=name, expected_output="可核实证据")


def runtime(tmp_path, model=None, tools=None):
    r = AutonomousReview(model, None, noop, noop, tmp_path, online_rag=False, coding_tools=tools)
    r.query, r.plan = "并行调查方法原理和代码实现", {}
    return r


def test_fast_result_arrives_before_slow_finishes_and_final_order_is_stable():
    async def exercise():
        slow_release, fast_arrived = asyncio.Event(), asyncio.Event()
        events = []
        async def execute(t):
            if t.name == "slow":
                await slow_release.wait()
            return {"summary": t.name, "status": "completed"}
        async def arrived(index, result):
            events.append((index, result))
            fast_arrived.set()
        job = asyncio.create_task(run_parallel([task("slow"), task("fast")], execute, arrived))
        try:
            await asyncio.wait_for(fast_arrived.wait(), 1)
            assert not job.done() and events[0][0] == 1
            assert events[0][1]["timing"]["elapsed_ms"] >= 0
            slow_release.set()
            result = await job
            assert [r["summary"] for r in result] == ["slow", "fast"]
            assert [i for i, _ in events] == [1, 0]
        finally:
            slow_release.set()
            await asyncio.gather(job, return_exceptions=True)
    asyncio.run(exercise())


def test_cancel_preserves_early_result_and_cancels_remaining_child(tmp_path):
    async def exercise():
        r = runtime(tmp_path)
        fast_arrived, slow_cancelled = asyncio.Event(), asyncio.Event()
        async def child(agent, objective, **kwargs):
            if kwargs["assignment_context"]["name"] == "slow":
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    slow_cancelled.set()
                    raise
            return {"agent": agent, "summary": "已核对方法公式", "status": "completed"}
        events = []
        async def emit(kind, event):
            events.append(event)
            if event["tool"] == "parallel_result":
                fast_arrived.set()
        r.loop, r.emit = child, emit
        job = asyncio.create_task(r.dispatch_assignments([task("slow"), task("fast")]))
        await asyncio.wait_for(fast_arrived.wait(), 1)
        assert len(r.briefs) == 1
        saved = json.loads((r.folder / "delegations.json").read_text())
        assert len(saved[0]["arrivals"]) == 1
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert slow_cancelled.is_set()
        saved = json.loads((r.folder / "delegations.json").read_text())[0]
        assert saved["status"] == "cancelled" and len(saved["arrivals"]) == 1
        assert events[-1]["tool"] == "parallel_batch" and events[-1]["status"] == "cancelled"
        assert saved["first_result_ms"] <= saved["elapsed_ms"]
    asyncio.run(exercise())


def test_direct_paper_read_diagnostics_and_diff_stay_in_one_loop(tmp_path):
    paper = "https://arxiv.org/abs/1706.03762"
    turns, events = [], []
    async def read(args):
        return {"name": "attention_demo.py", "content": "def attention(q, k, v):\n    return softmax(q @ k.T) @ v\n"}
    async def model(system, raw):
        data = json.loads(raw)
        turns.append(data)
        observation = data["observations"][0].get("observation_id") if data["observations"] else None
        actions = [
            {"tool": "read_workspace_file", "arguments": {"name": "attention_demo.py"}},
            {"tool": "read_paper", "arguments": {"paper_url": paper}},
            {"tool": "read_paper_passage", "arguments": {"paper_url": paper, "page": 4}},
            {"tool": "check_python_syntax", "arguments": {"observation_id": observation}},
            {"tool": "preview_code_diff", "arguments": {"observation_id": observation,
             "proposed_content": "def attention(q, k, v):\n    return softmax(q @ k.T / sqrt(k.shape[-1])) @ v\n"}},
            {"tool": "finish", "summary": "核对原文后预览缩放项修改；仅做语法检查，未运行代码。"},
        ]
        return json.dumps({"purpose": "核对代码与论文并检查修改", **actions[len(turns) - 1]})
    r = runtime(tmp_path, model, {"read_workspace_file": ({}, read)})
    r.query += " " + paper
    # Actual task-scoped library, preloaded with an explicit evidence fixture. No network/model claims.
    r.library.add({"url": paper, "title": "Attention"})
    r.library.papers[paper] = {"url": paper, "title": "Attention", "text": "scaling",
                            "pages": [{"page": 4, "text": "Attention(Q,K,V) = softmax(QK^T / sqrt(d_k))V."}]}
    async def emit(kind, event): events.append(event)
    r.emit = emit
    result = asyncio.run(r.dispatch_assignments([task("attention", "coding")]))[0]
    assert result["status"] == "completed" and len(turns) == 6
    assert r.children == 1 and not r.help_requests
    assert not result["execution_performed"]
    checks = result["tool_results"]
    assert checks[-1]["tool"] == "preview_code_diff" and checks[-1]["result"]["applied"] is False
    assert "sqrt(k.shape[-1])" in checks[-1]["result"]["diff"]
    assert checks[-2]["result"]["valid_syntax"]
    assert paper in result["sources"] and r.evidence[0]["passages"][0]["page"] == 4
    assert r.evidence[0]["agent"] == result["agent"]
    assert len([e for e in events if e["tool"] == "parallel_result"]) == 1


def test_static_check_never_executes_and_reports_line(tmp_path):
    target = tmp_path / "must-not-exist"
    code = f"from pathlib import Path\nPath({str(target)!r}).write_text('executed')"
    assert syntax_result(code, "danger.py")["valid_syntax"]
    assert not target.exists()
    result = syntax_result("def missing(:\n  return 1", "broken.py")
    assert not result["valid_syntax"] and result["issues"][0]["line"] == 1
    with pytest.raises(ValueError):
        syntax_result("print(1)", "not-python.js")


@pytest.mark.parametrize("observations", [[], [{"id": "fake", "tool": "search_papers", "result": {"content": "print(1)"}}],
    [{"id": "fake", "tool": "read_workspace_file", "result": {"exists": False, "content": ""}}]])
def test_diagnostics_require_real_file_observation(observations):
    tools = build_diagnostic_tools(observations)
    with pytest.raises(ValueError):
        asyncio.run(tools["check_python_syntax"][1]({"observation_id": "fake"}))


def test_direct_paper_tools_share_budget_and_reject_unseen_urls(tmp_path):
    r = runtime(tmp_path)
    paper = "https://arxiv.org/abs/1706.03762"
    tools = build_paper_tools(r, "coding-a")
    with pytest.raises(ValueError, match="只能读取"):
        asyncio.run(tools["read_paper"][1]({"paper_url": paper}))
    r.library.papers[paper] = {"pages": [{"page": 1, "text": "evidence"}]}
    r.direct_chars = 120000
    with pytest.raises(ValueError, match="预算"):
        asyncio.run(tools["read_paper_passage"][1]({"paper_url": paper}))
    assert not r.evidence


def test_progress_projection_keeps_only_bounded_display_fields():
    assert project_event({"tool": "read_workspace_file", "result": {"content": "private code"}}) is None
    event = {"tool": "parallel_result", "status": "completed", "purpose": "stage", "index": 0,
             "result": {"summary": "x" * 10000, "tool_results": [{"content": "secret"}]}, "credentials": "secret"}
    projected = project_event(event)
    assert len(projected["result"]["summary"]) == 2400
    assert "secret" not in json.dumps(projected) and "credentials" not in projected


def test_standalone_coding_publishes_before_final_response(tmp_path, monkeypatch):
    from backend.server import coding_tools
    async def read(args): return {"name": "demo.py", "content": "print(1)"}
    monkeypatch.setattr(coding_tools, "build_coding_tools", lambda email: {"read_workspace_file": ({}, read)})
    monkeypatch.chdir(tmp_path)
    async def exercise():
        seen = []
        async def progress(event): seen.append(event)
        async def model(system, raw):
            data = json.loads(raw)
            assert any(e["tool"] == "parallel_batch" for e in seen)
            if not data["observations"]:
                return json.dumps({"tool": "read_workspace_file", "purpose": "读取", "arguments": {"name": "demo.py"}})
            return json.dumps({"tool": "finish", "purpose": "解释", "summary": "读取到打印语句，未执行"})
        content, metadata = await coding_tools.run_workspace_coding("检查文件", [], model, "fixture-user", progress)
        assert "未执行" in content and metadata["status"] == "completed"
        assert any(e["tool"] == "parallel_result" for e in seen)
    asyncio.run(exercise())
