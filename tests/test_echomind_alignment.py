"""Architecture contracts, not live-model accuracy measurements."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from asteria_researcher.agentic.base_agent import AgentProfile, BaseAgent, AgentFinish
from asteria_researcher.agentic.agent_orchestrator import AgentOrchestrator, Request
from asteria_researcher.agentic.intent import Intent


def test_shared_loop_enforces_whitelist_schema_and_final_turn():
    async def run():
        calls, errors, advertised = [], [], []
        answers = ['bad json', '{"tool":"shell"}', '{"tool":"read"}', '{"tool":"read"}']
        async def decide(turn, allowed):
            advertised.append(allowed)
            return answers[turn]
        async def execute(action, turn): calls.append(action.tool)
        async def observe(message, error): errors.append(message)
        profile = AgentProfile('reader','read','','',('read','finish'),4)
        result = await BaseAgent(profile).run(decide=decide,
            parse=lambda raw:SimpleNamespace(**json.loads(raw)),execute=execute,observe_error=observe)
        assert result is None and calls == ['read'] and len(errors) == 3
        assert advertised[-1] == {'finish'}
    asyncio.run(run())


def test_shared_loop_provider_failure_and_cancellation_propagate():
    async def run():
        profile = AgentProfile('reader','read','','',('finish',))
        async def forbidden(*args): pytest.fail('must not execute or turn provider failure into observation')
        for error in (RuntimeError('provider unavailable'), asyncio.CancelledError()):
            async def decide(*args): raise error
            with pytest.raises(type(error)):
                await BaseAgent(profile).run(decide=decide,parse=json.loads,execute=forbidden,observe_error=forbidden)
    asyncio.run(run())


def request(capability, **kw):
    return Request('用户的完整请求','owner','conversation','request-1',
                   intent=Intent(capability=capability,reason='test',**kw))


def test_entry_skips_reclassification_and_never_routes_clarification():
    async def run():
        seen = []
        async def forbidden(*args, **kwargs): pytest.fail('must not reclassify')
        async def research(req, intent):
            seen.append(intent.capability)
            return {'run_id':'durable-run'}
        entry = AgentOrchestrator(forbidden, {'research_lead':research},recognize=forbidden)
        result = await entry.run(request('literature_review'))
        assert result['run_id'] == 'durable-run'
        assert result['routing_decision']['primary_agent'] == 'research_lead'
        result = await entry.run(request('literature_review',needs_clarification=True,clarification_question='请确认交付物'))
        assert seen == ['literature_review'] and 'run_id' not in result
        assert result['response']['metadata']['needs_clarification']
    asyncio.run(run())


def test_entry_passes_authenticated_context_to_fused_recognizer():
    async def run():
        async def recognize(message, model, **kw):
            assert kw['cache_scope'] == {'email':'owner','conversation_id':'c'}
            assert kw['history'] == [{'role':'assistant','content':'previous'}]
            assert kw['knowledge_catalog'][0]['id'] == 'authorized-kb'
            return Intent(capability='general_chat',reason='followup')
        async def answer(*args): return {'response':{'content':'answer'}}
        result = await AgentOrchestrator(None,{'general_chat':answer},recognize=recognize).run(
            Request('followup','owner','c','r',history=[{'role':'assistant','content':'previous'}],
                    knowledge_catalog=[{'id':'authorized-kb'}]))
        assert result['capability'] == 'general_chat'
    asyncio.run(run())


@pytest.mark.parametrize('capability,support',[
    ('workspace_coding',['company_research']),('literature_review',['learning_guidance']),
    ('company_research',['company_research'])])
def test_entry_rejects_write_fanout_and_duplicate_primary(capability,support):
    async def run():
        async def forbidden(*args): pytest.fail('must validate before starting an effect')
        with pytest.raises(ValueError,match='Parallel routing'):
            await AgentOrchestrator(forbidden,{}).run(request(capability,supporting_agents=support))
    asyncio.run(run())


def test_domain_parallel_runs_concurrently_and_retains_failures():
    async def run():
        started, active, peak = [], 0, 0
        def role(name):
            async def execute(req, intent):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                started.append((name,req.message))
                await asyncio.sleep(.01)
                active -= 1
                if name == 'financial_research': raise RuntimeError('private-provider-detail')
                return {'response':{'content':'已有资料，不代表投资建议','metadata':{}}}
            return execute
        async def compose(system, payload):
            assert 'private-provider-detail' not in payload
            assert json.loads(payload)['roles'][1]['success'] is False
            return '公司资料已整理，财务核查未完成。'
        result = await AgentOrchestrator(compose,{k:role(k) for k in ('company_research','financial_research')}).run(
            request('company_research',supporting_agents=['financial_research']))
        assert peak == 2 and len(started) == 2
        assert result['response']['metadata']['status'] == 'partial'
        assert 'financial_research' in result['response']['content']
    asyncio.run(run())


def test_parallel_cancellation_stops_all_roles():
    async def run():
        started, stopped = set(), set()
        gate = asyncio.Event()
        def handler(name):
            async def execute(*args):
                started.add(name)
                if len(started) == 2: gate.set()
                try: await asyncio.Event().wait()
                finally: stopped.add(name)
            return execute
        entry = AgentOrchestrator(None,{k:handler(k) for k in ('company_research','financial_research')})
        task = asyncio.create_task(entry.run(request('company_research',supporting_agents=['financial_research'])))
        await asyncio.wait_for(gate.wait(),1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert stopped == started
    asyncio.run(run())


def test_parallel_role_contexts_are_isolated():
    async def run():
        barrier = asyncio.Event()
        async def primary(req,intent):
            req.history.append({'role':'assistant','content':'primary-private-observation'})
            intent.knowledge_ids.append('not-for-sibling')
            barrier.set()
            return {'response':{'content':'primary'}}
        async def secondary(req,intent):
            await barrier.wait()
            assert not req.history and not intent.knowledge_ids
            assert req.role_context['assigned_role']=='financial_research'
            assert req.role_context['composition_owner']=='AgentOrchestrator'
            return {'response':{'content':'secondary'}}
        async def compose(*args): return 'combined'
        req = request('company_research',supporting_agents=['financial_research'])
        await AgentOrchestrator(compose,{'company_research':primary,'financial_research':secondary}).run(req)
        assert not req.history and not req.intent.knowledge_ids
    asyncio.run(run())


def test_role_clarifications_are_not_reported_as_completed():
    async def run():
        async def clarify(*args):
            return {'response':{'content':'请补充测试材料','metadata':{'status':'clarify'}}}
        async def compose(*args): return '请补充材料后再分析。'
        result = await AgentOrchestrator(compose,{k:clarify for k in ('company_research','financial_research')}).run(
            request('company_research',supporting_agents=['financial_research']))
        assert result['response']['metadata']['status']=='needs_clarification'
        assert result['response']['metadata']['needs_clarification']
    asyncio.run(run())


def test_failed_primary_never_composes_success():
    async def run():
        async def fail(*args): raise ValueError('failed')
        async def support(*args): return {'response':{'content':'support'}}
        async def forbidden(*args): pytest.fail('primary failure must not be synthesized away')
        with pytest.raises(ValueError,match='Primary agent failed'):
            await AgentOrchestrator(forbidden,{'company_research':fail,'financial_research':support}).run(
                request('company_research',supporting_agents=['financial_research']))
    asyncio.run(run())


def test_general_chat_uses_shared_loop_and_keeps_report_context():
    from backend.server.specialists import run_general
    async def model(system, payload):
        data = json.loads(payload)
        assert data['context']['report'] == '事实 https://example.org/paper'
        return json.dumps({'action':'answer','content':'已有报告的依据：https://example.org/paper'})
    text, meta = asyncio.run(run_general('解释','',model,'事实 https://example.org/paper'))
    assert 'example.org' in text and meta['agent'] == 'general_chat' and not meta['tool_calls']


def test_lead_checkpoints_on_finish_not_every_three_actions_and_resumes(tmp_path):
    from asteria_researcher.agentic.autonomous import AutonomousReview
    reviewed, actions, events = [], [], []
    sequence = ['search','search','search','finish','search','finish']
    async def model(system, raw):
        data = json.loads(raw)
        turn = len(actions)
        tool = sequence[turn]
        actions.append(tool)
        if turn == 3: assert not reviewed  # Already >=3 actions, but no periodic reviewer.
        if turn == 4: assert '补充' in str(data['observations'])
        return json.dumps({'tool':tool,'query':str(turn),'purpose':'继续研究','summary':'准备交付'})
    async def emit(kind, event): events.append(event)
    async def noop(*args): pass
    r = AutonomousReview(model,None,emit,noop,tmp_path,online_rag=False)
    r.query = '比较研究方法'
    r.plan = {'required_goals':[{'id':'g1','description':'方法对比'}]}
    r.evidence = [{'agent':'lead','query':'existing','passages':[]}]
    async def search(*args,**kw): return []
    r.library.search = search
    async def assess():
        reviewed.append(list(actions))
        record = {'ready':len(reviewed)==2,'goals':[], 'synthesis':'支持的结论'}
        r.assessments.append(record)
        return record
    async def implementation(): return []
    r.assess_sufficiency, r.review_implementation = assess, implementation
    r.assessment_gaps = lambda assessment:['补充方法对比依据']
    result = asyncio.run(r.loop('lead',r.query,lead=True,steps=6))
    assert result['status'] == 'completed'
    assert [len(a) for a in reviewed] == [4,6]
    assert len([e for e in events if e['agent']=='lead' and e['tool']=='checkpoint' and e['status']=='started']) == 2


def test_experiment_design_enters_shared_research_runtime(monkeypatch):
    from backend.server import agentic_runner
    async def run(query,sink,kwargs,*,capability):
        assert capability == 'experiment_design'
        return 'protocol'
    monkeypatch.setattr(agentic_runner,'run_autonomous_review',run)
    assert asyncio.run(agentic_runner.run_agentic_task('实验计划','experiment_design',None,{})) == 'protocol'


def test_experiment_profile_loads_experiment_skill(tmp_path):
    from asteria_researcher.agentic.autonomous import AutonomousReview
    r = AutonomousReview(None,None,None,None,tmp_path,online_rag=False,capability='experiment_design')
    assert list(r.research_skills.loaded) == ['experiment_research']


def test_public_research_preserves_domain_filter(monkeypatch):
    from backend.server import agentic_runner, specialists
    from asteria_researcher.agentic import latex
    async def search(query):
        assert 'site:example.org' in query
        return [{'url':'https://example.org/a'}, {'url':'https://sub.example.org/b'},
                {'url':'https://example.org.evil.invalid/c'}]
    async def specialist(*args, public_search, **kwargs):
        rows = await public_search('research question')
        assert len(rows)==2 and all('evil' not in r['url'] for r in rows)
        return 'A cited report', {'sources':rows,'status':'answer'}
    async def publish(*args,**kw): return {'md':'fixture-only'}
    async def emit(*args): pass
    monkeypatch.setattr(specialists,'search_public_sources',search)
    monkeypatch.setattr(specialists,'run_specialist',specialist)
    monkeypatch.setattr(agentic_runner,'configured_model',lambda *args:None)
    monkeypatch.setattr(latex,'publish',publish)
    sink=SimpleNamespace(send_json=emit)
    result=asyncio.run(agentic_runner.run_agentic_task('question','general_research',sink,
        {'report_source':'web','query_domains':['example.org']}))
    assert result=='A cited report'


@pytest.mark.parametrize('options',[{'report_source':'local'}, {'document_urls':['a.pdf']},
                                   {'source_urls':['https://example.org']}])
def test_public_research_never_silently_discards_unsupported_source_scope(options):
    from backend.server.agentic_runner import run_agentic_task
    with pytest.raises(ValueError,match='公开资料角色'):
        asyncio.run(run_agentic_task('question','general_research',None,options))


def test_canonical_and_legacy_routes_share_handlers():
    from backend.server.orchestrator import router
    from backend.server.coordinator import router as legacy
    assert {r.path for r in router.routes} == {'/api/orchestrator/route','/api/orchestrator/turn','/api/orchestrator/capabilities'}
    assert [r.endpoint for r in router.routes] == [r.endpoint for r in legacy.routes]
