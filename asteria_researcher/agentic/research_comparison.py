"""Paired architectural probe, NOT a coding benchmark or execution sandbox.

Same code and frozen, manually paraphrased evidence for direct reading and
delegated research. Reuses production loops; never executes proposed source.
"""
import asyncio
import hashlib
import json
import time
from pathlib import Path

from .autonomous import AutonomousReview
from .coding import run_coding
from .coding_research_tools import build_paper_tools
from .collaboration import Assignment
from .library import PaperLibrary, canonical
from asteria_researcher.utils.usage_context import usage_sink

PAPER = 'https://arxiv.org/abs/1706.03762'
SOURCE = 'https://arxiv.org/html/1706.03762v7#S3.SS2.SSS1'
# Intentionally a small paraphrase, not downloaded full text or a real PDF page.
EVIDENCE = ('[人工整理的冻结测试材料，非PDF原文；夹具第1页对应论文3.2.1节] '
    'Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V。缩放作用于softmax之前的点积，'
    'd_k是键向量的维度，不是序列长度。分量独立且均值为0、方差为1时，点积方差为d_k；'
    '较大的点积可能使softmax落在梯度很小的区域。该说明不是完整论文复现结论。')
PROMPT = ('检查 attention_demo.py。当前实现能通过语法检查，但注意力计算可能与 '
    + PAPER + ' 的定义不一致。请先读代码，根据本次提供的论文材料核实，'
    '给出修改diff，说明原因和未验证项；不修改文件，不运行代码。')
MODES = ('direct', 'delegated')


def assess_path(mode, result, evidence):
    """Independent execution contract, never an LLM's own success verdict."""
    failures=[]
    if not result or result.get('status')!='completed':
        failures.append('agent_not_completed')
    if not any(e.get('passages') for e in evidence):
        failures.append('no_observed_passage')
    requests=(result or {}).get('research_requests',[])
    if mode=='delegated' and not any(q.get('status')=='completed' for q in requests):
        failures.append('no_completed_research_handoff')
    if mode=='direct' and requests:
        failures.append('direct_arm_used_handoff')
    diffs=[t['result'] for t in (result or {}).get('tool_results',[]) if t['tool']=='preview_code_diff']
    if not diffs or not diffs[-1].get('proposed_syntax',{}).get('valid_syntax'):
        failures.append('no_syntax_valid_diff')
    return {'passed':not failures,'failures':failures,
            'scope':'observed evidence access + syntax-valid preview, NOT functional correctness'}


async def noop(*args, **kwargs):
    pass


class FrozenLibrary(PaperLibrary):
    """Same page/citation adapters with a closed evidence set and no network."""
    def __init__(self, folder, *, unavailable=False):
        super().__init__(folder, None, None)
        self.unavailable = unavailable
        self.add({'url': PAPER, 'title': 'Attention Is All You Need — frozen test excerpt'})
        self.papers[PAPER] = {'url': PAPER, 'text': EVIDENCE, 'bytes': len(EVIDENCE.encode()),
                              'pages': [{'page': 1, 'text': EVIDENCE}]}

    async def search(self, query, **kwargs):
        return [self.nodes[PAPER]] if not self.unavailable else []

    async def read(self, url):
        if canonical(url) != PAPER or self.unavailable:
            raise ValueError('本对照材料不可用；禁止外网兜底或猜测证据')
        return await super().read(url)

    def read_passage(self, *args, **kwargs):
        if self.unavailable:
            raise ValueError('本对照材料不可用；保留证据缺口')
        return super().read_passage(*args, **kwargs)

    async def references(self, *args, **kwargs):
        raise ValueError('冻结对照不扩展参考文献')


