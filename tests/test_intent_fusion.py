import asyncio
import json

import pytest

from asteria_researcher.agentic.intent import analyze_intent
from asteria_researcher.agentic.intent_fusion import IntentFusion, TEMPLATES, local_features, pattern_vote


def payload(message="你好", **kwargs):
    return {"message":message,"history":[],"report":"","knowledge_catalog":[],**kwargs}


def decision(capability="general_chat", confidence=.9, **kwargs):
    return {"capability":capability,"confidence":confidence,"reason":"语义判断",**kwargs}


def test_three_branches_are_parallel_and_template_vectors_reused():
    async def exercise():
        fusion = IntentFusion()
        llm_started, embed_started = asyncio.Event(), asyncio.Event()
        calls = []
        async def semantic():
            llm_started.set()
            await asyncio.wait_for(embed_started.wait(), 1)
            return decision()
        async def embed(texts):
            embed_started.set()
            await asyncio.wait_for(llm_started.wait(), 1)
            calls.append(texts)
            return [local_features(t) for t in texts]  # Test double, not a neural model.
        for scope in ('user1:conversation','user2:conversation'):
            result = await fusion.recognize(payload(),semantic,available=TEMPLATES,embed=embed,identity='test',cache_scope=scope)
            assert result['routing_trace']['source_votes']['embedding']['mode']=='semantic_embedding'
            assert not result['needs_clarification']
        assert len([c for c in calls if len(c)>1])==1 and len(calls)==3
    asyncio.run(exercise())


def test_lru_moves_hits_and_ttl_expires():
    now = [0.]
    cache = IntentFusion(capacity=2,ttl=10,clock=lambda:now[0])
    cache.cache_put('a', {'x':1}); cache.cache_put('b', {'x':2})
    hit = cache.cache_get('a'); hit['x']=99
    cache.cache_put('c',{'x':3})
    assert cache.cache_get('b') is None and cache.cache_get('a')['x']==1
    now[0]=10.
    assert cache.cache_get('a') is None


def test_concurrent_users_encode_static_templates_once():
    async def exercise():
        f=IntentFusion()
        encoded=[]
        async def embed(texts):
            encoded.append(texts)
            await asyncio.sleep(.001)
            return [local_features(t) for t in texts]
        async def semantic():return decision()
        results=await asyncio.gather(*(f.recognize(payload(),semantic,available=TEMPLATES,embed=embed,
                    identity='shared-config',cache_scope=f'user-{i}') for i in range(10)))
        assert len([t for t in encoded if len(t)>1])==1
        assert len(encoded)==11 and all(not r['routing_trace']['cache_hit'] for r in results)
    asyncio.run(exercise())


def test_cache_uses_whole_message_history_report_scope_and_catalog():
    async def exercise():
        cache = IntentFusion()
        calls = []
        async def semantic():
            calls.append(1)
            return decision()
        async def run(p=None,scope='user:c',identity='model-v1'):
            return await cache.recognize(p or payload(),semantic,available=TEMPLATES,identity=identity,cache_scope=scope)
        first = await run()
        hit = await run()
        assert not first['routing_trace']['cache_hit'] and hit['routing_trace']['cache_hit']
        hit['routing_trace']['scores'].clear()
        assert (await run())['routing_trace']['scores']
        await run(scope='other:c'); await run(scope='user:other'); await run(identity='model-v2')
        await run(payload(history=[{'role':'assistant','content':'context'}]))
        await run(payload(report='new report'))
        await run(payload(knowledge_catalog=[{'id':'kb','revision':1}]))
        await run(payload(knowledge_catalog=[{'id':'kb','revision':2}]))
        await run(payload('x'*250+'first')); await run(payload('x'*250+'different'))
        assert len(calls)==10  # The hit did not call the LLM, every context change did.
        assert all('user' not in key for key in cache.cache)
    asyncio.run(exercise())


def test_llm_failure_propagates_and_cancels_embedding_no_rule_fallback():
    async def exercise():
        started,cancelled=asyncio.Event(),asyncio.Event()
        async def embed(texts):
            started.set()
            try: await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set(); raise
        async def semantic():
            await started.wait()
            raise RuntimeError('provider failed')
        f=IntentFusion()
        with pytest.raises(RuntimeError):
            await f.recognize(payload('读取文件readme.md'),semantic,available=TEMPLATES,embed=embed,identity='m',cache_scope='owner')
        assert cancelled.is_set() and not f.cache
    asyncio.run(exercise())


