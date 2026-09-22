"""User priorities: distinct coverage, parallel execution, targeted coding handoff.

These use scripted models/tool doubles, NOT measured live-model quality scores.
"""
import asyncio
import json

import pytest

from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.collaboration import (
    Assignment, allocation_report, DelegationAudit, validate_audit, run_parallel)
from asteria_researcher.agentic.coding import run_coding


def task(name="method", objective="Explain the training objective", goals=("g1",), **kw):
    return Assignment(name=name, objective=objective, goal_ids=list(goals), focus="方法原理及适用条件",
                      expected_output="给出有原文依据的结论", **kw)


def audit_for(tasks, distinct=True):
    return {"tasks": [{"name": t.name, "in_scope": True, "distinct": distinct,
                        "covered_goal_ids": t.goal_ids, "reason": "独立调查问题" if distinct else "只是同一问题的改写"}
                       for t in tasks]}


async def noop(*a, **kw):
    pass


def runtime(tmp_path, model=None, tools=None):
    r = AutonomousReview(model, None, noop, noop, tmp_path, online_rag=False, coding_tools=tools)
    r.query = "比较方法原理、评估条件，并调查代码实现"
    r.plan = {"required_goals": [{"id": "g1", "description": "方法原理"},
                                 {"id": "g2", "description": "评估条件"}]}
    return r


def test_missing_goals_must_be_retained_by_lead():
    with pytest.raises(ValueError, match="未分配"):
        allocation_report([task()], ["g1", "g2"])
    result = allocation_report([task()], ["g1", "g2"], ["g2"])
    assert result["goal_owners"] == {"g1": ["method"], "g2": ["lead"]}
    assert "不代表" in result["note"]


@pytest.mark.parametrize("assignments", [
    [task(), task(name="another", objective="Explain the training objective!")],
    [task(), task(name="method", objective="Compare evaluation datasets")],
    [task(goals=("g1", "g1"))],
    [task(goals=("g99",))],
    [task().model_copy(update={"focus": ""})],
])
def test_redundant_invalid_or_empty_contracts_rejected(assignments):
    with pytest.raises(ValueError):
        allocation_report(assignments, ["g1"])


def test_same_goal_and_source_can_have_distinct_questions():
    tasks = [task(), task(name="implementation", objective="Check gradient implementation against equations", role="coding")]
    assert allocation_report(tasks, ["g1"])["goal_owners"]["g1"] == ["method", "implementation"]
    validate_audit(DelegationAudit.model_validate(audit_for(tasks)), tasks)


def test_semantic_paraphrases_and_misdeclared_coverage_rejected():
    tasks = [task(), task(name="other", objective="Study the method principles", goals=("g2",))]
    with pytest.raises(ValueError, match="独立审查"):
        validate_audit(DelegationAudit.model_validate(audit_for(tasks, False)), tasks)
    a = audit_for(tasks)
    a["tasks"][1]["covered_goal_ids"] = ["g1"]
    with pytest.raises(ValueError):
        validate_audit(DelegationAudit.model_validate(a), tasks)


def test_failed_semantic_audit_starts_no_children_and_is_saved(tmp_path):
    async def model(system, payload):
        assert "independently" in system
        data = json.loads(payload)
        return json.dumps(audit_for([Assignment.model_validate(a) for a in data["assignments"]], False))
    r = runtime(tmp_path, model)
    tasks = [task(), task(name="evaluation", objective="Study robustness metrics", goals=("g2",))]
    with pytest.raises(ValueError):
        asyncio.run(r.dispatch_assignments(tasks))
    assert r.children == 0
    assert json.loads((r.folder / "delegations.json").read_text())[0]["status"] == "rejected"


def test_approved_tasks_execute_concurrently_with_isolated_contracts(tmp_path):
    seen, active, peak = [], 0, 0
    tasks = [task(), task(name="evaluation", objective="Study robustness metrics", goals=("g2",))]
    async def model(*args):
        return json.dumps(audit_for(tasks))
    r = runtime(tmp_path, model)
    async def child(agent, objective, **kwargs):
        nonlocal active, peak
        seen.append(kwargs["assignment_context"])
        active += 1
        peak = max(active, peak)
        await asyncio.sleep(.01)
        active -= 1
        return {"agent": agent, "status": "completed", "summary": objective}
    r.loop = child
    result = asyncio.run(r.dispatch_assignments(tasks))
    assert peak == 2 and r.children == 2
    assert {t["goal_ids"][0] for t in seen} == {"g1", "g2"}
    assert [x["assignment"]["name"] for x in result] == ["method", "evaluation"]


