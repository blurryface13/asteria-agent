import asyncio
import json
from pathlib import Path
import shutil

import pytest

from asteria_researcher.agentic.anthropic_roles import role_guidance, ROOT
from asteria_researcher.agentic.illustrations import Chart, analyze, render_chart, validate_chart
from asteria_researcher.agentic.latex import publish, render_tex
from asteria_researcher.agentic.skill_catalog import SkillSession
from asteria_researcher.agentic.tool_hooks import ToolHooks


EVIDENCE = {'e1': {'source': 'https://example.org/paper',
                   'text': 'The method stores language features on 3D Gaussians. Baseline scores 12.5 and ours scores 14.2 on the same test split.'}}


def chart():
    return Chart(id='method-map', kind='matrix', title='方法证据对照', caption='定性对照，不表示实验排名。',
                 columns=['表示', '依据'], rows=[
                     {'label': '方法 A', 'cells': ['3D Gaussians', 'language features'], 'evidence_id': 'e1',
                      'quote': 'The method stores language features on 3D Gaussians.'},
                     {'label': '方法 B', 'cells': ['未确认', '未报告'], 'evidence_id': 'e1',
                      'quote': 'Baseline scores 12.5 and ours scores 14.2 on the same test split.'}])


def test_role_uses_verbatim_upstream_and_only_maps_bindings():
    raw = (ROOT / 'research_lead_agent.md').read_text()
    sentence = '* Avoid overlap between subagents - every subagent should have distinct, clearly separate tasks, to avoid replicating work unnecessarily and wasting resources.'
    assert sentence in raw and sentence in role_guidance(True)
    assert 'run_blocking_subagent' not in role_guidance(True)
    assert 'NEVER create a subagent to generate the final report' not in role_guidance(True)
    assert 'OODA' in role_guidance(False)
    assert 'MINIMUM of five' not in role_guidance(False)


def test_supported_handoff_is_not_rejected_by_arbitrary_finding_counts():
    from asteria_researcher.agentic.autonomous import Action
    value = {'conclusion': 'Across-paper synthesis', 'sources': [f'https://example.org/{i}' for i in range(10)]}
    action = Action(tool='finish', purpose='handoff', findings=[value] * 13)
    assert len(action.findings) == 13 and len(action.findings[0].sources) == 10


def test_finance_skills_are_discovered_before_their_bodies_are_loaded():
    session = SkillSession('research')
    assert 'anthropic_sector_overview' in {x['id'] for x in session.discover()}
    assert 'Market Size & Growth' not in session.prompt()
    session.load('anthropic_sector_overview')
    assert 'Market Size & Growth' in session.prompt()
    assert '不能假装生成或修改了工作簿' in session.prompt()


def test_financial_specialist_can_actually_load_upstream_skill():
    from backend.server.specialists import run_specialist
    seen = []
    async def model(system, payload):
        seen.append(system)
        if len(seen) == 1:
            assert 'anthropic_sector_overview' in payload
            return json.dumps({'action': 'tool', 'tool': 'load_skill', 'query': 'anthropic_sector_overview'})
        assert 'Market Size & Growth' in system
        return json.dumps({'action': 'answer', 'content': '请先确定行业范围和报告期；尚未检索财务资料。'})
    _, trace = asyncio.run(run_specialist('financial_research', '如何开展行业调研', [], model, None))
    assert any(s['id'] == 'anthropic_sector_overview' for s in trace['skills'])
    assert trace['tool_calls'][0]['tool'] == 'load_skill'


def test_chart_validation_requires_real_evidence_and_consistent_shape():
    good = chart()
    validate_chart(good, EVIDENCE)
    bad = good.model_copy(deep=True)
    bad.rows[0].quote = 'This sentence does not exist in the paper.'
    with pytest.raises(ValueError, match='exact excerpt'):
        validate_chart(bad, EVIDENCE)
    bad = good.model_copy(deep=True)
    bad.rows[0].cells = ['one']
    with pytest.raises(ValueError, match='cell count'):
        validate_chart(bad, EVIDENCE)


def test_bars_cannot_invent_scores_or_merge_different_protocols():
    bars = chart().model_copy(deep=True)
    bars.kind, bars.context = 'bar', 'same test split, score'
    bars.rows[0].quote = bars.rows[1].quote
    bars.rows[0].value, bars.rows[1].value = 12.5, 14.2
    validate_chart(bars, EVIDENCE)
    bars.rows[1].value = 97.8
    with pytest.raises(ValueError, match='Bar value'):
        validate_chart(bars, EVIDENCE)
    bars.rows[1].value, bars.rows[1].evidence_id = 14.2, 'e2'
    with pytest.raises(ValueError, match='one shared source'):
        validate_chart(bars, {**EVIDENCE, 'e2': EVIDENCE['e1']})


def test_renderer_rejects_unregistered_and_escaping_images():
    with pytest.raises(ValueError):
        render_tex('![image](../../private.png)', assets=['../../private.png'])
    with pytest.raises(ValueError):
        render_tex('![image](figures/missing.png)')
    tex = render_tex('![方法比较](figures/method-map.png)', assets=['figures/method-map.png'])
    assert r'\includegraphics' in tex and '方法比较' in tex


def test_parent_hook_context_isolated_across_parallel_tasks():
    hooks = ToolHooks('run')
    async def child(parent, call):
        token = hooks.parent.set(parent)
        await asyncio.sleep(0)
        record = hooks.record({'agent': call, 'tool': 'read', 'call_id': call, 'status': 'started', 'time': 1})
        hooks.parent.reset(token)
        return record
    async def run():
        return await asyncio.gather(child('p1', 'c1'), child('p2', 'c2'))
    records = asyncio.run(run())
    assert [r['parent_call_id'] for r in records] == ['p1', 'p2']
    end = hooks.record({'agent': 'c1', 'tool': 'read', 'call_id': 'c1', 'status': 'cancelled', 'time': 2})
    assert end['hook'] == 'ToolFailure' and end['parent_call_id'] == 'p1'
    assert 'c1' not in hooks.pending


def test_analyst_renders_manifest_and_provenance(tmp_path):
    async def model(system, payload):
        return json.dumps({'rationale': 'Show the method representation', 'charts': [chart().model_dump()]})
    events = []
    async def event(*args, **kwargs):
        events.append((args, kwargs))
    assets, manifest = asyncio.run(analyze(model, event, tmp_path, '带图报告', 'synthesis', [], EVIDENCE))
    assert assets['figures/method-map.png'].read_bytes().startswith(b'\x89PNG')
    assert manifest['charts'][0]['sources'] == ['https://example.org/paper']
    assert (tmp_path / 'analysis.json').is_file()
    assert [e[0][2] for e in events] == ['started', 'started', 'completed', 'completed']


@pytest.mark.skipif(not shutil.which('xelatex'), reason='Needs XeLaTeX')
def test_real_illustrated_chinese_pdf(tmp_path):
    path = tmp_path / 'chart.png'
    render_chart(chart(), path)
    result = asyncio.run(publish('# 中文图表测试\n\n![方法表示与证据对照](figures/method-map.png)\n\n图表为定性分析。',
                                 tmp_path, assets={'figures/method-map.png': path}))
    import fitz
    with fitz.open(result['latex_pdf']) as pdf:
        assert sum(len(page.get_images()) for page in pdf) >= 1
        assert '中文图表测试' in ''.join(page.get_text() for page in pdf)
    import zipfile
    with zipfile.ZipFile(result['report_bundle']) as archive:
        assert 'figures/method-map.png' in archive.namelist()
