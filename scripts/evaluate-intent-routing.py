"""Small, explicit routing probes. Vector matches are not end-to-end accuracy.

python scripts/evaluate-intent-routing.py --vector-only
python scripts/evaluate-intent-routing.py --live
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = [
    ("检查attention.py文件并分析实现差异", "workspace_coding"),
    ("制定机器学习的学习计划", "learning_guidance"),
    ("对比扩散模型水印论文并生成文献综述", "literature_review"),
    ("查询今年会议投稿截止时间和材料要求", "submission_consulting"),
    ("解释市盈率与现金流，不要执行交易", "financial_research"),
    ("核实这家公司的主体和公开业务资料", "company_research"),
]


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT / ".env.lab", override=True)
    from backend.server.agentic_runner import configured_model
    from asteria_researcher.agentic.intent import analyze_intent
    from asteria_researcher.agentic.intent_fusion import IntentFusion, TEMPLATES
    model, fusion = configured_model(), IntentFusion()
    output = ROOT / 'outputs' / ('intent-routing-' + uuid4().hex[:10])
    output.mkdir(parents=True)
    report = {'mode':'vector-only' if args.vector_only else 'live-routing', 'cases':[],
              'note':'六条固定探针，不代表生产准确率；向量分支匹配不代表融合路由或任务已执行。'}
    try:
        for query, expected in CASES:
            if args.vector_only:
                result = await fusion.vector_vote(query,sorted(TEMPLATES),model.intent_embeddings,model.routing_identity)
            else:
                result = (await analyze_intent(query,model)).model_dump()
            report['cases'].append({'query':query,'expected':expected,'result':result,
                                    'matches_expected':result['capability']==expected and not result.get('needs_clarification',False)})
        report['status']='finished'
    except Exception as exc:
        cause=exc
        balance=False
        while cause:
            balance |= getattr(cause,'status_code',None)==402
            cause=cause.__cause__
        report.update(status='blocked',reason='HTTP 402：模型余额不足' if balance else type(exc).__name__)
    finally:
        (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'output':str(output/'summary.json'),**report},ensure_ascii=False))
    return 0 if report['status']=='finished' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--vector-only',action='store_true',help='仅调用已配置Embedding，不调用LLM')
    group.add_argument('--live',action='store_true',help='调用当前LLM进行六条路由验证，可能产生费用')
    raise SystemExit(asyncio.run(run(parser.parse_args())))
