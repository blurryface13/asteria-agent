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


async def main(source):
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
    synthesis = next(d['summary'] for d in reversed(runtime.lead_decisions) if d['tool'] == 'finish')
    print('Replay output: '+str(runtime.folder), flush=True)
    report = await runtime.write_report(synthesis)
    citation = CitationAgent(runtime.llm, runtime.event, runtime.folder)
    report = await citation.attach_with_repair(report, evidence_catalog(runtime.evidence, runtime.read_sources()), runtime.read_sources())
    (runtime.folder/'report-with-citations.md').write_text(report)
    paths = await publish(report, runtime.folder, profile=runtime.format_profile)
    result = {'source_review':str(source),'mode':'report_stage_replay','paths':paths,
              'model_calls':runtime.model_calls,**report_length(report)}
    (runtime.folder/'replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.source))
