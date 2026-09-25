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


def test_evidence_tail_and_late_ids_are_not_silently_deleted():
    from asteria_researcher.agentic.citation_agent import visible_evidence
    catalog = {f'e_{i}': {**CATALOG['e_1'], 'text': '背景' * 1400 + '关键结果位于末尾。'} for i in range(110)}
    shown = visible_evidence(catalog)
    assert len(shown) == 110 and shown['e_109']['text'].endswith('关键结果位于末尾。')
    assert shown['e_109']['text'] == catalog['e_109']['text']


def test_citation_can_read_omitted_full_passage_before_judging(tmp_path, monkeypatch):
    import asteria_researcher.agentic.citation_agent as module
    catalog = {**CATALOG, 'e_tail': {**CATALOG['e_1'], 'text': 'context ' * 600 + 'critical tail result'}}
    monkeypatch.setattr(module, 'select_evidence', lambda lines, all_items: {'e_1': all_items['e_1']})
    calls = []
    async def model(system, payload):
        calls.append(payload)
        if len(calls) == 1:
            schema = json.loads(system.split('Return ONLY JSON ', 1)[1])
            assert 'e_tail' not in schema['$defs']['CitationFinding']['properties']['evidence_ids']['items']['enum']
            assert 'e_tail' in schema['properties']['read_evidence_ids']['items']['enum']
            assert any(x['id'] == 'e_tail' for x in payload['evidence_index'])
            return json.dumps({'read_evidence_ids': ['e_tail']})
        assert next(x for x in payload['evidence'] if x['id']=='e_tail')['text'].endswith('critical tail result')
        return json.dumps({'findings': [{'line_id': 2, 'supported': True,
            'evidence_ids': ['e_tail'], 'reason': 'Full tail supports the claim'}]})
    assert SOURCE in asyncio.run(CitationAgent(model, emit, tmp_path).attach(REPORT, catalog, {SOURCE: {}}))
    assert len(calls) == 2


def test_evidence_retrieval_does_not_repeat_entire_catalog():
    from asteria_researcher.agentic.citation_agent import select_evidence, visible_evidence
    catalog = {f'e_{i}': {'source': f'https://example.org/{i}', 'text': ('background ' * 1000)} for i in range(30)}
    catalog['e_match'] = {'source': SOURCE, 'text': 'critical complete source ' * 500}
    chosen = select_evidence([{'text': f'Compare this method [source]({SOURCE})'}], visible_evidence(catalog))
    assert 'e_match' in chosen and len(chosen) < len(catalog)
    assert chosen['e_match']['text'] == catalog['e_match']['text']


@pytest.mark.parametrize('actually_supported', [True, False])
def test_index_only_citation_fetches_full_text_and_rejudges(tmp_path, monkeypatch, actually_supported):
    import asteria_researcher.agentic.citation_agent as module
    catalog = {**CATALOG, 'e_tail': {**CATALOG['e_1'], 'text': 'preview ' * 100 + ' decisive full passage'}}
    monkeypatch.setattr(module, 'select_evidence', lambda lines, items: {'e_1': items['e_1']})
    calls, events = [], []
    async def event(*args, **kwargs):
        events.append(args)
    async def model(system, payload):
        calls.append(True)
        if len(calls) == 1:
            assert 'e_tail' not in {x['id'] for x in payload['evidence']}
        else:
            assert next(x for x in payload['evidence'] if x['id']=='e_tail')['text'].endswith('decisive full passage')
            assert 'not accepted' in payload['read_feedback']['instruction']
        return json.dumps({'findings': [{'line_id': 2, 'supported': True if len(calls)==1 else actually_supported,
            'evidence_ids': ['e_tail'], 'reason': 'Reassessed against full text'}]})
    run = CitationAgent(model, event, tmp_path).attach(REPORT, catalog, {SOURCE: {}})
    if actually_supported:
        assert SOURCE in asyncio.run(run)
    else:
        with pytest.raises(module.CitationGapError):
            asyncio.run(run)
    assert len(calls) == 2
    assert not any(args[1]=='citation_contract_retry' for args in events)


