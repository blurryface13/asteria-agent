"""Retry only PDF publication of a completed citation review, without LLM calls.

Records a separate publication result; never changes the failed research Run.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main(folder, profile='academic'):
    from asteria_researcher.agentic.latex import publish
    folder = folder.resolve()
    if not folder.is_relative_to(ROOT/'outputs'):
        raise ValueError('Only saved project outputs may be republished')
    review = json.loads((folder/'citation-review.json').read_text())
    if review['status'] != 'completed' or review.get('gaps'):
        raise ValueError('Publication requires a completed citation review')
    report = (folder/'report-with-citations.md').read_text()
    manifest = json.loads((folder/'analysis.json').read_text()) if (folder/'analysis.json').is_file() else {'charts': []}
    assets = {chart['path']: folder/chart['path'] for chart in manifest['charts']}
    record = {'mode': 'publication_only_recovery', 'source_review': str(folder),
              'authenticated_end_to_end': False, 'model_calls': 0, 'status': 'publishing'}
    state_path = folder/f'publication-recovery-{uuid4().hex}.json'
    state_path.write_text(json.dumps(record, indent=2))
    try:
        paths = await publish(report, folder, profile=profile, assets=assets)
        record.update(status='completed', paths=paths)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    except BaseException as error:
        record.update(status='failed', error_type=type(error).__name__)
        raise
    finally:
        state_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--profile', default='academic')
    args = parser.parse_args()
    asyncio.run(main(args.folder, args.profile))