@pytest.mark.parametrize('vectors', [[], [[float('nan')]], [[1.,2.]]])
def test_broken_vectors_are_explicit_lexical_degradation_and_not_cached(vectors):
    async def exercise():
        f=IntentFusion()
        async def semantic():return decision()
        async def embed(texts):return vectors
        result=await f.recognize(payload(),semantic,available=TEMPLATES,embed=embed,identity='m',cache_scope='owner')
        trace=result['routing_trace']
        assert trace['source_votes']['embedding']['mode']=='local_ngram'
        assert trace['weights']['embedding']==.05 and not f.cache
    asyncio.run(exercise())


def test_low_confidence_or_disagreement_asks_before_tool_routing():
    async def exercise():
        f=IntentFusion()
        async def semantic():return decision(confidence=.1)
        async def embed(texts):
            return [[1.,0.] if '读取attention.py' in t or t=='读取文件bug.py' else [0.,1.] for t in texts]
        result=await f.recognize(payload('读取文件bug.py'),semantic,available=TEMPLATES,embed=embed,identity='test')
        assert result['needs_clarification'] and result['clarification_question']
        assert result['routing_trace']['winning_score'] < .5
    asyncio.run(exercise())


@pytest.mark.parametrize('message, expected', [
    ('请对比扩散模型水印论文并核对GitHub实现，生成综述报告','literature_review'),
    ('请检查attention.py，不要生成调研报告','workspace_coding'),
    ('解释报告中的实验设计，不需要新调研','general_chat'),
    ('给我规划机器学习学习路径','learning_guidance'),
    ('查询今年会议投稿日期','submission_consulting'),
    ('市盈率是什么意思，不用联网','financial_research'),
    ('核查公司主体，整理企业公开资料','company_research'),
])
def test_semantic_deliverable_wins_over_incidental_keywords(message, expected):
    async def model(system, raw):
        assert 'Few-shot examples:' in system
        assert json.loads(raw)['message']==message
        return json.dumps(decision(expected,.95))
    result=asyncio.run(analyze_intent(message,model))
    assert result.capability==expected and not result.needs_clarification


def test_knowledge_permission_cannot_be_invented_by_model():
    async def model(*a):return json.dumps(decision('knowledge_chat',knowledge_ids=['private-other']))
    with pytest.raises(ValueError):
        asyncio.run(analyze_intent('知识库问题',model,knowledge_catalog=[{'id':'allowed'}]))
    with pytest.raises(ValueError):asyncio.run(analyze_intent('知识库问题',model))


def test_pattern_ties_do_not_turn_compound_tasks_into_first_match():
    result=pattern_vote('请调查论文调研和企业背调',TEMPLATES)
    assert result['capability'] is None and len(result['ambiguous'])==2


def test_memory_file_edit_invalidates_router_cache(monkeypatch):
    from asteria_researcher.agentic import intent
    from asteria_researcher.utils.memory_context import memory_context
    monkeypatch.setattr(intent,'FUSION',IntentFusion())
    calls=[]
    async def model(*a):
        calls.append(1)
        return json.dumps(decision())
    model.routing_identity='same-model'
    async def exercise():
        token=memory_context.set({'files':[{'name':'PROFILE.md','version':'v1','content':'研究方向一'}]})
        try:
            await intent.analyze_intent('你好',model,cache_scope='owner:c')
            hit=await intent.analyze_intent('你好',model,cache_scope='owner:c')
            assert hit.routing_trace['cache_hit']
            memory_context.set({'files':[{'name':'PROFILE.md','version':'v2','content':'研究方向二'}]})
            changed=await intent.analyze_intent('你好',model,cache_scope='owner:c')
            assert not changed.routing_trace['cache_hit'] and len(calls)==2
        finally:memory_context.reset(token)
    asyncio.run(exercise())


@pytest.mark.parametrize('capability', ['workspace_coding','knowledge_chat','learning_guidance',
                                     'submission_consulting','financial_research','company_research','general_chat'])
@pytest.mark.parametrize('supplied', [True, False])
def test_legacy_research_entry_rejects_non_research_routes(monkeypatch, capability, supplied):
    from asteria_researcher.agentic import intent
    from backend.server import agentic_runner, websocket_manager

    class Sink:
        feedback_queue = object()
        async def send_json(self, event): pass

    async def classify(*args, **kwargs):
        return intent.Intent(capability=capability,reason='ordinary task')

    async def forbidden(*args, **kwargs):
        pytest.fail('A specialist or clarification must not start a research loop')

    monkeypatch.setattr(intent,'analyze_intent',classify)
    monkeypatch.setattr(agentic_runner,'configured_model',lambda *args: None)
    monkeypatch.setattr(agentic_runner,'run_agentic_task',forbidden)
    with pytest.raises(ValueError,match='Coordinator'):
        asyncio.run(websocket_manager.run_agent('check a file','research_report','web',[],[],
                    'Objective',None,logs_handler=Sink(),coordinator_capability=capability if supplied else None))
