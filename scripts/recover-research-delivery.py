"""Explicit offline recovery from saved evidence; never changes the original Run.

No new research is performed. Lead decides whether existing material supports
delivery, then the normal Analyst/Writer/CitationAgent/publisher path executes.
This is not an authenticated end-to-end acceptance result.
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
    from asteria_researcher.agentic.latex import publish
    async def emit(kind, value):
        if kind == 'agent_action':
            print(json.dumps({k: value.get(k) for k in ['agent', 'tool', 'status', 'purpose']}, ensure_ascii=False), flush=True)
    source = source.resolve()
    if not source.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Recovery only accepts this repository’s saved research directories')
    read = lambda name: json.loads((source / name).read_text())
    runtime = AutonomousReview(configured_model(), None, emit, None, ROOT / 'outputs/delivery_recovery', online_rag=False)
    runtime.folder.mkdir(parents=True, exist_ok=True)
    runtime.query, runtime.plan = read('run.json')['task'], read('plan.json')
    runtime.user_scope = runtime.query
    runtime.evidence = read('evidence.json')
    runtime.lead_decisions = read('lead-decisions.json')
    runtime.briefs = []
    for artifact in sorted(source.glob('subagent-*.json')):
        data = json.loads(artifact.read_text())
        runtime.briefs.append({**data['result'], 'assignment': data['assignment'], 'artifact': artifact.name})
        (runtime.folder / artifact.name).write_text(artifact.read_text())
    for artifact in source.glob('paper-*.json'):
        data = json.loads(artifact.read_text())
        runtime.library.papers[data['requested_url']] = data
    runtime.library.nodes = {n['id']: n for n in read('citations.json')['nodes']}
    runtime.successful_searches = sum(json.loads(line).get('tool') == 'search' and json.loads(line).get('status') == 'completed'
                                      for line in (source / 'events.jsonl').read_text().splitlines())
    runtime.actions = runtime.max_actions  # Explicitly close research tools, not the final handoff.
    runtime.save_working_memory('delivery_recovery')
    (runtime.folder / 'plan.json').write_text(json.dumps(runtime.plan, ensure_ascii=False))
    state = {'source_review': str(source), 'mode': 'saved_evidence_delivery_recovery', 'authenticated_end_to_end': False}
    (runtime.folder / 'recovery.json').write_text(json.dumps(state, ensure_ascii=False))
    print('RECOVERY ' + str(runtime.folder), flush=True)
    try:
        result = await runtime.loop('lead', runtime.query, lead=True, steps=3)
        if result['status'] != 'completed':
            raise ValueError('Lead judged saved evidence insufficient: ' + result['summary'])
        report = await runtime.deliver(result['summary'])
        paths = await publish(report, runtime.folder, profile=runtime.format_profile, assets=runtime.figure_assets)
        state.update(status='completed', paths=paths, model_calls=runtime.model_calls)
        print(json.dumps(state, ensure_ascii=False), flush=True)
    except BaseException as error:
        state.update(status='failed', error_type=type(error).__name__, model_calls=runtime.model_calls)
        raise
    finally:
        (runtime.folder / 'recovery.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    asyncio.run(main(parser.parse_args().source))
