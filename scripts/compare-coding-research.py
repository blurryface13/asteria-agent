"""Run a paired direct-reading vs research-handoff proposal experiment.

--scripted: deterministic engineering replay, no quality claims.
--live: configured model + SAME frozen evidence; no network paper search,
        shell, generated-code execution or edits. May incur model charges.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


async def main(args):
    from asteria_researcher.agentic.research_comparison import run_arm, ScriptedModel
    original=(ROOT/'tests/fixtures/attention_demo.py').read_text()
    folder=ROOT/'outputs'/('coding-research-comparison-'+uuid4().hex[:10])
    folder.mkdir(parents=True)
    if args.live:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env');load_dotenv(ROOT/'.env.lab',override=True)
        # This experiment stops on provider failure instead of paying for retries.
        import os
        os.environ['ASTERIA_LLM_MAX_ATTEMPTS']='1'
        from backend.server.agentic_runner import configured_model
        live_model=configured_model()
    mode='live' if args.live else 'scripted'
    arms=args.order.split(',')
    report={'mode':mode,'scope':'single local-formula proposal task; not executed debugging or quality benchmark',
            'arms':[],'status':'finished','equivalent_inputs':True}
    for arm in arms:
        result=await run_arm(arm,live_model if args.live else ScriptedModel(arm,original),
                             folder,original,model_mode=mode,unavailable=args.evidence_unavailable)
        report['arms'].append(result)
        if result['status']=='blocked':
            report['status']='blocked';break
    # Finishing an experiment is not equivalent to passing its path contract.
    report['path_contract_passed'] = (len(report['arms']) == 2 and
        all(r['path_contract']['passed'] for r in report['arms']))
    path=folder/'summary.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'report':str(path),'mode':mode,'status':report['status'],
        'path_contract_passed':report['path_contract_passed'],
        'arms':[{k:r[k] for k in ('arm','status','path_contract','model_calls','input_chars','wall_ms',
            'handoff_wait_ms','observed_evidence','diff_produced','failure')} for r in report['arms']]},ensure_ascii=False))
    return 1 if report['status']=='blocked' else (0 if report['path_contract_passed'] else 2)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--scripted',action='store_true')
    modes.add_argument('--live',action='store_true')
    parser.add_argument('--order',choices=('direct,delegated','delegated,direct'),default='direct,delegated')
    parser.add_argument('--evidence-unavailable',action='store_true')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
