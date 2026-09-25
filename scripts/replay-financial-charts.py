"""Replay only Data Analyst against a saved financial research run.

This intentionally calls the configured paid model, but does not rerun search,
download, Lead, Writer or CitationAgent. Artifacts go to a new output folder.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv


async def run(review_dir: Path, cached_plan: Path | None):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'backend'))
    from asteria_researcher.agentic.citation_agent import visible_evidence
    from asteria_researcher.agentic.illustrations import analyze
    from asteria_researcher.agentic.sufficiency import evidence_catalog
    from asteria_researcher.utils.usage_context import track_usage_stage
    from backend.auth.schema_bootstrap import initialize_database
    from backend.server.agentic_runner import configured_model

    await initialize_database()
    evidence = json.loads((review_dir / 'evidence.json').read_text())
    sources = {item['url']: item for path in review_dir.glob('paper-*.json')
               if (item := json.loads(path.read_text())).get('url')}
    catalog = visible_evidence(evidence_catalog(evidence, sources))
    plan = json.loads((review_dir / 'plan.json').read_text())
    previous = json.loads((review_dir / 'analysis.json').read_text())
    destination = root / 'outputs' / ('financial-chart-replay-' + uuid4().hex)
    destination.mkdir(parents=True)

    async def emit(*_args, **_kwargs):
        return None

    configured = configured_model(os.getenv('CONFIG_PATH'))

    async def model(system, payload):
        return await configured(system, json.dumps(payload, ensure_ascii=False))

    with track_usage_stage('data_analyst'):
        _, manifest = await analyze(model, emit, destination, plan['scope'],
                                    previous['rationale'], [], catalog,
                                    cached_plan=cached_plan,
                                    domain='financial_research')
    print('REPLAY', destination, 'charts:', [chart['id'] for chart in manifest['charts']],
          'limitations:', manifest['limitations'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('review_dir', type=Path)
    parser.add_argument('--cached-plan', type=Path,
                        help='Replay saved analyst JSON without another model call')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    load_dotenv(root / '.env')
    load_dotenv(root / '.env.lab', override=True)
    asyncio.run(run(args.review_dir, args.cached_plan))