def test_parallel_failure_not_hidden_and_cancellation_propagates():
    tasks = [task(), task(name="b", objective="other")]
    async def execute(t):
        if t.name == "b":
            raise RuntimeError("private-provider-token")
        return {"status": "completed", "summary": "source checked"}
    results = asyncio.run(run_parallel(tasks, execute))
    assert results[1]["status"] == "failed" and "private" not in str(results)
    async def cancel_test():
        running, cancelled = asyncio.Event(), []
        async def wait(t):
            running.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(t.name)
        work = asyncio.create_task(run_parallel(tasks, wait))
        await running.wait()
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        assert set(cancelled) == {"method", "b"}
    asyncio.run(cancel_test())


def test_coding_reads_then_requests_research_then_resumes():
    observed, events, asked = [], [], []
    async def emit(agent, tool, status, purpose, **kw):
        events.append({"agent": agent, "tool": tool, "status": status, **kw})
    async def read(args):
        return {"name": "loss.py", "content": "loss = reconstruction + 0.1 * watermark"}
    async def help(req, request_id, requester):
        asked.append(req.question)
        return {"status": "completed", "summary": "论文的默认权重为0.1，消融实验需保持其他变量不变",
                "evidence": [{"source": "https://arxiv.org/abs/1706.03762", "page": 1,
                              "text": "Synthetic test fixture: default weight 0.1; other variables fixed."}]}
    responses = [
        {"tool": "read_workspace_file", "purpose": "核对当前实现", "arguments": {"name": "loss.py"}},
        {"tool": "request_research", "purpose": "确认论文的默认配置", "arguments": {
            "question": "这个损失中的水印权重应该采用什么默认值？", "observed_problem": "代码设为0.1，但实验笔记记录了另一个值，需要对照原论文。",
            "expected_answer": "给出原文默认权重与适用条件"}},
        {"tool": "finish", "purpose": "回到原任务解释代码", "summary": "已对照调研答复分析权重。尚未运行实验。"},
    ]
    async def model(system, payload):
        observed.append(payload)
        return json.dumps(responses[len(observed)-1])
    result = asyncio.run(run_coding(task(role="coding"), model, {"read_workspace_file": ({}, read)}, help, emit))
    assert len(asked) == 1 and result["status"] == "completed"
    assert "论文的默认" in str(observed[2]["observations"])
    assert not result["execution_performed"]
    handoffs = [e for e in events if e["tool"] == "research_handoff"]
    assert [e["status"] for e in handoffs] == ["waiting", "completed"]
    assert handoffs[0]["request_id"] == handoffs[1]["request_id"]


def test_empty_research_handoff_and_fake_completion_are_rejected():
    payloads = []
    async def model(system, data):
        payloads.append(data)
        if len(payloads) == 1:
            return json.dumps({"tool": "request_research", "purpose": "blind delegation", "arguments": {
                "question": "帮我研究论文的整体复现方法", "observed_problem": "这里并没有读过任何代码或文件", "expected_answer": "完整调研报告"}})
        return json.dumps({"tool": "finish", "purpose": "fake done", "summary": "Everything finished"})
    async def forbidden(*args):
        pytest.fail("must not call research")
    result = asyncio.run(run_coding(task(role="coding"), model, {}, forbidden, noop, max_turns=3))
    assert result["status"] == "incomplete"
    assert "已观察" in str(payloads[1]["observations"])


def test_unknown_tools_schema_repair_and_failed_research_are_observations():
    payloads = []
    async def read(_): return {"content": "observed implementation"}
    responses = ["not-json", {"tool": "run_shell", "purpose": "escape"},
                 {"tool": "read_workspace_file", "purpose": "inspect"},
                 {"tool": "request_research", "purpose": "help", "arguments": {
                     "question": "请核实论文中损失函数的定义", "observed_problem": "本地代码的损失函数缺少权重说明", "expected_answer": "权重的原文依据"}},
                 {"tool": "finish", "purpose": "report blocker", "outcome": "incomplete", "summary": "研究服务不可用，未执行实验"}]
    async def model(system, payload):
        payloads.append(payload)
        value = responses[len(payloads)-1]
        return value if isinstance(value, str) else json.dumps(value)
    async def fail(*args): raise TimeoutError("private-token")
    result = asyncio.run(run_coding(task(role="coding"), model, {"read_workspace_file": ({}, read)}, fail, noop, max_turns=5))
    assert result["status"] == "incomplete"
    assert result["research_requests"][0]["status"] == "failed"
    assert "private-token" not in str(payloads)


