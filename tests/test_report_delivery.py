import shutil
import subprocess
import asyncio
from pathlib import Path

import pytest

from asteria_researcher.agentic.autonomous import Action, writing_briefs
from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.latex import render_tex, publish
from asteria_researcher.agentic.pdf_fonts import embed_unicode_maps
from asteria_researcher.agentic.report_tools import report_length, validate_report_draft
from asteria_researcher.agentic.citation_agent import CitationPlan, factual_lines


def test_bare_and_mixed_bibliography_urls_keep_body_numbers_aligned():
    report = ('[B](https://example.org/b) [A](https://example.org/a) [C](https://example.org/c)\n'
              '## 参考文献\n1. Title A — https://example.org/a\n'
              '2. [Title B](https://example.org/b)\n3. Title C — https://example.org/c （预印本）')
    body = render_tex(report).split(r'\section{参考文献}')[0]
    assert r'\href{https://example.org/b}{[2]}' in body
    assert r'\href{https://example.org/a}{[1]}' in body
    assert r'\href{https://example.org/c}{[3]}' in body


def test_citation_explanation_length_is_not_a_delivery_gate():
    reason = '原文支持该结论，但它仍有适用条件。' * 100
    plan = CitationPlan(findings=[{'line_id': 1, 'supported': True, 'reason': reason}])
    assert plan.findings[0].reason == reason
    assert factual_lines('## 参考资料\n这里是参考资料而不是待逐句检查的报告正文。') == []


def test_handoff_keeps_conditions_without_duplicate_raw_evidence():
    action = Action(tool="finish", purpose="回传发现", summary="两组实验不可混比", findings=[{
        "conclusion": "方法在全量集更好", "conditions": "5000题；同一准确率指标；基线55.18%",
        "sources": ["https://example.org/paper"], "limitations": "子集结果不可混用"}])
    brief = {**action.model_dump(), "evidence": [{"text": "原文" * 1000}], "artifact": "subagent-1.json"}
    writer = writing_briefs([brief])[0]
    assert writer['findings'] == brief['findings']
    assert writer['summary'] == brief['summary']
    assert 'evidence' not in writer and writer['artifact'] == 'subagent-1.json'


def test_body_length_counts_english_but_not_citations_or_references():
    text = '# 结论\n研究方法 agent memory 12.5% [来源](https://example.org/long-path)\n## 参考文献\n很多参考内容'
    assert report_length(text)['length_units'] == 9  # 6 CJK + 3 words
    short = validate_report_draft(text, ['https://example.org/long-path'], target_chars=100, min_length_ratio=.8)
    assert any('篇幅不足' in issue for issue in short['issues'])
    approximate = validate_report_draft(text, ['https://example.org/long-path'], target_chars=100,
                                        min_length_ratio=.8, enforce_length=False)
    assert approximate['ok'] and approximate['warnings']


def test_pdf_keeps_emphasis_code_and_numbered_links():
    text = '# 报告\n**结论** `file_name` [来源](https://example.org/a)\n## 参考文献\n- [论文标题](https://example.org/a)'
    tex = render_tex(text)
    assert r'\textbf{结论}' in tex
    assert r'\texttt{file\_name}' in tex
    assert r'\href{https://example.org/a}{[1]}' in tex
    assert r'{[1] 论文标题}' in tex
    assert r'\input{' not in render_tex(r'**\input{/etc/passwd}**')
    reordered = render_tex('[B](https://example.org/b) [A](https://example.org/a)\n## 参考文献\n1. [A](https://example.org/a)\n2. [B](https://example.org/b)')
    assert r'\href{https://example.org/b}{[2]}' in reordered


def test_math_symbols_and_long_table_identifiers_remain_readable():
    tex = render_tex('a≈b $\\ell_{cons}$\n\n| 数据 | 来源 |\n|---|---|\n| ScanNet200/ARKitScenes mAP/AP@25/AP@50 | [原文](https://example.org/long/path) |')
    assert r'\ensuremath{\approx}' in tex and r'\ell_{cons}' in tex
    assert r'\allowbreak{}' in tex and r'\raggedright\arraybackslash' in tex
    assert r'\href{https://example.org/long/path}' in tex
    assert r'\ensuremath{\neq}' in render_tex('可见性≠前景IoU')
    assert r'\(\eta=0.9\)' in render_tex(r'$\eta=0.9$')