def test_citation_receives_proposal_context_and_skips_table_headers():
    from asteria_researcher.agentic.citation_agent import factual_lines
    lines = factual_lines('# 综述\n## 候选研究方向\n### 方向 A\n建议消融：改变视角数量，实验尚未执行。\n| Method header | Dataset header |\n|---|---|\n| 方法一具有三维表示 | 只在室内验证 |')
    assert len(lines) == 2
    assert lines[0]['section'] == '综述 / 候选研究方向 / 方向 A'
    assert lines[1]['text'].startswith('| 方法一')


def test_methodological_judgment_needs_no_invented_citation(tmp_path):
    async def model(_system, payload):
        return json.dumps({'findings': [{'line_id': 2, 'supported': True, 'kind': 'analysis',
            'evidence_ids': [], 'reason': 'Methodological framing, no empirical claim'}]})
    report = '# 报告\n\n以下比较按评价协议组织，用于指导实验设计。\n'
    assert asyncio.run(CitationAgent(model, emit, tmp_path).attach(report, CATALOG, {SOURCE: {}})) == report


def test_repair_rechecks_only_changed_lines(tmp_path):
    report = REPORT + '\n尚无证据却宣称精度提高百分之九十，需要修正。\n'
    judged = []
    async def model(system, payload):
        if 'Repair ONLY' in system:
            return json.dumps({'replacements': [{'line_id': 4, 'text': '建议未来对准确率进行实验评估，目前尚未执行。'}]})
        judged.append([r['line_id'] for r in payload['report_lines']])
        return json.dumps({'findings': [{'line_id': r['line_id'], 'supported': r['line_id']==2 or len(judged)>1,
            'kind': 'factual' if r['line_id']==2 else 'recommendation',
            'evidence_ids': ['e_1'] if r['line_id']==2 else [], 'reason': 'source or explicit proposed experiment'}
            for r in payload['report_lines']]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach_with_repair(report, CATALOG, {SOURCE: {}}))
    assert judged == [[2, 4], [4]] and SOURCE in result


def test_bad_evidence_id_gets_one_contract_correction(tmp_path):
    calls = []
    async def model(_system, payload):
        calls.append(payload)
        if len(calls) == 2:
            assert "e_typo" in payload["validation_error"]
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
            "evidence_ids": ["e_typo" if len(calls) == 1 else "e_1"], "reason": "原文支持"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach(REPORT, CATALOG, {SOURCE: {}}))
    assert SOURCE in result and len(calls) == 2
    assert len(list(tmp_path.glob("citation-plan-*-raw.json"))) == 2


def test_invalid_id_retry_is_bounded(tmp_path):
    calls = []
    async def model(*args):
        calls.append(args)
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
            "evidence_ids": ["e_invented"], "reason": "incorrect"}]})
    with pytest.raises(ValueError, match="不存在"):
        asyncio.run(CitationAgent(model, emit, tmp_path).attach_with_repair(REPORT, CATALOG, {SOURCE: {}}))
    assert len(calls) == 2
    assert not (tmp_path / "citation-draft-2.md").exists()


def test_comparative_paragraph_may_use_more_than_five_excerpts(tmp_path):
    catalog = {f"e_{i}": {**CATALOG['e_1'], "text": f"Evidence {i}"} for i in range(6)}
    async def model(_system, payload):
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
            "evidence_ids": list(catalog), "reason": "six complementary excerpts"}]})
    assert SOURCE in asyncio.run(CitationAgent(model, emit, tmp_path).attach(REPORT, catalog, {SOURCE: {}}))


