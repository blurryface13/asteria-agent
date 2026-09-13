"""Conversation-scoped, persisted intent turns. Research still runs in its worker."""
import asyncio
import hashlib
import json
import os
import logging
import traceback
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.auth.db import get_pool
from backend.auth.dependencies import get_current_user_email
from backend.runs.routes import validate_request
from backend.runs.store import RunStore
from asteria_researcher.utils.usage_context import usage_sink

router = APIRouter(prefix='/api/coordinator', tags=['coordinator'])
tasks: set[asyncio.Task] = set()
logger = logging.getLogger(__name__)


def conversation_context(messages, completed_run=None, artifacts=()):
    """A completed research request is history, not an unanswered user turn."""
    history = []
    if completed_run:
        history.append({'role': 'assistant', 'content': json.dumps({
            'research_status': 'completed',
            'report': 'The completed report is provided in the report context.',
            'artifacts': [dict(item) for item in artifacts],
        }, ensure_ascii=False)})
    history.extend({'role': m['role'], 'content': m['content']} for m in messages
                   if m['role'] in {'user', 'assistant'} and
                   (not completed_run or m['created_at'] > completed_run['finished_at']))
    return history


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=1, max_length=50000)
    research_request: dict | None = None
    knowledge_mode: Literal['auto','off','selected'] = 'auto'
    knowledge_ids: list[str] = Field(default_factory=list, max_length=3)

    @field_validator('message')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('message must not be blank')
        return value.strip()


async def get_turn(email, conversation_id, request_id=None):
    pool = await get_pool()
    async with pool.acquire() as c:
        if not await c.fetchval('SELECT 1 FROM workspace_conversations WHERE id=$1 AND user_email=$2', conversation_id, email):
            raise HTTPException(404, 'Conversation not found')
        # A dead API cannot complete its in-flight model call. Never replay it
        # automatically: the provider may already have billed that attempt.
        await c.execute("""UPDATE coordinator_turns SET status='interrupted',
            error='协调请求已中断，请检查后重新提交；不会自动重复调用模型', finished_at=now()
            WHERE conversation_id=$1 AND status='running' AND started_at < now()-interval '5 minutes'""", conversation_id)
        row = await c.fetchrow('''SELECT * FROM coordinator_turns WHERE conversation_id=$1
            AND ($2::text IS NULL OR request_id=$2) ORDER BY started_at DESC LIMIT 1''', conversation_id, request_id)
    if row is None:
        return None
    return {k: row[k] for k in ('request_id', 'conversation_id', 'status', 'result', 'error', 'usage', 'started_at', 'finished_at')}


async def submit_turn(body, email):
    if body.knowledge_mode == 'selected':
        if not body.knowledge_ids:
            raise HTTPException(422, '请选择知识库')
        from backend.knowledge.managed import get_library
        for kb_id in body.knowledge_ids:
            await get_library(email, kb_id)
    if body.research_request is not None:
        validate_request({**body.research_request, 'task': body.message})
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    pool = await get_pool()
    async with pool.acquire() as c, c.transaction():
        conversation = await c.fetchrow('SELECT * FROM workspace_conversations WHERE id=$1 AND user_email=$2 FOR UPDATE', body.conversation_id, email)
        if not conversation:
            raise HTTPException(404, 'Conversation not found')
        previous = await c.fetchrow('SELECT * FROM coordinator_turns WHERE conversation_id=$1 AND request_id=$2', body.conversation_id, body.request_id)
        if previous:
            if previous['request_hash'] != fingerprint:
                raise HTTPException(409, '同一请求标识不能用于不同内容')
            return False
        if await c.fetchval("SELECT 1 FROM coordinator_turns WHERE conversation_id=$1 AND status='running'", body.conversation_id):
            raise HTTPException(409, '当前对话仍在处理上一条消息')
        if await c.fetchval("SELECT 1 FROM research_runs WHERE conversation_id=$1 AND status IN ('queued','running','waiting_approval','cancel_requested')", body.conversation_id):
            raise HTTPException(409, '研究任务仍在运行，请通过审批节点反馈或等待完成')
        await c.execute('''INSERT INTO coordinator_turns(conversation_id,request_id,request_hash,status)
            VALUES($1,$2,$3,'running')''', body.conversation_id, body.request_id, fingerprint)
        await c.execute('''INSERT INTO workspace_messages(id,conversation_id,role,content,metadata)
            VALUES($1,$2,'user',$3,$4)''', str(uuid4()), body.conversation_id, body.message, {'turn_id': body.request_id})
        await c.execute('UPDATE workspace_conversations SET updated_at=now() WHERE id=$1', body.conversation_id)
    return True