def test_supervisor_handoff_is_targeted_bounded_and_does_not_reenter_full_run(tmp_path):
    from asteria_researcher.agentic.coding import ResearchRequest
    r = runtime(tmp_path)
    observed = []
    async def child(agent, objective, **kwargs):
        observed.append((agent, objective, kwargs))
        return {"status": "completed", "summary": "a sourced answer"}
    r.loop = child
    req = ResearchRequest(question="论文的损失权重如何选择？", observed_problem="代码和论文默认配置似乎不同，需要核实", expected_answer="原始参数及条件")
    result = asyncio.run(r.answer_research_request(task(role="coding"), req, "request1", "coding1"))
    assert observed[0][1] == req.question and observed[0][2]["steps"] == 7
    assert "parent_task" in observed[0][2]["assignment_context"]
    assert result["status"] == "completed" and r.children == 1
    r.children = 8
    assert asyncio.run(r.answer_research_request(task(), req, "request2", "coding1"))["status"] == "incomplete"
    assert len(observed) == 1


def test_experiment_execution_cannot_pass_from_a_generated_script(tmp_path):
    async def model(*args):
        return json.dumps({"findings": [{"goal_id": "c1", "supported": True, "evidence_ids": ["tool1"], "reason": "mistaken judge says ran"}]})
    r = runtime(tmp_path, model)
    r.plan["implementation_requirements"] = [{"id": "c1", "kind": "experiment_execution", "description": "运行实验"}]
    r.coding_results = [{"summary": "Generated script", "tool_results": [{"id": "tool1", "tool": "propose_workspace_change", "result": {"status": "pending"}}]}]
    result = asyncio.run(r.review_implementation())
    assert result[0]["supported"] is False
    assert r.pending_goals()[-1]["id"] == "c1"


def test_code_review_checks_actual_evidence_and_caches_unchanged_results(tmp_path):
    calls = []
    async def model(*args):
        calls.append(1)
        return json.dumps({"findings": [{"goal_id": "c1", "supported": True, "evidence_ids": ["t1"], "reason": "代码已包含对应实现"}]})
    r = runtime(tmp_path, model)
    r.plan["implementation_requirements"] = [{"id": "c1", "kind": "code_analysis", "description": "核对实现"}]
    r.coding_results = [{"summary": "checked", "tool_results": [{"id": "t1", "tool": "read_workspace_file", "result": {"content": "x=1"}}]}]
    assert asyncio.run(r.review_implementation())[0]["supported"]
    assert asyncio.run(r.review_implementation())[0]["supported"]
    assert len(calls) == 1


def test_mcp_owner_cannot_be_supplied_by_model(monkeypatch):
    from backend.files import client
    from backend.server.coding_tools import build_coding_tools
    calls = []
    async def call(email, name, args):
        calls.append((email, name, args))
        return []
    monkeypatch.setattr(client, "call", call)
    assert "read_workspace_file" not in build_coding_tools()
    tools = build_coding_tools("owner@example.org")
    with pytest.raises(ValueError):
        asyncio.run(tools["read_workspace_file"][1]({"name": "notes.md", "email": "other"}))
    asyncio.run(tools["read_workspace_file"][1]({"name": "notes.md"}))
    assert calls[0][0] == "owner@example.org"


def test_repository_reads_are_pinned_and_reject_arbitrary_hosts(monkeypatch):
    import base64
    from asteria_researcher.agentic import repository_tools as repo
    seen = []
    async def api(path):
        seen.append(path)
        if "/commits/" in path:
            return {"sha": "a" * 40}
        return {"type": "file", "encoding": "base64", "size": 3, "content": base64.b64encode(b"x=1").decode()}
    monkeypatch.setattr(repo, "api", api)
    result = asyncio.run(repo.read_repository_file({"repository": "org/repo", "path": "src/a.py"}))
    assert "a" * 40 in result["source_url"] and "?ref=" + "a" * 40 in seen[1]
    for name in ("http://localhost/secrets", "https://evil.test/org/repo", "../secrets"):
        with pytest.raises(ValueError): repo.repository_name(name)
    with pytest.raises(ValueError):
        asyncio.run(repo.read_repository_file({"repository": "org/repo", "path": "../secret"}))


