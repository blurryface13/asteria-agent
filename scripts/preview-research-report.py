"""Render a clearly labelled offline preview without model calls or run changes."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main(source):
    from asteria_researcher.agentic.illustrations import Chart, render_chart
    from asteria_researcher.agentic.latex import publish
    source = source.resolve()
    if not source.is_relative_to(ROOT/'outputs'):
        raise ValueError('Preview requires local research artifacts')
    checks = [json.loads(line) for line in (source/'events.jsonl').read_text().splitlines()
              if json.loads(line).get('tool') == 'report_check']
    if not checks or checks[-1]['status'] != 'completed':
        raise ValueError('No source-validated draft; do not disguise a failed draft as a preview')
    draft = (source/f"draft-{checks[-1]['attempt']}.md").read_text()
    folder = ROOT/'outputs/delivery_preview'/uuid4().hex
    folder.mkdir(parents=True)
    assets = {}
    analysis = json.loads((source/'analysis.json').read_text())
    for record in analysis['charts']:
        chart = Chart.model_validate({k: record[k] for k in Chart.model_fields if k in record})
        if 'display_cells' in record:
            for row, cells in zip(chart.rows, record['display_cells']):
                row.cells = cells
        name = f'figures/{chart.id}.png'
        render_chart(chart, folder/name)
        assets[name] = folder/name
    notice = '**离线排版预览，非验收交付：正文来源链接已校验；逐项引文支持尚未完成核对，不代表端到端任务成功。研究建议尚未开展实验。**\n\n'
    profile = json.loads((source/'writing.json').read_text())['format_profile']
    paths = await publish(notice+draft, folder, profile=profile, assets=assets)
    (folder/'preview.json').write_text(json.dumps({'source': str(source), 'authenticated_end_to_end': False,
        'citation_review': 'pending', 'paths': paths}, ensure_ascii=False, indent=2))
    print(json.dumps(paths, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    asyncio.run(main(parser.parse_args().source))