class ScriptedModel:
    """Deterministic path replay. No model quality or speed claims permitted."""
    def __init__(self, mode, original):
        self.mode, self.original = mode, original

    async def __call__(self, system, raw):
        data = json.loads(raw)
        obs = data['observations']
        seen = {o.get('tool') for o in obs}
        unavailable = any('error' in o for o in obs)
        if 'tools' not in data:  # Real research subagent action schema.
            if unavailable:
                action = {'tool':'finish', 'summary':'材料不可用，不能确定公式。', 'outcome':'incomplete'}
            elif 'read' not in seen:
                action = {'tool':'read', 'paper_ids':[PAPER]}
            elif 'read_passage' not in seen:
                action = {'tool':'read_passage', 'paper_ids':[PAPER], 'page':1}
            else:
                action = {'tool':'finish', 'summary':f'夹具第1页：softmax之前除以sqrt(d_k)，d_k为键维度。{PAPER}'}
        elif 'read_workspace_file' not in seen:
            action = {'tool':'read_workspace_file', 'arguments':{'name':'attention_demo.py'}}
        elif unavailable or any(o.get('result',{}).get('status')=='incomplete' for o in obs):
            action = {'tool':'finish', 'outcome':'incomplete', 'summary':'无法取得可核查依据，保留问题，未执行。'}
        elif self.mode == 'delegated' and 'request_research' not in seen:
            action = {'tool':'request_research', 'arguments':{
                'question':'请核对注意力公式中缩放项的位置和维度含义。',
                'observed_problem':'代码将query与key转置点积后直接softmax，未发现缩放。',
                'expected_answer':'给出冻结材料对应公式、适用维度和来源；不要接管代码修改。'}}
        elif self.mode == 'direct' and 'read_paper' not in seen:
            action = {'tool':'read_paper', 'arguments':{'paper_url':PAPER}}
        elif self.mode == 'direct' and 'read_paper_passage' not in seen:
            action = {'tool':'read_paper_passage', 'arguments':{'paper_url':PAPER, 'page':1}}
        elif 'preview_code_diff' not in seen:
            observed = next(o['observation_id'] for o in obs if o.get('tool')=='read_workspace_file')
            revised = self.original.replace('(query @ key.transpose(-2, -1)).softmax(dim=-1)',
                '((query @ key.transpose(-2, -1)) / (key.shape[-1] ** 0.5)).softmax(dim=-1)')
            action = {'tool':'preview_code_diff', 'arguments':{'observation_id':observed, 'proposed_content':revised}}
        else:
            action = {'tool':'finish', 'summary':f'根据夹具第1页预览缩放修正，未应用也未运行。{PAPER}'}
        return json.dumps({'purpose':'核对局部注意力公式差异', **action},ensure_ascii=False)