def test_lead_revises_redundant_assignment_then_real_child_loops_run(tmp_path):
    paper = "https://arxiv.org/abs/1706.03762"
    turns, saw_rejection = {}, []
    tasks = [task(), task(name="evaluation", objective="Compare robustness measures", goals=("g2",))]
    async def model(system, raw):
        data = json.loads(raw)
        if system.startswith("Audit the proposed delegation"):
            return json.dumps(audit_for(tasks))
        objective = data["objective"]
        turn = turns.get(objective, 0)
        turns[objective] = turn + 1
        if objective == r.query:
            if turn == 0:
                selected = [task(), task(name="duplicate", goals=("g2",))]
            else:
                saw_rejection.extend(data["observations"])
                selected = tasks
            return json.dumps({"tool": "delegate", "purpose": "按目标分工", "assignments": [a.model_dump() for a in selected]})
        return json.dumps({"tool": "retrieve" if turn == 0 else "finish", "purpose": objective,
                           "query": objective, "summary": "Evidence " + paper})
    r = runtime(tmp_path, model)
    r.online_rag = True
    r.library.papers[paper] = {}
    async def retrieve(*args):
        return json.dumps([{"source": paper, "page": 1, "text": "actual tool fixture evidence"}])
    r.library.retrieve = retrieve
    async def checkpoint():
        if len(r.briefs) == 2:
            return {"status": "completed", "summary": "children returned"}
    r.lead_checkpoint = checkpoint
    result = asyncio.run(r.loop("lead", r.query, lead=True, steps=4))
    assert result["status"] == "completed" and r.children == 2
    assert "高度重复" in str(saw_rejection)
    assert [d["status"] for d in r.delegations] == ["rejected", "returned"]
    assert len(r.evidence) == 2


def test_full_coding_to_research_to_coding_without_restarting_workflow(tmp_path):
    paper = "https://arxiv.org/abs/1706.03762"
    coding_turns, research_turns = [], []
    async def read(args):
        return {"name": "attention_demo.py", "content": "softmax(q @ k.T) @ v"}
    async def model(system, raw):
        data = json.loads(raw)
        if "assignment" in data:
            coding_turns.append(data)
            if len(coding_turns) == 1:
                return json.dumps({"tool": "read_workspace_file", "purpose": "读取代码", "arguments": {"name": "attention_demo.py"}})
            if len(coding_turns) == 2:
                return json.dumps({"tool": "request_research", "purpose": "核实缩放因子", "arguments": {
                    "question": "注意力的缩放因子为何是根号d_k？", "observed_problem": "代码直接计算q乘k，没有缩放；需核对原论文公式", "expected_answer": "原文公式和缩放理由"}})
            assert "Evidence" in str(data["observations"])
            return json.dumps({"tool": "finish", "purpose": "回到代码任务", "summary": "按论文建议补充缩放；未运行代码。"})
        research_turns.append(data)
        return json.dumps({"tool": "retrieve" if len(research_turns) == 1 else "finish", "purpose": "回答特定问题",
                           "query": "scaled dot-product attention", "summary": "Evidence " + paper})
    r = runtime(tmp_path, model, {"read_workspace_file": ({}, read)})
    r.plan = {}
    r.online_rag = True
    r.library.papers[paper] = {}
    async def retrieve(*args):
        return json.dumps([{"source": paper, "page": 4, "text": "Attention(Q,K,V) uses scaling by sqrt(d_k)."}])
    r.library.retrieve = retrieve
    result = asyncio.run(r.dispatch_assignments([task(role="coding", goals=())]))[0]
    assert result["status"] == "completed" and r.children == 2
    assert len(research_turns) == 2 and len(coding_turns) == 3
    assert len(r.help_requests) == 1
    assert next(iter(r.help_requests.values()))["status"] == "completed"
    assert "根号d_k" in research_turns[0]["objective"]
    assert not result["execution_performed"]


