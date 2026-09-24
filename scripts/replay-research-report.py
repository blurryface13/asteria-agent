"""Replay writing/citation/publication from saved research, without repeating searches.

Uses configured paid model. Source Run/artifacts are never modified. This is an
offline report-stage verification, not a new authenticated end-to-end Run.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main(source, draft=None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    load_dotenv(ROOT / '.env.lab', override=True)
    from backend.server.agentic_runner import configured_model
    from asteria_researcher.agentic.autonomous import AutonomousReview
    from asteria_researcher.agentic.citation_agent import CitationAgent
    from asteria_researcher.agentic.sufficiency import evidence_catalog
    from asteria_researcher.agentic.latex import publish
    from asteria_researcher.agentic.report_tools import report_length

    async def emit(*args):
        pass
    source = source.resolve()
    if draft is not None and (Path(draft).name != draft or not (source / draft).is_file()
                              or (source / draft).suffix != '.md'
                              or not (source / draft).resolve().is_relative_to(source)):
        raise ValueError('Draft must name an existing Markdown file inside the source review')
    runtime = AutonomousReview(configured_model(), None, emit, None,
                               ROOT/'outputs'/'report_replay', online_rag=False)
    runtime.folder.mkdir(parents=True, exist_ok=True)
    read = lambda name: json.loads((source/name).read_text())
    runtime.query = read('run.json')['task']
    runtime.plan = read('plan.json')
    runtime.evidence = read('evidence.json')
    runtime.lead_decisions = read('lead-decisions.json')
    runtime.briefs = [json.loads(p.read_text())['result'] for p in sorted(source.glob('subagent-*.json'))]
    for paper in source.glob('paper-*.json'):
        data = json.loads(paper.read_text())
        runtime.library.papers[data['requested_url']] = data
    runtime.library.nodes = {node['id']:node for node in read('citations.json')['nodes']}
    if (source/'knowledge-sources.json').exists():
        runtime.knowledge_sources = read('knowledge-sources.json')
    if (source/'analysis.json').exists():
        runtime.analysis_manifest = read('analysis.json')
        import re
        for chart in runtime.analysis_manifest.get('charts', []):
            name = chart['path']
            if not re.fullmatch(r'figures/[a-z][a-z0-9-]{0,40}\.png', name):
                raise ValueError('Invalid source figure path')
            path = source / name
            if path.is_symlink() or not path.resolve().is_relative_to(source) or not path.is_file():
                raise ValueError('Source figure unavailable or outside review directory')
            runtime.figure_assets[name] = path
    synthesis = next(d['summary'] for d in reversed(runtime.lead_decisions) if d['tool'] == 'finish')
    print('Replay output: '+str(runtime.folder), flush=True)
    if draft is None:
        report = await runtime.write_report(synthesis)
    else:
        report = (source / draft).read_text()
        runtime.format_profile = read('writing.json')['format_profile']
    (runtime.folder / 'replay-input.json').write_text(json.dumps({
        'source_review': str(source), 'source_draft': draft,
        'mode': 'citation_stage_replay' if draft else 'report_stage_replay',
        'authenticated_end_to_end': False}, ensure_ascii=False, indent=2))
    citation = CitationAgent(runtime.llm, runtime.event, runtime.folder)
    report = await citation.attach_with_repair(report, evidence_catalog(runtime.evidence, runtime.read_sources()), runtime.read_sources())
    (runtime.folder/'report-with-citations.md').write_text(report)
    paths = await publish(report, runtime.folder, profile=runtime.format_profile, assets=runtime.figure_assets)
    result = {'source_review':str(source),'source_draft':draft,
              'mode':'citation_stage_replay' if draft else 'report_stage_replay','paths':paths,
              'model_calls':runtime.model_calls,**report_length(report)}
    (runtime.folder/'replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--draft', help='Replay only citation/publication from this saved Markdown filename')
    args = parser.parse_args()
    asyncio.run(main(args.source, args.draft))
