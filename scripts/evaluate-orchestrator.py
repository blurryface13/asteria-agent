"""Bounded live-model probes for the EchoMind-aligned entry and shared loops.

No production user data, external search, file edits, generated-code execution or
durable research runs. Synthetic domain material is explicitly labelled. These
are engineering acceptance examples, not a model-quality benchmark.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


async def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    load_dotenv(ROOT/'.env.lab',override=True)
    os.environ['ASTERIA_LLM_MAX_ATTEMPTS'] = '1'
    from backend.server.agentic_runner import configured_model
    from backend.server.orchestrator_handlers import executors
    from asteria_researcher.agentic.agent_orchestrator import AgentOrchestrator, Request
    from asteria_researcher.agentic.intent import Intent
    from asteria_researcher.utils.usage_context import usage_sink
    actual = configured_model()
    folder = ROOT/'outputs'/('orchestrator-eval-'+uuid4().hex[:10])
    folder.mkdir(parents=True)
    calls, usage, search_calls, turns = [], [], [], []
    async def model(system, payload):
        if len(calls) >= 20:
            raise RuntimeError('Live acceptance model budget exhausted (20 calls)')
        start = time.monotonic()
        record = {'index':len(calls)+1,'status':'started'}
        calls.append(record)
        try:
            answer = await actual(system,payload)
            record.update(status='completed',latency_ms=round((time.monotonic()-start)*1000))
            return answer
        except Exception as exc:
            record.update(status='failed',error=type(exc).__name__)
            raise
    model.intent_embeddings = actual.intent_embeddings
    model.routing_identity = actual.routing_identity
    async def capture(event):
        usage.append({k:event.get(k) for k in ('model','provider','stage','usage','available','latency_ms')})
    async def frozen_search(query):
        search_calls.append(query)
        await asyncio.sleep(.02)
        return [{'title':'虚构企业测试夹具，不是真实公司财务数据','url':'https://example.org/fixture',
                 'content':'测试材料：星河样例公司主营传感器，收入100，经营现金流60，应收账款由20增至40；币种省略。不得当成真实投资资料。'}]
    handlers = executors(model)
    async def dry_research(req,intent):
        return {'dry_run':True,'requested_capability':intent.capability}
    handlers['research_lead'] = dry_research
    handlers['general_research'] = dry_research
    entry = AgentOrchestrator(model,handlers)
    scenarios = [
        ('general', '解释并发和并行的区别，用两句话回答，不检索资料。', None, 'general_chat'),
        ('research_route_only', '对比扩散模型图像水印的方法原理和编辑攻击鲁棒性，写一份带论文依据的综述；需要时让两路调研分别负责方法与评估。', None, 'literature_review'),
        ('compound_route', '请让企业背调助手核查星河样例公司的业务信息，并请财务研究助手辅助分析其经营现金流与应收账款风险，最后合并两个角色的回答。仅使用测试材料，不生成独立研究报告。', None, 'company_research'),
        ('domain_parallel', '请结合提供的虚构星河样例公司资料，从公司业务与财务风险两个角度分别核查并综合说明。需要检索测试材料，不要生成独立报告文件，也不要给投资建议。',
         Intent(capability='company_research',reason='已识别为只读公司与财务复合核查',supporting_agents=['financial_research']), 'company_research'),
    ]
    token = usage_sink.set(capture)
    try:
        with patch('backend.server.specialists.search_public_sources',frozen_search):
            for name,prompt,intent,expected in scenarios:
                before, start, searches_before = len(calls),time.monotonic(),len(search_calls)
                case = {'case':name,'prompt':prompt,'routing_mode':'preclassified' if intent else 'live_fusion'}
                try:
                    result = await asyncio.wait_for(entry.run(Request(prompt,'acceptance-fixture',name,uuid4().hex,
                        knowledge_mode='off',intent=intent)),120)
                    passed = result['capability']==expected and not result['intent']['needs_clarification']
                    if name in {'domain_parallel','compound_route'}:
                        responses = result.get('response',{}).get('metadata',{}).get('agent_responses',[])
                        passed = passed and len(responses)==2 and all(r['success'] for r in responses)
                        if name=='domain_parallel':
                            passed = (passed and len(search_calls)>searches_before and
                                      result['response']['metadata']['status']=='completed')
                        else:
                            # This prompt deliberately supplies no test material or retrieval instruction.
                            # Clarifying unavailable material is valid, claiming all work completed is not.
                            statuses=[r.get('result_status') for r in responses]
                            passed = passed and (result['response']['metadata']['status']!='completed' or 'clarify' not in statuses)
                    case.update(status='passed' if passed else 'failed',result=result)
                except Exception as exc:
                    case.update(status='failed',error=type(exc).__name__)
                case.update(model_calls=len(calls)-before,wall_ms=round((time.monotonic()-start)*1000))
                turns.append(case)
                print(json.dumps({k:case[k] for k in ('case','status','model_calls','wall_ms')},ensure_ascii=False),flush=True)
    finally:
        usage_sink.reset(token)
        report = {'mode':'live-model with frozen domain tool data','cases':turns,'calls':calls,'usage':usage,
                  'search_calls':search_calls,'limits':'No real corporate facts, file changes or full research execution.'}
        path = folder/'summary.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'report':str(path),'passed':sum(c['status']=='passed' for c in turns),'total':len(turns)},ensure_ascii=False))
    return 0 if len(turns)==len(scenarios) and all(c['status']=='passed' for c in turns) else 1


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Call configured model (may incur charges)')
    if not parser.parse_args().live:
        parser.error('Use --live explicitly; offline coverage: pytest tests/test_echomind_alignment.py')
    raise SystemExit(asyncio.run(main()))
