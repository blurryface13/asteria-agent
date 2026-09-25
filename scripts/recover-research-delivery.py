"""Explicit offline recovery from saved evidence; never changes the original Run.

Default recovery resumes the Lead handoff and delivery path. --resume-draft
on a failed source Run resumes only CitationAgent and publishing from its last
saved draft, accepted charts, and still-valid audited body lines. Neither path
counts as an authenticated end-to-end acceptance result.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def saved_citation_checkpoint(source: Path, destination: Path, read_sources: dict, domain: str) -> dict:
    """Copy an accepted draft and charts; never alter the failed source Run."""
    from asteria_researcher.agentic.citation_agent import factual_lines
    from asteria_researcher.agentic.illustrations import Chart, validate_chart
    from asteria_researcher.agentic.report_tools import validate_report_draft
    from asteria_researcher.agentic.sufficiency import evidence_catalog

    run = json.loads((source/'run.json').read_text())
    history = json.loads((source/'citation-history.json').read_text())
    audit = json.loads((source/'citation-review.json').read_text())
    if (run['status'] != 'failed' or not history or history[-1]['status'] != 'incomplete'
            or audit['status'] != 'incomplete'):
        raise ValueError('Only a failed CitationAgent checkpoint may resume from a source draft')
    attempt = len(history)
    draft_path = source/f'citation-draft-{attempt}.md'
    draft = draft_path.read_text()
    if not validate_report_draft(draft, read_sources, domain=domain)['ok']:
        raise ValueError('Saved citation draft does not pass the read-source contract')
    lines = draft.splitlines()
    body_ids = {line['line_id'] for line in factual_lines(draft)}
    catalog = evidence_catalog(json.loads((source/'evidence.json').read_text()), read_sources)
    manifest = json.loads((source/'analysis.json').read_text())
    assets, hashes = {}, {}
    for item in manifest['charts']:
        chart = Chart.model_validate({key: item[key] for key in Chart.model_fields})
        validate_chart(chart, catalog, domain=domain)
        name = item['path']
        if name != f'figures/{chart.id}.png' or not re.fullmatch(r'figures/[a-z][a-z0-9-]{0,40}\.png', name):
            raise ValueError('Saved chart path is not an accepted figure asset')
        original = source/name
        if original.is_symlink() or not original.is_file() or not original.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Saved figure is missing or is not a PNG: ' + name)
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        if name in assets:
            raise ValueError('Duplicate saved chart path')
        assets[name] = target
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    embedded = set(re.findall(r'!\[[^\]]*\]\((figures/[a-z][a-z0-9-]{0,40}\.png)\)', draft))
    if embedded != set(assets):
        raise ValueError('Saved draft and accepted figures have different image sets')
    gaps = {gap['line_id'] for gap in audit['gaps']}
    verified = {}
    for finding in audit['findings']:
        line_id = finding['line_id']
        if line_id in body_ids and line_id not in gaps and finding['supported']:
            verified[line_id] = (lines[line_id], finding)
    profile = json.loads((source/'writing.json').read_text())['format_profile']
    return {'draft': draft, 'manifest': manifest, 'assets': assets, 'verified': verified,
            'profile': profile, 'source_draft': draft_path.name, 'figure_sha256': hashes}


async def main(source, checkpoint=None, resume_draft=False, capability=None):
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
    source_run = read('run.json')
    recorded_capability = source_run.get('capability')
    if recorded_capability and capability and capability != recorded_capability:
        raise ValueError('Recovery capability differs from the saved source Run')
    capability = recorded_capability or capability or 'literature_review'
    runtime = AutonomousReview(configured_model(), None, emit, None, ROOT / 'outputs/delivery_recovery',
                               online_rag=False, capability=capability)
    runtime.folder.mkdir(parents=True, exist_ok=True)
    runtime.query, runtime.plan = source_run['task'], read('plan.json')
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
    state = {'source_review': str(source), 'mode': 'saved_evidence_delivery_recovery',
             'capability': capability,
             'authenticated_end_to_end': False, 'status': 'running', 'pid': os.getpid(), 'started_at': time.time()}
    (runtime.folder / 'recovery.json').write_text(json.dumps(state, ensure_ascii=False))
    print('RECOVERY ' + str(runtime.folder), flush=True)
    try:
        analysis_plan = None
        saved_draft = None
        saved_source_checkpoint = None
        if checkpoint:
            checkpoint = checkpoint.resolve()
            if not checkpoint.is_relative_to(ROOT/'outputs/delivery_recovery'):
                raise ValueError('Checkpoint must be a saved delivery recovery')
            prior = json.loads((checkpoint/'recovery.json').read_text())
            if prior['source_review'] != str(source) or prior.get('capability', 'literature_review') != capability:
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
        elif resume_draft:
            if source.parent != ROOT/'outputs' or not source.name.startswith('review_'):
                raise ValueError('Source-draft recovery requires an original saved review')
            saved_source_checkpoint = saved_citation_checkpoint(source, runtime.folder, runtime.read_sources(), capability)
            saved_draft = saved_source_checkpoint['draft']
            runtime.analysis_manifest = saved_source_checkpoint['manifest']
            runtime.figure_assets = saved_source_checkpoint['assets']
            runtime.format_profile = saved_source_checkpoint['profile']
            state.update(mode='saved_citation_checkpoint', resumed_from='citation_agent',
                         source_draft=saved_source_checkpoint['source_draft'],
                         reused_citation_lines=len(saved_source_checkpoint['verified']),
                         figure_sha256=saved_source_checkpoint['figure_sha256'])
        else:
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
        # Persist ancestry before any slow model call; abrupt process loss does
        # not run finally and must not erase the next recovery's provenance.
        state['phase'] = 'citation_agent' if saved_draft is not None else 'delivery'
        (runtime.folder / 'recovery.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
        if saved_source_checkpoint:
            report = await runtime.deliver('', saved_draft=saved_draft, saved_figures=True,
                                           citation_verified=saved_source_checkpoint['verified'])
        else:
            report = await runtime.deliver(await runtime.delivery_handoff(result),
                                           analysis_plan=analysis_plan, saved_draft=saved_draft)
        state['phase'] = 'publishing'
        (runtime.folder / 'recovery.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
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
    parser.add_argument('--resume-draft', action='store_true',
                        help='Resume saved draft at CitationAgent from this failed Run or a recovery checkpoint; no new research/Writer call')
    parser.add_argument('--capability', choices=['literature_review', 'experiment_design', 'financial_research'],
                        help='Required for legacy Run files without recorded capability when not literature_review')
    args = parser.parse_args()
    asyncio.run(main(args.source, args.checkpoint, args.resume_draft, args.capability))
