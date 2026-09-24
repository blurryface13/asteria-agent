"""Evidence-backed Data Analyst: declarative charts, no model-generated code.

Research Agent demo's read-notes -> analyze -> chart -> writer handoff pattern.
The rendering tool is deterministic and never executes model Python or Shell.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import threading
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PLOT_LOCK = threading.Lock()  # matplotlib has process-global state


class Datum(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=70)
    cells: list[str] = Field(default_factory=list, max_length=5)
    value: float | None = Field(default=None, allow_inf_nan=False)
    evidence_id: str
    quote: str = Field(min_length=12, max_length=1500)


class Chart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,40}$')
    kind: Literal['matrix', 'bar']
    title: str = Field(min_length=1, max_length=120)
    caption: str = Field(min_length=1, max_length=1200)
    columns: list[str] = Field(default_factory=list, max_length=5)
    context: str = Field(default='', max_length=1000, description='Metric/unit/dataset/split/protocol, or qualitative classification basis')
    rows: list[Datum] = Field(min_length=2, max_length=12)


class Analysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rationale: str
    charts: list[Chart] = Field(default_factory=list, max_length=4)
    limitations: list[str] = Field(default_factory=list)


def validate_chart(chart: Chart, evidence: dict) -> None:
    if chart.kind == 'matrix' and not chart.columns:
        raise ValueError('Matrix needs column labels')
    if chart.kind == 'bar' and not chart.context.strip():
        raise ValueError('Bar chart needs common metric, unit, dataset and protocol')
    for row in chart.rows:
        item = evidence.get(row.evidence_id)
        normalize = lambda s: re.sub(r'\s+', ' ', s).strip()
        if not item or normalize(row.quote) not in normalize(item['text']):
            raise ValueError(f'{row.label}: quote must be an exact excerpt from its evidence_id')
        if chart.kind == 'matrix':
            if len(row.cells) != len(chart.columns) or any(len(s) > 120 for s in row.cells):
                raise ValueError('Matrix cell count/length mismatch')
            if row.value is not None:
                raise ValueError('Qualitative matrices must not invent numeric scores')
        else:
            numbers = re.findall(r'(?<![\w.])-?\d+(?:\.\d+)?', row.quote)
            if row.value is None or row.value not in [float(n) for n in numbers]:
                raise ValueError('Bar value must appear in the quoted source; derived numbers need a separate calculation tool')
    if chart.kind == 'bar' and len({r.evidence_id for r in chart.rows}) > 1:
        # Require a single original comparison table instead of trusting an LLM's
        # claim that results from independent papers share an evaluation protocol.
        raise ValueError('Numeric comparisons currently require one shared source excerpt/table')


def render_chart(chart: Chart, path: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib import font_manager, rc_context
    import textwrap
    with PLOT_LOCK:
        installed = {f.name for f in font_manager.fontManager.ttflist}
        fonts = [f for f in ['Arial Unicode MS', 'Noto Sans CJK SC', 'SimHei', 'DejaVu Sans'] if f in installed]
        with rc_context({'font.family': fonts, 'axes.unicode_minus': False}):
            fig = Figure(figsize=(11, max(3.2, .8 * len(chart.rows) + 1.5)), dpi=180)
            FigureCanvasAgg(fig)
            ax = fig.add_subplot()
            if chart.kind == 'matrix':
                ax.axis('off')
                wrap = lambda s: '\n'.join(textwrap.wrap(s, width=15, break_long_words=True))
                table = ax.table(cellText=[[wrap(r.label), *map(wrap, r.cells)] for r in chart.rows],
                                 colLabels=['Method / 方法', *chart.columns], cellLoc='left', loc='center')
                table.auto_set_font_size(False)
                table.set_fontsize(9)
                for (i, j), cell in table.get_celld().items():
                    cell.set_edgecolor('#dbe4ed')
                    cell.set_facecolor('#183c59' if i == 0 else '#f0f5fa' if i % 2 else '#ffffff')
                    cell.set_text_props(color='white' if i == 0 else '#16324f')
                    cell.set_height(.12 if i == 0 else max(.12, .055 * max(len(wrap(s).splitlines()) for s in [chart.rows[i-1].label, *chart.rows[i-1].cells])))
            else:
                ax.barh([r.label for r in chart.rows], [r.value for r in chart.rows], color='#247e94')
                ax.invert_yaxis()
                ax.set_xlabel(chart.context)
                ax.spines[['top', 'right']].set_visible(False)
            ax.set_title(chart.title, fontsize=14, pad=22, color='#16324f')
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, bbox_inches='tight', facecolor='white')


async def analyze(model, event, folder: Path, task: str, synthesis: str, briefs: list, evidence: dict):
    """Optional analyst role with validation feedback; cannot collect new facts."""
    call_id = uuid4().hex
    await event('data_analyst', 'analyze', 'started', '从原文证据规划图表', call_id=call_id)
    system = ('You are the Data Analyst in a research team. Read the supplied notes and original evidence, '
              'choose useful visual comparisons, then hand figures and provenance to the Report Writer. '
              'No new search, simulated values or invented results. Use a matrix for qualitative method taxonomy '
              'or limitations; use bars ONLY for a single original comparison table with one shared evaluation '
              'protocol. Each row requires a verbatim quote and its evidence_id. An exact quote is provenance, '
              'not proof of your interpretation: cells must be directly supported. Distinguish unknown from absent. '
              'Use short readable labels. Choose chart count for usefulness, not a quota. If no useful supported '
              'figure exists return charts=[] with an honest rationale. Return ONLY JSON: ' + json.dumps(Analysis.model_json_schema()))
    payload = {'task': task, 'synthesis': synthesis, 'notes': briefs, 'evidence': evidence}
    try:
        for attempt in range(2):
            raw = await model(system, payload)
            (folder / f'analysis-attempt-{attempt+1}.txt').write_text(raw)
            try:
                result = Analysis.model_validate_json(raw)
                if len({c.id for c in result.charts}) != len(result.charts):
                    raise ValueError('Duplicate chart IDs')
                for chart in result.charts:
                    validate_chart(chart, evidence)
                break
            except ValueError as error:
                if attempt == 1:
                    raise
                payload['validation_feedback'] = str(error)[:2500]
        assets, manifests = {}, []
        for chart in result.charts:
            key = 'figures/' + chart.id + '.png'
            path = folder / key
            render_id = uuid4().hex
            await event('data_analyst', 'render_chart', 'started', chart.title, call_id=render_id, parent_call_id=call_id)
            try:
                await asyncio.to_thread(render_chart, chart, path)
            except BaseException:
                await event('data_analyst', 'render_chart', 'failed', chart.title, call_id=render_id, parent_call_id=call_id)
                raise
            assets[key] = path
            manifests.append({**chart.model_dump(), 'path': key,
                              'sources': sorted({evidence[r.evidence_id]['source'] for r in chart.rows})})
            await event('data_analyst', 'render_chart', 'completed', chart.title, call_id=render_id, parent_call_id=call_id, path=key)
        manifest = {**result.model_dump(), 'charts': manifests, 'validation': 'Exact quotes/IDs checked; semantic interpretation still requires review'}
        (folder / 'analysis.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        await event('data_analyst', 'analyze', 'completed', result.rationale, call_id=call_id, charts=len(assets))
        return assets, manifest
    except BaseException:
        await event('data_analyst', 'analyze', 'failed', '图表分析未通过，未伪造或替代图表', call_id=call_id)
        raise