def test_cancelled_handoff_is_saved_as_cancelled(tmp_path):
    from asteria_researcher.agentic.coding import ResearchRequest
    r = runtime(tmp_path)
    async def exercise():
        started = asyncio.Event()
        async def child(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        r.loop = child
        req = ResearchRequest(question="请核对论文中的实验参数", observed_problem="已读取的代码默认值与实验笔记不同", expected_answer="准确参数及其出处")
        work = asyncio.create_task(r.answer_research_request(task(role="coding"), req, "cancel1", "coding1"))
        await started.wait()
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
    asyncio.run(exercise())
    assert json.loads((r.folder / "research-requests.json").read_text())["cancel1"]["status"] == "cancelled"


def test_research_request_cannot_be_based_only_on_file_listing():
    payloads, called = [], []
    async def listing(_): return ["a.py"]
    async def help(*_): called.append(1)
    responses = [{"tool": "list_workspace_files", "purpose": "list"},
                 {"tool": "request_research", "purpose": "premature help", "arguments": {
                     "question": "请解释代码采用的损失函数", "observed_problem": "当前只有文件列表，并没有读文件", "expected_answer": "方法原理解释"}},
                 {"tool": "finish", "purpose": "stop", "summary": "还需要读取代码", "outcome": "incomplete"}]
    async def model(system, data):
        payloads.append(data)
        return json.dumps(responses[len(payloads)-1])
    r = asyncio.run(run_coding(task(role="coding"), model, {"list_workspace_files": ({}, listing)}, help, noop, max_turns=3))
    assert r["status"] == "incomplete" and not called


def test_final_code_answer_cannot_invent_source_urls():
    count = 0
    async def model(*args):
        nonlocal count
        count += 1
        if count == 1:
            return json.dumps({"tool": "read_workspace_file", "purpose": "read"})
        return json.dumps({"tool": "finish", "purpose": "fake cite", "summary": "依据 https://example.org/fake"})
    async def read(_): return {"content": "x=1"}
    r = asyncio.run(run_coding(task(role="coding"), model, {"read_workspace_file": ({}, read)}, noop, noop, max_turns=3))
    assert r["status"] == "incomplete"


def test_real_mcp_file_read_then_research_handoff(tmp_path, monkeypatch):
    """Real MCP subprocess and private filesystem; scripted LLM/paper evidence."""
    from backend.files import service
    from backend.server.coding_tools import build_coding_tools
    paper = "https://arxiv.org/abs/1706.03762"
    monkeypatch.setenv("ASTERIA_WORKSPACES_ROOT", str(tmp_path / "workspaces"))
    service.apply_file("collaboration-test", {"id": "fixture", "path": "attention_demo.py", "operation": "write",
                       "content": "softmax(q @ k.T) @ v", "expected_version": None})
    counters = {"coding": 0, "research": 0}
    async def model(system, raw):
        data = json.loads(raw)
        if "assignment" in data:
            counters["coding"] += 1
            if counters["coding"] == 1:
                return json.dumps({"tool": "read_workspace_file", "purpose": "读取实际文件", "arguments": {"name": "attention_demo.py"}})
            if counters["coding"] == 2:
                assert "softmax" in str(data["observations"])
                return json.dumps({"tool": "request_research", "purpose": "核对原理", "arguments": {
                    "question": "注意力计算为什么需要缩放因子？", "observed_problem": "已经读取实际文件，当前实现只有qk乘积，没有缩放", "expected_answer": "论文中的缩放因子和依据"}})
            return json.dumps({"tool": "finish", "purpose": "解释修改建议", "summary": "实际读取后建议核对缩放项；未运行代码"})
        counters["research"] += 1
        return json.dumps({"tool": "retrieve" if counters["research"] == 1 else "finish", "purpose": "定向核对",
                           "query": "attention scaling", "summary": "Evidence " + paper})
    r = runtime(tmp_path, model, build_coding_tools("collaboration-test"))
    r.plan, r.online_rag = {}, True
    r.library.papers[paper] = {}
    async def retrieve(*args):
        return json.dumps([{"source": paper, "page": 4, "text": "Attention scaling fixture"}])
    r.library.retrieve = retrieve
    result = asyncio.run(r.dispatch_assignments([task(role="coding", goals=())]))[0]
    assert result["status"] == "completed"
    assert result["tool_results"][0]["result"][0]["exists"] is True
    assert result["research_requests"][0]["status"] == "completed"
    assert service.read("other-user", "attention_demo.py")["exists"] is False