def test_repair_uses_exact_same_visible_evidence_and_source_feedback(tmp_path):
    other = "https://arxiv.org/abs/1810.04805"
    catalog = {f"e_{i}": {**CATALOG['e_1'], "text": f"Passage {i}"} for i in range(110)}
    catalog['e_late'] = {"source": other, "text": "Late source remains visible", "page": 1}
    original = REPORT.rstrip() + f" [incorrect]({other})\n"
    seen, repaired = None, False
    async def model(system, payload):
        nonlocal seen, repaired
        if "Repair ONLY" in system:
            repair_evidence = {v['id']: v['text'] for v in payload['evidence']}
            assert repair_evidence == seen
            assert 'e_late' in repair_evidence
            assert payload['gaps'][0]['unmatched_sources']
            repaired = True
            return json.dumps({"replacements": [{"line_id": 2, "text": REPORT.splitlines()[2]}]})
        seen = {v['id']: v['text'] for v in payload['evidence']}
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
            "evidence_ids": ['e_0'], "reason": "source supports text"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach_with_repair(original, catalog, {SOURCE: {}, other: {}}))
    assert repaired and other not in result
    assert len(list(tmp_path.glob('citation-plan-*-raw.json'))) == 2


def test_provider_failure_preserves_draft_without_paid_retry(tmp_path):
    calls = []
    async def model(*args):
        calls.append(args)
        raise RuntimeError("HTTP 402")
    with pytest.raises(RuntimeError, match="402"):
        asyncio.run(CitationAgent(model, emit, tmp_path).attach_with_repair(REPORT, CATALOG, {SOURCE: {}}))
    assert len(calls) == 1
    assert (tmp_path / "citation-draft-1.md").read_text() == REPORT
    assert json.loads((tmp_path / "citation-history.json").read_text()) == [
        {"attempt": 1, "status": "failed", "error_type": "RuntimeError"}]


def test_citation_agent_places_source_at_checked_line(tmp_path):
    async def model(_system, payload):
        assert payload["evidence"][0]["id"] == "e_1"
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
                                         "evidence_ids": ["e_1"], "reason": "原文摘要支持"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach(REPORT, CATALOG, {SOURCE: {}}))
    assert f"[来源]({SOURCE})" in result.splitlines()[2]
    assert json.loads((tmp_path / "citation-review.json").read_text())["status"] == "completed"