async def execute_turn(body, email):
    from asteria_researcher.agentic.intent import analyze_intent
    from backend.server.agentic_runner import configured_model
    from backend.chat.chat import ChatAgentWithMemory

    pool = await get_pool()

    async def record(event):
        if event.get('type') != 'usage':
            return
        event = {k: event.get(k) for k in ('type','model','provider','attempt','usage','available')}
        async with pool.acquire() as c:
            await c.execute('''UPDATE coordinator_turns SET usage=usage || $3::jsonb
                WHERE conversation_id=$1 AND request_id=$2''', body.conversation_id, body.request_id, [event])

    async def work():
        async with pool.acquire() as c:
            messages = await c.fetch('''SELECT role,content,created_at FROM workspace_messages
                WHERE conversation_id=$1 ORDER BY sequence_no''', body.conversation_id)
            report = await c.fetchval('SELECT answer FROM reports WHERE id=$1 AND user_email=$2', body.conversation_id, email) or ''
            completed_run = await c.fetchrow('''SELECT id,finished_at FROM research_runs
                WHERE conversation_id=$1 AND status='completed' ORDER BY finished_at DESC LIMIT 1''', body.conversation_id) if report else None
            artifacts = await c.fetch('SELECT kind,path FROM research_artifacts WHERE run_id=$1', completed_run['id']) if completed_run else []
        history = conversation_context(messages, completed_run, artifacts)
        config = os.getenv('CONFIG_PATH') or None
        from backend.knowledge import managed
        from asteria_researcher.agentic.intent import Intent
        model = configured_model(config)
        from backend.memory.service import snapshot
        memory = await snapshot(email, body.conversation_id, body.message, model)
        memory_context.set(memory)
        catalog = await managed.libraries(email) if body.knowledge_mode != 'off' else []
        if body.knowledge_mode == 'selected':
            allowed = [k for k in catalog if k['id'] in body.knowledge_ids]
            if len(allowed) != len(set(body.knowledge_ids)):
                raise HTTPException(404,'所选知识库不存在')
            # Explicit library scope is a user command, not a keyword heuristic.
            intent = Intent(capability='knowledge_chat', reason='用户指定知识库问答',knowledge_ids=body.knowledge_ids)
        elif catalog:
            intent = await analyze_intent(body.message, model, history=history[:-1], report=report,
                knowledge_catalog=[{k:item[k] for k in ('id','name','description','ready_documents')} for item in catalog])
        else:
            intent = await analyze_intent(body.message, model, history=history[:-1], report=report)
        result = {'intent': intent.model_dump(), 'capability': intent.capability, 'memory': memory}
        if intent.capability == 'knowledge_chat':
            allowed_ids = {k['id'] for k in catalog}
            if not intent.knowledge_ids or not set(intent.knowledge_ids) <= allowed_ids:
                raise ValueError('Coordinator selected invalid library scope')
            query = intent.retrieval_query or body.message
            if body.knowledge_mode == 'selected' and len(history)>1:
                query = await model('Rewrite the latest question as a standalone retrieval query using conversation only for references. Do not answer. Return only the query.',json.dumps({'question':body.message,'history':history[:-1][-8:]},ensure_ascii=False))
            content, sources = await managed.answer(email,intent.knowledge_ids,query,model,history[:-1])
            citation_lines = [f"[{s['index']}] {s['name']}" + (f" · 第{s['page']}页" if s['page'] else '') + f" · 版本 {s['version_id'][:8]}" for s in sources]
            # The model may echo an older source footer from conversation history.
            # Render canonical metadata once, without altering inline references.
            content = '\n'.join(line for line in content.splitlines() if line.strip() not in citation_lines).rstrip()
            citations = '\n\n' + '\n'.join(citation_lines) if sources else ''
            result['response']={'role':'assistant','content':content+citations,'metadata':{
                'turn_id':body.request_id,'knowledge_ids':intent.knowledge_ids,'sources':sources,'retrieval_query':query}}
        elif intent.capability == 'general_chat':
            agent = ChatAgentWithMemory(report=report, config_path=config, headers=None)
            content, metadata = await agent.chat(history, None, allow_tools=bool(report))
            if not content or not content.strip():
                raise ValueError('模型未返回有效回答')
            result['response'] = {'role': 'assistant', 'content': content, 'metadata': {'tool_calls': metadata or [], 'turn_id': body.request_id}}
        elif body.research_request is not None:
            request = {**body.research_request, 'task': body.message, 'coordinator_capability': intent.capability}
            # Request identity survives lost HTTP responses; worker ownership and
            # research lifecycle continue to be enforced by the existing store.
            run = await RunStore().submit(email, body.request_id, body.conversation_id, validate_request(request))
            result['run_id'] = run['id']
        async with pool.acquire() as c, c.transaction():
            status = await c.fetchval('SELECT status FROM coordinator_turns WHERE conversation_id=$1 AND request_id=$2 FOR UPDATE', body.conversation_id, body.request_id)
            if status != 'running':
                return
            if 'response' in result:
                message = result['response']
                message['metadata']['memory'] = memory
                await c.execute('''INSERT INTO workspace_messages(id,conversation_id,role,content,metadata)
                    VALUES($1,$2,'assistant',$3,$4)''', str(uuid4()), body.conversation_id, message['content'], message['metadata'])
            await c.execute('''UPDATE workspace_conversations SET mode=$2,updated_at=now() WHERE id=$1''',
                            body.conversation_id, 'research' if report or intent.capability not in {'general_chat','knowledge_chat'} else 'chat')
            await c.execute("""UPDATE coordinator_turns SET status='completed',result=$3,finished_at=now()
                WHERE conversation_id=$1 AND request_id=$2""", body.conversation_id, body.request_id, result)

    from asteria_researcher.utils.memory_context import memory_context
    memory_token = memory_context.set(None)
    token = usage_sink.set(record)
    try:
        await asyncio.wait_for(work(), timeout=240)
    except BaseException as exc:
        if not isinstance(exc, (Exception, asyncio.CancelledError)):
            raise
        # Diagnose exact code locations without logging provider exception text,
        # which may contain credentials, URLs or private request payloads.
        logger.error('Coordinator turn %s failed: %s; frames=%s', body.request_id,
                     type(exc).__name__, [(f.filename, f.lineno, f.name) for f in traceback.extract_tb(exc.__traceback__)])
        # Provider exception strings can contain request URLs/credentials.
        status = 'interrupted' if isinstance(exc, asyncio.CancelledError) else 'failed'
        error = '协调请求中断，未自动重试' if status == 'interrupted' else f'协调请求失败（{type(exc).__name__}），请检查模型服务或研究配置后重新提交'
        if isinstance(exc, HTTPException):
            error = str(exc.detail)
        cause = exc
        while cause:
            if getattr(cause, 'status_code', None) == 402:
                error = '模型服务余额不足（HTTP 402），充值后重新提交；本次未生成回答'
            cause = cause.__cause__
        async with pool.acquire() as c:
            await c.execute('''UPDATE coordinator_turns SET status=$3,error=$4,finished_at=now()
                WHERE conversation_id=$1 AND request_id=$2 AND status='running' ''', body.conversation_id, body.request_id, status, error)
    finally:
        usage_sink.reset(token)
        memory_context.reset(memory_token)


@router.post('/route')
async def route(body: TurnRequest, email=Depends(get_current_user_email)):
    # Expire abandoned turns before taking the conversation lock.
    await get_turn(email, body.conversation_id)
    if await submit_turn(body, email):
        task = asyncio.create_task(execute_turn(body, email))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    return await get_turn(email, body.conversation_id, body.request_id)


@router.get('/turn')
async def read(conversation_id: str, request_id: str | None = None, email=Depends(get_current_user_email)):
    return {'turn': await get_turn(email, conversation_id, request_id)}


async def shutdown():
    pending = list(tasks)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