def test_escaped_math_literals_do_not_become_tex_comments():
    from asteria_researcher.agentic.latex import sanitize_math
    assert sanitize_math(r's_0=15\%') == r's_0=15\%'
    for symbol in '%&#$_{}':
        assert sanitize_math('\\' + symbol) == '\\' + symbol
    assert r'\input' not in sanitize_math(r'\input{/etc/passwd}')


@pytest.mark.skipif(not shutil.which('xelatex'), reason='XeLaTeX required')
def test_real_pdf_compiles_math_percentage(tmp_path):
    result = asyncio.run(publish('# 公式回归\n\n固定尺度 $s_0=15\\%$；阈值 $\\eta=0.9$。', tmp_path))
    assert Path(result['latex_pdf']).read_bytes().startswith(b'%PDF-')
    assert 'Missing character' not in Path(result['compile_log']).read_text()


def test_compiler_start_failure_does_not_stay_compiling(tmp_path, monkeypatch):
    import json
    import asteria_researcher.agentic.latex as module
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/test/xelatex')
    async def broken(*args, **kwargs):
        raise OSError('compiler unavailable')
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', broken)
    with pytest.raises(OSError):
        asyncio.run(publish('# 报告\n正文', tmp_path))
    state = json.loads(next(tmp_path.glob('scientific_*/publication.json')).read_text())
    assert state['status'] == 'failed' and state['error_type'] == 'OSError'


def test_unread_future_reading_is_repaired_locally_not_regenerated(tmp_path):
    import json
    source = 'https://arxiv.org/abs/1706.03762'
    unread = 'https://arxiv.org/abs/1810.04805'
    report = f'# 研究报告\n已有证据支持注意力机制。[来源]({source})\n\n后续阅读（未读）：[候选]({unread})\n## 参考文献\n- [已读]({source})\n- [未读]({unread})'
    calls = []
    async def model(system, payload):
        if system.startswith('Select exactly ONE content skill'):
            return json.dumps({'content_skill': 'report_writing', 'format_profile': 'brief', 'reason': 'review'})
        calls.append(system)
        if system.startswith('Repair only these lines'):
            lines = json.loads(payload)['lines']
            return json.dumps({'replacements': [{'line_id': r['line_id'], 'text': '' if r['text'].startswith('-') else '后续阅读：候选（未读，不作为证据）'} for r in lines]})
        return report
    async def emit(*args): pass
    runtime = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    runtime.query, runtime.plan = '研究报告', {}
    runtime.library.papers[source] = {}
    result = asyncio.run(runtime.write_report('synthesis'))
    assert unread not in result and source in result
    assert '后续阅读：候选（未读，不作为证据）' in result
    assert len(calls) == 2


def test_approximate_length_never_restarts_research_or_blocks_delivery(tmp_path):
    import json
    calls = []
    source = 'https://arxiv.org/abs/1706.03762'
    async def model(system, payload):
        if system.startswith('Select exactly ONE content skill'):
            return json.dumps({'content_skill':'report_writing', 'format_profile':'brief', 'reason':'review'})
        calls.append(system)
        return '研究' * 250 + f' [来源]({source})'
    async def emit(*args): pass
    runtime = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    runtime.query, runtime.plan = '写约300字综述', {'perspectives': []}
    runtime.library.papers[source] = {}
    result = asyncio.run(runtime.write_report('synthesis'))
    assert len(calls) == 1  # Approximate length never triggers a rewrite.
    assert result.startswith('研究')


@pytest.mark.skipif(not shutil.which('xelatex') or not shutil.which('pdftoppm'), reason='Needs XeLaTeX and Poppler')
def test_pdf_renders_cjk_without_external_poppler_language_pack(tmp_path):
    paths = asyncio.run(publish('# 中文报告\n\n## 研究结论\n**中文正文**与 English。', tmp_path))
    pdf = Path(paths['latex_pdf'])
    assert embed_unicode_maps(pdf) == 0  # Idempotent; all maps already embedded.
    result = subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '500', '-png', str(pdf), str(tmp_path/'page')], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'Missing language pack' not in result.stderr
    assert 'Unknown font' not in result.stderr
    assert (tmp_path/'page.png').stat().st_size > 1000
