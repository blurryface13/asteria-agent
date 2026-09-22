"""Compare production control paths, not pretrained-model answer quality."""
import asyncio
import json
from pathlib import Path

import pytest

from asteria_researcher.agentic.research_comparison import (
    FrozenLibrary, PAPER, ScriptedModel, assess_path, run_arm)

ORIGINAL = (Path(__file__).parent/'fixtures/attention_demo.py').read_text()


def test_identical_fixture_and_patch_with_different_control_paths(tmp_path):
    async def exercise():
        results=[]
        for mode in ('direct','delegated'):
            results.append(await run_arm(mode,ScriptedModel(mode,ORIGINAL),tmp_path,ORIGINAL,model_mode='scripted'))
        direct, delegated=results
        assert direct['model_calls']==5
        assert delegated['model_calls']==7
        assert direct['source_sha256']==delegated['source_sha256']
        assert direct['evidence_sha256']==delegated['evidence_sha256']
        proposals=[]
        for r in results:
            assert r['status']=='completed' and r['observed_evidence'] and r['proposed_syntax_valid']
            assert r['path_contract']['passed']
            assert r['functional_tests_run'] is False and r['patch_applied'] is False
            assert not r['usage'] and r['semantic_quality']=='not_scored'
            t=next(t for t in r['result']['tool_results'] if t['tool']=='preview_code_diff')
            proposals.append(t['result']['proposed_sha256'])
            assert 'comparison.json' in {p.name for p in Path(r['runtime_folder']).iterdir()}
        assert proposals[0]==proposals[1]
        assert not direct['result']['research_requests']
        assert len(delegated['result']['research_requests'])==1
        assert [c['role'] for c in direct['calls']]==['coding']*5
        assert [c['role'] for c in delegated['calls']].count('research')==3
    asyncio.run(exercise())


@pytest.mark.parametrize('mode',['direct','delegated'])
def test_unavailable_evidence_stays_incomplete_no_fabricated_patch(tmp_path,mode):
    r=asyncio.run(run_arm(mode,ScriptedModel(mode,ORIGINAL),tmp_path,ORIGINAL,
                         model_mode='scripted',unavailable=True))
    assert r['status']=='incomplete'
    assert not r['observed_evidence'] and not r['diff_produced']
    assert not r['functional_tests_run']


def test_direct_arm_does_not_offer_handoff_and_rejects_attempt(tmp_path):
    steps=[]
    async def model(system,payload):
        data=json.loads(payload);steps.append(data)
        assert 'request_research' not in data['tools']
        if len(steps)==1:
            return json.dumps({'tool':'request_research','purpose':'forbidden','arguments':{}})
        assert 'permissions' in data['observations'][-1]['error']
        return json.dumps({'tool':'finish','purpose':'stop','outcome':'incomplete','summary':'当前组未授权委派'})
    r=asyncio.run(run_arm('direct',model,tmp_path,ORIGINAL,model_mode='scripted'))
    assert not r['result']['research_requests'] and r['status']=='incomplete'


def test_frozen_evidence_does_not_fetch_unknown_sources(tmp_path):
    lib=FrozenLibrary(tmp_path)
    with pytest.raises(ValueError):asyncio.run(lib.read('https://arxiv.org/abs/2001.00001'))
    with pytest.raises(ValueError):asyncio.run(lib.references(PAPER))


def test_live_provider_failure_is_blocked_not_scripted_fallback(tmp_path):
    class PaymentRequired(Exception): status_code=402
    async def failed(*args): raise PaymentRequired('secret provider payload')
    r=asyncio.run(run_arm('direct',failed,tmp_path,ORIGINAL,model_mode='live'))
    assert r['status']=='blocked' and r['failure']['reason']=='HTTP 402'
    assert r['model_calls']==1 and r['result'] is None
    assert 'secret' not in json.dumps(r)


def test_self_reported_completion_does_not_pass_without_observed_evidence():
    # Regression for real run bc6d245cda: repeated file reads and a plausible
    # patch did not establish either paper access or delegated research.
    result={'status':'completed','research_requests':[],
            'tool_results':[{'tool':'preview_code_diff','result':{'proposed_syntax':{'valid_syntax':True}}}]}
    checked=assess_path('delegated',result,[])
    assert checked['passed'] is False
    assert set(checked['failures'])=={'no_observed_passage','no_completed_research_handoff'}


def test_cancellation_propagates_to_waiting_model(tmp_path):
    async def exercise():
        started,cancelled=asyncio.Event(),asyncio.Event()
        async def waiting(*args):
            started.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        job=asyncio.create_task(run_arm('direct',waiting,tmp_path,ORIGINAL,model_mode='scripted'))
        await started.wait();job.cancel()
        with pytest.raises(asyncio.CancelledError):await job
        assert cancelled.is_set()
    asyncio.run(exercise())
