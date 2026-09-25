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


async def main(source, checkpoint=None, resume_draft=False):
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
        analysis_plan = None
        saved_draft = None
        if checkpoint:
            checkpoint = checkpoint.resolve()
            if not checkpoint.is_relative_to(ROOT/'outputs/delivery_recovery'):
                raise ValueError('Checkpoint must be a saved delivery recovery')
            prior = json.loads((checkpoint/'recovery.json').read_text())
            if prior['source_review'] != str(source):
                raise ValueError('Checkpoint belongs to different source research')
            events = [json.loads(line) for line in (checkpoint/'events.jsonl').read_text().splitlines()]
            handoff_events = events
            ancestor, visited = checkpoint, set()
            while not any(e['agent']=='lead' and e['tool']=='finish' and e['status']=='completed' for e in handoff_events):
                if str(ancestor) in visited:
                    raise ValueError('Cyclic recovery checkpoint')
                visited.add(str(ancestor))
                record = json.loads((ancestor/'recovery.json').read_text())
                ancestor = Path(record['checkpoint']).resolve()
                if not ancestor.is_relative_to(ROOT/'outputs/delivery_recovery'):
                    raise ValueError('Invalid ancestor checkpoint')
                if json.loads((ancestor/'recovery.json').read_text())['source_review'] != str(source):
                    raise ValueError('Ancestor belongs to another research task')
                handoff_events = [json.loads(line) for line in (ancestor/'events.jsonl').read_text().splitlines()]
            result = next(e['result'] for e in reversed(handoff_events)
                          if e['agent']=='lead' and e['tool']=='finish' and e['status']=='completed')
            plans = sorted(checkpoint.glob('analysis-attempt-*.txt'))
            analysis_plan = plans[-1] if plans else None
            if (checkpoint/'analysis.json').is_file():
                # Resume the accepted charts, not an earlier attempt containing
                # an explicitly rejected optional figure. Revalidate/render
                # them normally; no saved asset is silently trusted.
                from asteria_researcher.agentic.illustrations import Analysis, Chart
                manifest = json.loads((checkpoint/'analysis.json').read_text())
                accepted = Analysis.model_validate({
                    **{key: manifest[key] for key in Analysis.model_fields if key != 'charts'},
                    'charts': [{key: chart[key] for key in Chart.model_fields} for chart in manifest['charts']]})
                analysis_plan = runtime.folder/'accepted-analysis-plan.json'
                analysis_plan.write_text(accepted.model_dump_json())
            state['checkpoint'] = str(checkpoint)
            if resume_draft:
                checks = [e for e in events if e['tool']=='report_check']
                citation_drafts = sorted(checkpoint.glob('citation-draft-*.md'))
                if citation_drafts:
                    saved_draft = citation_drafts[-1].read_text()
                elif checks and checks[-1]['status'] == 'completed':
                    saved_draft = (checkpoint/f"draft-{checks[-1]['attempt']}.md").read_text()
                else:
                    raise ValueError('Checkpoint has no validated report draft')
                profile_source, seen = checkpoint, set()
                while not (profile_source/'writing.json').is_file():
                    if str(profile_source) in seen:
                        raise ValueError('Cyclic writing profile checkpoint')
                    seen.add(str(profile_source))
                    record = json.loads((profile_source/'recovery.json').read_text())
                    profile_source = Path(record['checkpoint']).resolve()
                    if not profile_source.is_relative_to(ROOT/'outputs/delivery_recovery'):
                        raise ValueError('Invalid writing profile checkpoint')
                    if json.loads((profile_source/'recovery.json').read_text())['source_review'] != str(source):
                        raise ValueError('Writing profile belongs to a different research task')
                runtime.format_profile = json.loads((profile_source/'writing.json').read_text())['format_profile']
                state['resumed_from'] = 'citation_agent'
        else:
            if resume_draft:
                raise ValueError('--resume-draft requires --checkpoint')
            events = [json.loads(line) for line in (source/'events.jsonl').read_text().splitlines()]
            finished = [e['result'] for e in events if e.get('agent')=='lead' and e.get('tool')=='finish'
                        and e.get('status')=='completed' and 'result' in e]
            if finished:
                result = finished[-1]
                state['resumed_from'] = 'completed_lead_handoff'
                await runtime.event('lead', 'finish', 'completed', '恢复已保存的 Lead 交接，不重复调研', result=result)
                plans = sorted(source.glob('analysis-attempt-*.txt'))
                analysis_plan = plans[-1] if plans else None
            else:
                result = await runtime.loop('lead', runtime.query, lead=True, steps=3)
        report = await runtime.deliver(await runtime.delivery_handoff(result), analysis_plan=analysis_plan, saved_draft=saved_draft)
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
    parser.add_argument('--checkpoint', type=Path, help='Reuse completed Lead handoff and revalidate saved figure plan')
    parser.add_argument('--resume-draft', action='store_true', help='Resume validated checkpoint draft at CitationAgent; no new Writer call')
    args = parser.parse_args()
    asyncio.run(main(args.source, args.checkpoint, args.resume_draft))
