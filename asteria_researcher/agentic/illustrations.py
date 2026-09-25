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
import unicodedata
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

PLOT_LOCK = threading.Lock()  # matplotlib has process-global state


def normalized_excerpt(text):
    # PDFs wrap words across lines and use typographic ligatures. These are
    # layout differences, not factual edits. Preserve all words and numbers.
    text = unicodedata.normalize('NFKC', text)
    text = text.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'}))
    text = re.sub(r'(?<=\w)-\s*(?=\w)', '', text)
    return re.sub(r'\s+', ' ', text).strip()


class Datum(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=70)
    cells: list[str] = Field(default_factory=list, max_length=5, description='Short display labels (prefer <=25 Chinese characters or 6 English words). Put detailed explanation in caption/context, not in chart cells.')
    value: float | None = Field(default=None, allow_inf_nan=False)
    evidence_id: str
    quote: str = Field(min_length=12, max_length=1500)
    cell_evidence_ids: list[list[str]] = Field(default_factory=list, description='For matrices: one list per cell, linking that cell to supporting full evidence IDs. Empty cell list only for explicitly unknown/not applicable entries.')
    metric: str = Field(default='', description='For bars: metric name including threshold/unit. Use ONE metric per chart.')


class Chart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,40}$')
    kind: Literal['matrix', 'bar']
    title: str = Field(min_length=1, max_length=120)
    caption: str = Field(min_length=1, max_length=1200)
    row_header: str = Field(default='方法 / 维度', max_length=50)
    columns: list[str] = Field(default_factory=list, max_length=5, description='Headers for cells only; the label column has row_header')
    context: str = Field(default='', max_length=1000, description='Metric/unit/dataset/split/protocol, or qualitative classification basis')
    rows: list[Datum] = Field(min_length=2, max_length=12)

    @model_validator(mode='after')
    def separate_label_header(self):
        # Common table notation includes the row-label header in columns.
        # Move it without changing/removing any data, rather than reject a valid table.
        if self.kind == 'matrix' and self.columns and all(len(r.cells) == len(self.columns)-1 for r in self.rows):
            self.row_header, self.columns = self.columns[0], self.columns[1:]
        return self


class Analysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rationale: str
    charts: list[Chart] = Field(default_factory=list, max_length=4)
    limitations: list[str] = Field(default_factory=list)


class DisplayRow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chart_id: str
    row: int
    cells: list[str]


class DisplayLabels(BaseModel):
    rows: list[DisplayRow]


def writer_chart_brief(manifest: dict) -> dict:
    """Hand off accepted figures, not the analyst's stale planning narrative.

    Planning rationale/captions can describe a discarded chart or a previous
    version of its cells. The immutable manifest keeps that audit history;
    Writer receives the actual rendered labels plus original row provenance.
    """
    return {
        'charts': [{key: value for key, value in chart.items() if key != 'caption'}
                   for chart in manifest.get('charts', [])],
        'limitations': manifest.get('limitations', []),
        'instruction': 'Describe only the accepted figures below. display_cells are the labels actually rendered; '
                       'rows retain full descriptions and source excerpts. Distinguish a documented mechanism '
                       'from an independently evaluated effect. Do not infer that the field lacks a benchmark '
                       'from the absence of one in this reading sample. Omitted charts were not delivered.'}


def citation_chart_brief(manifest: dict) -> dict:
    """Only the rendered cells needed to check prose/figure consistency.

    Evidence excerpts remain in CitationAgent's separately verified catalog;
    repeating analyst drafts and source quotes in every citation batch would
    inflate context and risk treating a chart as original evidence.
    """
    return {'charts': [{
        'id': chart['id'],
        'title': chart['title'],
        'columns': chart.get('columns', []),
        'row_labels': [row['label'] for row in chart.get('rows', [])],
        'display_cells': chart.get('display_cells', []),
    } for chart in manifest.get('charts', [])]}


