import asyncio
import json
import pytest

from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.library import PaperLibrary, canonical
from asteria_researcher.agentic.primary_sources import extract_file
from asteria_researcher.agentic.sufficiency import ReviewPlan

URL = "https://arxiv.org/abs/1706.03762"
OTHER = "https://arxiv.org/abs/1810.04805"


class Embeddings:
    async def aembed_documents(self, texts):
        return [[1., float("watermark" in t.lower()), float(len(t) % 7)] for t in texts]


def test_review_runtime_loads_only_research_skills_initially(tmp_path):
    async def emit(*args, **kwargs):
        pass
    async def approve(*args, **kwargs):
        return None

    runtime = AutonomousReview(None, Embeddings(), emit, approve, tmp_path)
    assert list(runtime.research_skills.loaded) == ["literature_review"]
    from asteria_researcher.agentic.skill_catalog import SkillSession
    session = SkillSession("research")
    assert "temporal order of ideas" in session.load("source_priority")["content"].lower()
    with pytest.raises(ValueError):
        session.load("report_formatting")


def test_all_pages_are_available_to_reference_reader(tmp_path):
    import fitz
    path = tmp_path / "long.pdf"
    with fitz.open() as doc:
        for i in range(35):
            doc.new_page().insert_text((30, 30), "References" if i == 34 else "Research")
        doc.save(path)
    text, pages = extract_file(path, "application/pdf")
    assert len(pages) == 35 and "[Page 35]" in text and "References" in text


def test_graph_requires_bibliography_evidence_and_real_title_match(tmp_path, monkeypatch):
    async def model(system, payload):
        return json.dumps({"references": [
            {"title": "BERT", "quote": "Devlin. BERT. 2019."},
            {"title": "Fabricated paper", "quote": "Does not exist."}]})
    library = PaperLibrary(tmp_path, model, Embeddings())
    library.add({"url": URL, "title": "Transformer"})
    library.papers[URL] = {"text": "Research\nReferences\nDevlin. BERT. 2019."}
    async def search(query, **kwargs):
        return [library.add({"url": OTHER, "title": "BERT"})]
    monkeypatch.setattr(library, "search", search)
    result = asyncio.run(library.references(URL, "language models"))
    assert len(result["resolved"]) == 1
    assert len(library.edges) == 1 and len(result["unresolved"]) == 1
    edge = library.edges[(URL, OTHER)]
    assert edge["evidence"] == "Devlin. BERT. 2019."
    assert library.nodes[OTHER]["status"] == "discovered"


def test_shared_reads_are_deduplicated_and_download_budget_enforced(tmp_path, monkeypatch):
    from asteria_researcher.agentic import library as module
    calls = []
    async def read(url, consume_bytes):
        calls.append(url)
        await asyncio.sleep(.01)
        consume_bytes(8)
        return {"text": "paper", "pages": [{"page": 1, "text": "paper"}], "bytes": 8}
    monkeypatch.setattr(module, "read_paper", read)
    lib = PaperLibrary(tmp_path, None, Embeddings(), max_bytes=10)
    lib.add({"url": URL, "title": "paper"})
    async def check():
        await asyncio.gather(lib.read(URL), lib.read(URL + "v7"))
    asyncio.run(check())
    assert len(calls) == 1
    with pytest.raises(ValueError, match="预算"):
        lib.consume(3)


def test_subagents_have_independent_parallel_action_loops(tmp_path):
    active, peak = 0, 0
    by_agent = {}
    async def model(system, payload):
        nonlocal active, peak
        data = json.loads(payload)
        name = data["objective"]
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.01)
        active -= 1
        turn = by_agent.get(name, 0)
        by_agent[name] = turn + 1
        return json.dumps({"tool": "retrieve" if turn == 0 else "finish", "purpose": name,
                           "query": name, "summary": "Evidence " + URL})
    async def emit(*args): pass
    async def approve(*args): return None
    runtime = AutonomousReview(model, Embeddings(), emit, approve, tmp_path)
    runtime.query, runtime.plan = "broad review", {"scope": "broad review"}
    runtime.library.add({"url": URL, "title": "paper"})
    runtime.library.papers[URL] = {}
    async def retrieve(*args): return json.dumps([{"source": URL, "page": 1, "text": "evidence"}])
    runtime.library.retrieve = retrieve
    async def run():
        return await asyncio.gather(runtime.loop("a", "robustness"), runtime.loop("b", "security"))
    results = asyncio.run(run())
    assert peak == 2 and all(r["status"] == "completed" for r in results)
    assert by_agent == {"robustness": 2, "security": 2}