def test_citation_and_targeted_repair_receive_actual_figure_context(tmp_path):
    figures = {'charts': [{'display_cells': [['GALA', '渲染特征图 + 码本']],
                           'id': 'methods'}]}
    source = 'https://arxiv.org/abs/2508.14278'
    catalog = {'e_1': {'source': source, 'page': 4,
                       'text': 'GALA renders a language feature map with codebook attention.'}}
    report = '# 方法综述\n\n图中的码本方法都直接查询三维结构，因此它们完全不需要渲染特征图。\n'
    reviewed = False
    async def model(system, payload):
        nonlocal reviewed
        assert payload['figures'] == figures
        if 'Repair ONLY' in system:
            assert 'repair the prose to match' in system
            reviewed = True
            return json.dumps({'replacements': [{'line_id': 2,
                'text': '图中的 GALA 仍通过渲染特征图与码本查询，不能把所有码本方法归为直接三维查询。'}]})
        assert 'cross-check, not independent proof' in payload['instruction']
        return json.dumps({'findings': [{'line_id': 2, 'supported': reviewed,
            'evidence_ids': ['e_1'] if reviewed else [],
            'reason': 'The displayed GALA cell contradicts the all-direct-query summary'}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path, figures=figures).attach_with_repair(report, catalog, {source: {}}))
    assert reviewed and '不能把所有码本方法归为直接三维查询' in result and source in result


def test_citation_figure_handoff_excludes_analyst_drafts_and_quotes():
    from asteria_researcher.agentic.illustrations import citation_chart_brief
    manifest = {'rationale': 'stale plan', 'charts': [{
        'id': 'methods', 'title': '方法对照', 'columns': ['查询接口'],
        'rows': [{'label': 'GALA', 'quote': 'source excerpt', 'cells': ['outdated cell']}],
        'display_cells': [['渲染特征图 + 码本']], 'caption': 'stale caption',
    }]}
    brief = citation_chart_brief(manifest)
    assert brief['charts'][0] == {
        'id': 'methods', 'title': '方法对照', 'columns': ['查询接口'],
        'row_labels': ['GALA'], 'display_cells': [['渲染特征图 + 码本']]}
    assert 'source excerpt' not in json.dumps(brief)


def test_checked_public_citation_replaces_internal_evidence_marker(tmp_path):
    report = REPORT.rstrip() + '〔KB:e_3621e7d33dcb2c02〕\n'
    async def model(system, payload):
        return json.dumps({'findings': [{'line_id': 2, 'supported': True,
            'evidence_ids': ['e_1'], 'reason': 'Full passage supports the claim'}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach(report, CATALOG, {SOURCE: {}}))
    assert 'KB:e_' not in result and f'[来源]({SOURCE})' in result


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


def test_citation_agent_places_private_chunk_marker(tmp_path):
    private = "KB:" + "a" * 20
    async def model(_system, _payload):
        return json.dumps({"findings": [{"line_id": 2, "supported": True,
                                         "evidence_ids": ["e_private"], "reason": "实验室原始页段支持"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach(
        REPORT, {"e_private": {"source": private, "page": 3, "text": "原始资料指出了模型结构。"}},
        {private: {"title": "组内资料", "page": 3}}))
    assert f"〔{private}〕" in result


def test_citation_repair_rechecks_and_preserves_history(tmp_path):
    calls = 0
    async def model(system, payload):
        nonlocal calls
        calls += 1
        if "Repair ONLY" in system:
            return json.dumps({"replacements": [{"line_id": 2, "text": "该方法基于注意力机制进行序列建模，目前所读摘要不足以确认其具体实验效果。"}]})
        return json.dumps({"findings": [{"line_id": 2, "supported": calls > 1,
            "evidence_ids": ["e_1"] if calls > 1 else [], "reason": "补足限定条件"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach_with_repair(REPORT, CATALOG, {SOURCE: {}}))
    assert "目前所读摘要不足" in result and calls == 3
    assert [r["status"] for r in json.loads((tmp_path / "citation-history.json").read_text())] == ["incomplete", "completed"]


def test_citation_repairs_are_bounded(tmp_path):
    async def model(system, payload):
        if "Repair ONLY" in system:
            return json.dumps({"replacements": [{"line_id": 2, "text": REPORT.splitlines()[2]}]})
        return json.dumps({"findings": [{"line_id": 2, "supported": False, "reason": "仍缺证据"}]})
    with pytest.raises(ValueError, match="未获原文支持"):
        asyncio.run(CitationAgent(model, emit, tmp_path).attach_with_repair(REPORT, CATALOG, {SOURCE: {}}, max_repairs=1))
    assert len(json.loads((tmp_path / "citation-history.json").read_text())) == 2


def test_table_citations_stay_inside_cell_and_code_is_excluded(tmp_path):
    report = "# 比较\n| 模型名称 | 方法描述 |\n| --- | --- |\n| Transformer | 该模型使用注意力机制处理序列信息并形成输出表示 |\n```python\nprint('this code is not a factual claim')\n```\n"
    async def model(system, payload):
        assert [row["line_id"] for row in payload["report_lines"]] == [3]
        return json.dumps({"findings": [{"line_id": 3, "supported": True, "evidence_ids": ["e_1"], "reason": "原文支持"}]})
    result = asyncio.run(CitationAgent(model, emit, tmp_path).attach(report, CATALOG, {SOURCE: {}}))
    assert result.splitlines()[3].count("|") == 3
    assert result.splitlines()[3].endswith(" |")


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
    async def no_reclassification(*_args):
        raise AssertionError("A confirmed plan must not be reclassified by a second model")
    runtime.partition_with_contract = no_reclassification
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