def validate_chart(chart: Chart, evidence: dict) -> None:
    if chart.kind == 'matrix' and not chart.columns:
        raise ValueError('Matrix needs column labels')
    if chart.kind == 'bar' and not chart.context.strip():
        raise ValueError('Bar chart needs common metric, unit, dataset and protocol')
    for row in chart.rows:
        item = evidence.get(row.evidence_id)
        if not item or normalized_excerpt(row.quote) not in normalized_excerpt(item['text']):
            raise ValueError(f'{row.label}: quote must be an exact excerpt from its evidence_id')
        if chart.kind == 'matrix':
            if len(row.cells) != len(chart.columns):
                raise ValueError(f'{chart.id}/{row.label}: expected {len(chart.columns)} cells for columns {chart.columns}, got {len(row.cells)}')
            if row.value is not None:
                raise ValueError('Qualitative matrices must not invent numeric scores')
            if row.cell_evidence_ids:
                if len(row.cell_evidence_ids) != len(row.cells):
                    raise ValueError('Cell provenance must follow the matrix columns')
                if any(key not in evidence for ids in row.cell_evidence_ids for key in ids):
                    raise ValueError('Cell provenance references unknown evidence')
        else:
            numbers = re.findall(r'(?<![\w.])-?\d+(?:\.\d+)?', row.quote)
            if row.value is None or row.value not in [float(n) for n in numbers]:
                raise ValueError('Bar value must appear in the quoted source; derived numbers need a separate calculation tool')
    if chart.kind == 'bar' and len({r.evidence_id for r in chart.rows}) > 1:
        # Require a single original comparison table instead of trusting an LLM's
        # claim that results from independent papers share an evaluation protocol.
        raise ValueError('Numeric comparisons currently require one shared source excerpt/table')
    if chart.kind == 'bar' and len({r.metric.strip().lower() for r in chart.rows}) > 1:
        raise ValueError('Use separate charts for different metrics, even within the same paper/table')


def render_chart(chart: Chart, path: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib import font_manager, rc_context
    with PLOT_LOCK:
        installed = {f.name for f in font_manager.fontManager.ttflist}
        fonts = [f for f in ['Arial Unicode MS', 'Noto Sans CJK SC', 'SimHei', 'DejaVu Sans'] if f in installed]
        with rc_context({'font.family': fonts, 'axes.unicode_minus': False}):
            # CJK glyphs occupy about twice an ASCII glyph's width. Reserve
            # physical space per text line, then normalize table row heights.
            # The previous axes-relative heights summed above 1 and overlapped
            # the title; ordinary textwrap also undercounted Chinese widths.
            measuring = Figure(figsize=(8.5, 1), dpi=180)
            renderer = FigureCanvasAgg(measuring).get_renderer()
            def wrap(text, width, size=11):
                font = font_manager.FontProperties(family=fonts, size=size)
                fits = lambda s: renderer.get_text_width_height_descent(s, font, False)[0] <= width
                lines, line = [], ''
                for token in re.findall(r'[A-Za-z0-9_./@%+\-]+|\n|[^\S\n]+|.', text):
                    if token == '\n' or (line and not fits(line + token)):
                        lines.append(line.rstrip())
                        line = ''
                    if token == '\n':
                        continue
                    for char in token:
                        if line and not fits(line + char):
                            lines.append(line.rstrip())
                            line = ''
                        line += char
                return '\n'.join([*lines, line.rstrip()])
            width = 8.5 * .95 * 180 / (len(chart.columns) + 1) * .86
            cells = [[wrap(r.label, width), *[wrap(s, width) for s in r.cells]] for r in chart.rows]
            headers = [wrap(s, width) for s in [chart.row_header, *chart.columns]]
            heights = [.20 * max(s.count('\n') + 1 for s in row) + .20 for row in [headers, *cells]]
            table_height = sum(heights)
            title = wrap(chart.title, 8.1 * 180, size=13)
            title_height = .28 * (title.count('\n') + 1) + .30
            fig = Figure(figsize=(8.5, table_height + title_height + .25 if chart.kind == 'matrix' else max(3.2, .5*len(chart.rows)+1.5)), dpi=180)
            FigureCanvasAgg(fig)
            if chart.kind == 'matrix':
                ax = fig.add_axes([.025, .025, .95, table_height / fig.get_figheight()])
                ax.axis('off')
                table = ax.table(cellText=cells, colLabels=headers, cellLoc='left', bbox=[0, 0, 1, 1])
                table.auto_set_font_size(False)
                table.set_fontsize(11)
                for (i, j), cell in table.get_celld().items():
                    cell.set_edgecolor('#dbe4ed')
                    cell.set_facecolor('#183c59' if i == 0 else '#f0f5fa' if i % 2 else '#ffffff')
                    cell.set_text_props(color='white' if i == 0 else '#16324f')
                    cell.set_height(heights[i] / table_height)
                    cell.PAD = .055
                fig.text(.025, .98, title, va='top', fontsize=13, color='#16324f')
            else:
                ax = fig.add_subplot()
                ax.barh([r.label for r in chart.rows], [r.value for r in chart.rows], color='#247e94')
                ax.invert_yaxis()
                ax.set_xlabel(chart.context)
                ax.spines[['top', 'right']].set_visible(False)
                ax.set_title(chart.title, fontsize=14, pad=22, color='#16324f')
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, bbox_inches='tight', facecolor='white')