def test_lead_can_delegate_unresolved_work_and_merge_shared_evidence(tmp_path):
    calls = {}

    async def model(system, payload):
        data = json.loads(payload)
        objective = data["objective"]
        turn = calls.get(objective, 0)
        calls[objective] = turn + 1
        if objective == "broad review":
            return json.dumps({
                "tool": "delegate" if turn == 0 else "finish",
                "purpose": "split unresolved research goals",
                "assignments": [
                    {"name": "method", "objective": "method evidence", "goal_ids": []},
                    {"name": "evaluation", "objective": "evaluation evidence", "goal_ids": []},
                ] if turn == 0 else [],
                "summary": "Merged evidence " + URL,
            })
        return json.dumps({
            "tool": "retrieve" if turn == 0 else "finish",
            "purpose": objective,
            "query": objective,
            "summary": "Child evidence " + URL,
        })

    async def emit(*args, **kwargs):
        pass

    async def approve(*args):
        return None

    runtime = AutonomousReview(model, Embeddings(), emit, approve, tmp_path, online_rag=True)
    runtime.query, runtime.plan = "broad review", {}
    runtime.library.papers[URL] = {}

    async def retrieve(*args):
        return json.dumps([{"source": URL, "page": 1, "text": "shared child evidence"}])

    runtime.library.retrieve = retrieve
    result = asyncio.run(runtime.loop("lead", "broad review", lead=True, steps=2))

    assert result["status"] == "completed"
    assert runtime.children == 2
    assert len(runtime.evidence) == 2
    assert all(name.startswith("method") or name.startswith("evaluation") or name == "broad review"
               for name in calls)


def test_adaptive_replan_changes_strategy_but_preserves_confirmed_contract(tmp_path):
    events = []
    async def emit(*args, **kwargs):
        events.append((args, kwargs))

    async def approve(*args):
        return None

    runtime = AutonomousReview(None, None, emit, approve, tmp_path, online_rag=False)
    runtime.query = "比较数字水印方法"
    runtime.user_scope = runtime.query
    runtime.plan = {
        "scope": runtime.query,
        "perspectives": [{"name": "初始方法", "query": "初始方法"}],
        "required_goals": [{"id": "g1", "description": "比较方法", "user_quote": "比较数字水印方法"}],
        "process_requirements": [],
        "delivery_constraints": ["中文"],
        "optional_extensions": [],
    }

    async def replan(*args):
        return ReviewPlan.model_validate({
            **runtime.plan,
            "perspectives": [{"name": "证据缺口", "query": "数字水印实验对比"}],
            "optional_extensions": ["追踪基础方法"],
        })

    runtime.plan_with_contract = replan
    result = asyncio.run(runtime.adaptive_replan([{"tool": "search", "result": "未覆盖实验对比"}]))

    assert result["revision"] == 1
    assert runtime.plan["required_goals"][0]["id"] == "g1"
    assert runtime.plan["delivery_constraints"] == ["中文"]
    assert runtime.plan["perspectives"][0]["name"] == "证据缺口"
    assert (runtime.folder / "plan-revision-1.json").exists()
    assert any(item[0][0] == "agent_action" and item[0][1]["tool"] == "plan_revised" for item in events)


def test_subagent_cannot_delegate_and_tool_failure_is_observed(tmp_path):
    seen = []
    async def model(system, payload):
        data = json.loads(payload)
        seen.append(data)
        tools = ["delegate", "read", "finish"]
        return json.dumps({"tool": tools[min(len(seen) - 1, 2)], "purpose": "test", "paper_ids": [URL], "summary": "done"})
    async def emit(*args): pass
    async def approve(*args): return None
    runtime = AutonomousReview(model, Embeddings(), emit, approve, tmp_path)
    runtime.query, runtime.plan = "review", {}
    result = asyncio.run(runtime.loop("child", "test", steps=3))
    assert result["status"] == "incomplete"
    assert "permissions" in seen[1]["observations"][0]["error"]
    assert "error" in seen[2]["observations"][-1]["result"][0]


def test_canonical_deduplicates_arxiv_versions():
    assert canonical(URL + "v7") == canonical("https://arxiv.org/pdf/1706.03762v1.pdf")


def test_embedding_preflight_stops_before_model_spending(tmp_path):
    async def model(*args):
        pytest.fail("must not spend LLM quota when retrieval dependency is down")
    class BrokenEmbedding:
        async def aembed_documents(self, texts):
            raise RuntimeError("Metal initialization failed")
    async def emit(*args): pass
    async def approve(*args): pass
    runtime = AutonomousReview(model, BrokenEmbedding(), emit, approve, tmp_path)
    with pytest.raises(RuntimeError, match="embedding 服务检查失败"):
        asyncio.run(runtime.run("broad review"))