async def run_arm(mode, model, folder, original, *, model_mode, unavailable=False,
                  max_calls=16, deadline=180, enforce_path_policy=True):
    if mode not in MODES:
        raise ValueError('Unknown comparison arm')
    folder = Path(folder)
    calls, events, usage = [], [], []
    started = time.monotonic()

    async def measured(system, payload):
        if len(calls) >= max_calls:
            raise RuntimeError('Comparison model-call budget exhausted')
        role='coding' if 'tools' in json.loads(payload) else 'research'
        if role=='coding' and enforce_path_policy:
            # Policy is an explicit experimental variable. Never feed the answer.
            system += ('\nControlled evidence-access comparison: the context evidence_scope is only a label, '
                'NOT supplied evidence. You must acquire the actual material using tools. '
                'If inaccessible, finish incomplete; your pretrained knowledge is not a substitute. '
                'Only a diff preview is available; it is NOT a pending approval proposal. ')
            system += ('In this arm, obtain required scientific evidence through request_research, even for a '
                       'local formula check; direct paper tools are disabled. Resume the coding task after its reply.'
                       if mode=='delegated' else
                       'In this arm, obtain scientific evidence directly through the paper tools; handoff is disabled.')
        call = {'role':role,'input_chars':len(system)+len(payload)}
        calls.append(call)
        t = time.monotonic()
        try:
            value = await model(system, payload)
            call['output_chars'] = len(value)
            return value
        finally:
            call['wall_ms'] = round((time.monotonic()-t)*1000,2)

    async def emit(kind, event): events.append(event)
    async def capture_usage(event):
        usage.append({k:event.get(k) for k in ('model','provider','attempt','usage','available')})
    runtime = AutonomousReview(measured,None,emit,noop,folder,online_rag=False,max_actions=30)
    runtime.query, runtime.plan = PROMPT, {}
    runtime.library = FrozenLibrary(runtime.folder,unavailable=unavailable)
    agent = 'coding-' + mode
    async def read(arguments):
        if arguments != {'name':'attention_demo.py'}:
            raise ValueError('Only the immutable comparison fixture is readable')
        return {'name':'attention_demo.py','content':original,'exists':True}
    assignment = Assignment(name='注意力局部公式排查',objective=PROMPT,role='coding',
                            focus='核对缩放位置与维度',expected_output='证据与diff；不执行')
    tools = {'read_workspace_file': ({'type':'object','properties':{'name':{'const':'attention_demo.py'}},
              'required':['name'],'additionalProperties':False},read)}
    if mode == 'direct':
        tools.update(build_paper_tools(runtime,agent))
    async def help_research(request, request_id, requester):
        if mode != 'delegated':
            raise ValueError('Handoff is disabled in the direct-reading arm')
        return await runtime.answer_research_request(assignment,request,request_id,requester)
    def consume():
        if runtime.actions >= runtime.max_actions-5:
            return False
        runtime.actions += 1
        return True
    failure, result = None, None
    token = usage_sink.set(capture_usage)
    try:
        result = await asyncio.wait_for(run_coding(assignment,runtime.llm,tools,help_research,runtime.event,
            consume_action=consume,context={'comparison_arm':mode,'evidence_scope':'frozen paraphrase, fixture page 1'},
            agent_id=agent,allow_research_request=mode=='delegated'),deadline)
    except Exception as exc:
        cause, balance = exc, False
        while cause:
            balance |= getattr(cause,'status_code',None)==402
            cause = cause.__cause__
        failure = {'type':type(exc).__name__, 'reason':'HTTP 402' if balance else 'provider/budget/deadline failure'}
    finally:
        usage_sink.reset(token)
    tool_results = result.get('tool_results',[]) if result else []
    diffs = [t['result'] for t in tool_results if t['tool']=='preview_code_diff']
    observed_evidence = any(e['passages'] for e in runtime.evidence)
    # Structural observations only; semantic correctness is deliberately not inferred.
    report = {'arm':mode,'model_mode':model_mode,'status':'blocked' if failure else result['status'],
        'enforce_path_policy':enforce_path_policy,
        'limits':{'model_calls':max_calls,'deadline_seconds':deadline,
                  'provider_retries':'disabled by live CLI'},
        'failure':failure,'calls':calls,'model_calls':len(calls),
        'wall_ms':round((time.monotonic()-started)*1000,2),
        'handoff_wait_ms':sum(q.get('wait_ms',0) for q in (result or {}).get('research_requests',[])),
        'tool_calls':sum(e.get('status')=='started' and e.get('call_id') is not None for e in events),
        'observed_evidence':observed_evidence,'diff_produced':bool(diffs),
        'proposed_syntax_valid':diffs[-1].get('proposed_syntax',{}).get('valid_syntax') if diffs else None,
        'functional_tests_run':False,'patch_applied':False,'semantic_quality':'not_scored',
        'usage':usage,'input_chars':sum(c['input_chars'] for c in calls),
        'output_chars':sum(c.get('output_chars',0) for c in calls),
        'source_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'evidence_sha256':hashlib.sha256(EVIDENCE.encode()).hexdigest(),
        'evidence_provenance':{'source':SOURCE,'kind':'manual_paraphrase_fixture','page':'fixture page 1, not PDF page'},
        'runtime_folder':str(runtime.folder),'result':result,'path_contract':assess_path(mode,result,runtime.evidence),
        'note':'Scripted model counts/timings describe replay structure, NOT live quality, production latency or token cost.'}
    (runtime.folder/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report