async def analyze(model, event, folder: Path, task: str, synthesis: str, briefs: list, evidence: dict, *, cached_plan=None):
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
              'figure exists return charts=[] with an honest rationale. For method comparisons prefer one paper/method '
              'per row with columns for representation, mechanism and limitation; do NOT place several papers under '
              'one row and cite a single unrelated quotation. Provide cell_evidence_ids for every matrix cell: one '
              'list per column, containing the original excerpts that actually support that cell. Do not confuse '
              'similarly named papers: a source describing one method cannot establish another method\'s design. '
              'For bars use exactly one named metric per chart, with identical dataset/split/protocol. '
              'These charts support research decisions; hypotheses/experimental plans belong in the report, not '
              'dense figures masquerading as published evidence. Return ONLY JSON: ' + json.dumps(Analysis.model_json_schema()))
    payload = {'task': task, 'synthesis': synthesis, 'notes': briefs, 'evidence': evidence}
    try:
        for attempt in range(2):
            raw = cached_plan.read_text() if attempt == 0 and cached_plan else await model(system, payload)
            (folder / f'analysis-attempt-{attempt+1}.txt').write_text(raw)
            try:
                result = Analysis.model_validate_json(raw)
                if len({c.id for c in result.charts}) != len(result.charts):
                    raise ValueError('Duplicate chart IDs')
                issues, supported_charts, rejected_charts = [], [], []
                for chart in result.charts:
                    try:
                        validate_chart(chart, evidence)
                        supported_charts.append(chart)
                    except ValueError as error:
                        issues.append(f'{chart.id}: {error}')
                        rejected_charts.append({'chart': chart.model_dump(), 'reason': str(error)})
                if issues:
                    if attempt == 0 or not supported_charts:
                        raise ValueError('\n'.join(issues))
                    # A failed optional numeric figure must not discard valid
                    # qualitative figures. Preserve its diagnostics and tell the
                    # Writer exactly which evidence could not be visualized.
                    (folder/'rejected-charts.json').write_text(json.dumps(rejected_charts, ensure_ascii=False, indent=2))
                    result.charts = supported_charts
                    result.limitations += ['未交付图表 ' + issue for issue in issues]
                    await event('data_analyst', 'chart_omitted', 'incomplete',
                                '保留有证据的图表，未通过校验的图表单独记录', issues=issues)
                crowded = [{'chart': c.id, 'row': r.label, 'column': c.columns[i], 'text': s}
                           for c in result.charts if c.kind == 'matrix' for r in c.rows
                           for i, s in enumerate(r.cells) if len(s) > 65]
                if crowded and attempt == 0:
                    payload['previous_plan'] = raw
                    payload['layout_feedback'] = crowded
                    payload['repair_instruction'] = ('Shorten ONLY crowded display cells to concise labels, ideally <=25 Chinese characters or 6 English words. '
                        'Preserve meaning/conditions; keep original exact quotes/evidence IDs, rows and columns unchanged. '
                        'Detailed evidence belongs in quotes and the report, not whole paragraphs inside a figure. This is layout editing, not new research.')
                    continue
                break
            except ValueError as error:
                if attempt == 1:
                    raise
                payload['validation_feedback'] = str(error)[:2500]
                payload['previous_plan'] = raw
                payload['repair_instruction'] = 'Correct only the reported issue in the previous plan; preserve valid rows and exact source excerpts.'
        # Rendering text is separate from the original data. Source quotes and
        # full analysis remain immutable; only the visible labels are condensed.
        crowded_rows = [{'chart_id': c.id, 'row': i, 'label': r.label, 'columns': c.columns, 'cells': r.cells}
                        for c in result.charts if c.kind == 'matrix' for i, r in enumerate(c.rows)
                        if any(len(s) > 65 for s in r.cells)]
        display_rows = {}
        if crowded_rows:
            raw = await model('You are editing figure labels, not doing research. Condense each supplied cell to a short label '
                '(prefer 8-20 Chinese characters or 3-6 English words). Preserve comparison meaning and uncertainty. '
                'Do not add facts or numbers. Preserve chart_id, row, number/order of cells. Full descriptions and '
                'quotes are retained separately, so do NOT reproduce them. Return JSON: '
                + json.dumps(DisplayLabels.model_json_schema()), {'rows': crowded_rows})
            (folder/'chart-display-labels.json').write_text(raw)
            labels = DisplayLabels.model_validate_json(raw)
            expected = {(r['chart_id'], r['row']): len(r['cells']) for r in crowded_rows}
            for row in labels.rows:
                key = (row.chart_id, row.row)
                if key not in expected or key in display_rows or len(row.cells) != expected[key]:
                    raise ValueError('Figure label editing changed row/column identity')
                # Preserve all remaining text. Wrapping, never character slicing,
                # handles long labels without dropping qualifications/numbers.
                display_rows[key] = row.cells
            if display_rows.keys() != expected.keys():
                raise ValueError('Figure label editing omitted rows')
        assets, manifests = {}, []
        for chart in result.charts:
            key = 'figures/' + chart.id + '.png'
            path = folder / key
            render_id = uuid4().hex
            await event('data_analyst', 'render_chart', 'started', chart.title, call_id=render_id, parent_call_id=call_id)
            try:
                display_chart = chart.model_copy(deep=True)
                for i, row in enumerate(display_chart.rows):
                    row.cells = display_rows.get((chart.id, i), row.cells)
                await asyncio.to_thread(render_chart, display_chart, path)
            except BaseException:
                await event('data_analyst', 'render_chart', 'failed', chart.title, call_id=render_id, parent_call_id=call_id)
                raise
            assets[key] = path
            manifests.append({**chart.model_dump(), 'path': key,
                              'display_cells': [r.cells for r in display_chart.rows],
                              'sources': sorted({evidence[key]['source'] for r in chart.rows
                                                 for key in [r.evidence_id, *[k for ids in r.cell_evidence_ids for k in ids]]})})
            await event('data_analyst', 'render_chart', 'completed', chart.title, call_id=render_id, parent_call_id=call_id, path=key)
        manifest = {**result.model_dump(), 'charts': manifests, 'validation': 'Exact quotes/IDs checked; semantic interpretation still requires review'}
        (folder / 'analysis.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        await event('data_analyst', 'analyze', 'completed', result.rationale, call_id=call_id, charts=len(assets))
        return assets, manifest
    except BaseException:
        await event('data_analyst', 'analyze', 'failed', '图表分析未通过，未伪造或替代图表', call_id=call_id)
        raise