def test_large_pdf_stream_exceeds_old_limit_without_truncation(tmp_path, monkeypatch):
    import httpx
    from asteria_researcher.agentic import primary_sources as source
    real = httpx.AsyncClient
    total = 13 * 1048576
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(total // 65536):
                yield b"x" * 65536
    monkeypatch.setattr(source.httpx, "AsyncClient", lambda **kwargs:
        real(transport=httpx.MockTransport(lambda request: httpx.Response(200,
             headers={"content-type": "application/pdf"}, stream=Stream()))))
    monkeypatch.setattr(source, "extract_file", lambda path, kind:
        ("full text", [{"page": 1, "text": "full text"}]))
    result = asyncio.run(source.read_paper(URL))
    assert result["bytes"] == total and result["extraction_limit"] is None


def test_hybrid_retrieval_retains_source_and_page(tmp_path):
    library = PaperLibrary(tmp_path, None, Embeddings())
    library.add({"url": URL, "title": "Paper"})
    library.papers[URL] = {"pages": [{"page": i, "text": ("watermark robustness method " * 50)} for i in range(1, 8)]}
    result = json.loads(asyncio.run(library.retrieve("watermark robustness")))
    assert result and all(r["source"] == URL and 1 <= r["page"] <= 7 for r in result)


def test_direct_reader_paginates_without_losing_text(tmp_path):
    lib = PaperLibrary(tmp_path, None, None)
    lib.add({"url": URL, "title": "Paper"})
    lib.papers[URL] = {"pages": [{"page": 1, "text": "a" * 12000}, {"page": 2, "text": "end"}]}
    first = lib.read_passage(URL)
    second = lib.read_passage(URL, **first["next"])
    third = lib.read_passage(URL, **second["next"])
    assert first["text"] + second["text"] == "a" * 12000
    assert third["text"] == "end" and third["next"] is None
    with pytest.raises(ValueError):
        lib.read_passage(URL, page=3)


def test_direct_mode_no_embeddings_and_rejects_retrieve(tmp_path):
    turns = []
    async def model(system, payload):
        data = json.loads(payload)
        turns.append(data)
        tool = ["retrieve", "read_passage", "finish"][len(turns) - 1]
        return json.dumps({"tool": tool, "purpose": "read evidence", "paper_ids": [URL], "summary": "Finding " + URL})
    async def emit(*args): pass
    async def approve(*args): pass
    runtime = AutonomousReview(model, None, emit, approve, tmp_path, online_rag=False)
    runtime.query, runtime.plan = "review", {}
    runtime.library.add({"url": URL, "title": "Paper"})
    runtime.library.papers[URL] = {"pages": [{"page": 1, "text": "source evidence"}]}
    async def research():
        result = await runtime.loop("researcher", "read paper", steps=3)
        assert result["status"] == "completed"
        return "report"
    runtime.research = research
    assert asyncio.run(runtime.run("review")) == "report"
    assert "关闭在线 RAG" in turns[1]["observations"][0]["error"]
    metadata = json.loads((runtime.folder / "run.json").read_text())
    assert metadata["evidence_mode"] == "direct" and metadata["embedding_calls"] == 0
    assert runtime.evidence[0]["passages"][0]["text"] == "source evidence"


def test_rag_option_is_strict_boolean(tmp_path):
    with pytest.raises(ValueError, match="boolean"):
        AutonomousReview(None, None, None, None, tmp_path, online_rag="false")


def test_child_is_told_local_budget_and_can_return_partial_result(tmp_path):
    seen = []
    async def model(system, payload):
        seen.append(json.loads(payload))
        return json.dumps({"tool": "finish", "purpose": "handoff", "outcome": "incomplete",
                           "summary": "原文服务不可用，尚未取得证据，请主 Agent 重新分配研究目标。"})
    async def emit(*args): pass
    runtime = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    runtime.query, runtime.plan = "review", {}
    result = asyncio.run(runtime.loop("child", "objective", steps=1))
    assert seen[0]["remaining_turns"] == 1 and seen[0]["handoff_required"]
    assert seen[0]["remaining_actions"] == runtime.max_actions - 5
    assert result["status"] == "incomplete" and "原文服务" in result["summary"]


def test_writer_repairs_length_and_keeps_audit_drafts(tmp_path):
    calls = []
    async def model(system, payload):
        if system.startswith("Select exactly ONE content skill"):
            return json.dumps({"skill_ids": ["report_writing"], "format_profile": "brief", "reason": "short review"})
        calls.append((system, json.loads(payload)))
        return ("水" * 500 if len(calls) == 1 else "水" * 250) + f" [source]({URL})"
    async def emit(*args): pass
    runtime = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    runtime.query, runtime.plan = "写约300字", {"perspectives": []}
    runtime.library.papers[URL] = {}
    runtime.evidence = [{"agent": "reader", "query": "test", "passages": [{"source": URL, "page": 1, "text": "evidence"}]}]
    report = asyncio.run(runtime.write_report("summary"))
    assert report.count("水") == 250 and len(calls) == 2
    assert "500" in calls[1][1]["length_issue"]
    assert "<skill id='report_writing'" in calls[0][0] and "<skill id='report_writing'" in calls[1][0]
    assert runtime.format_profile == "brief"
    assert "three compact paragraphs" not in calls[0][0]
    assert "not a mandatory chapter outline" in calls[0][0]
    assert (runtime.folder / "draft-1.md").exists() and (runtime.folder / "draft-2.md").exists()
