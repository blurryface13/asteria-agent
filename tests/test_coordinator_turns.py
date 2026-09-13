"""Coordinator semantics and disposable-schema lifecycle regression tests."""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from backend.server.coordinator import TurnRequest


def test_request_rejects_blank_or_client_history():
    with pytest.raises(ValidationError):
        TurnRequest(conversation_id='c', request_id='request-1', message='  ')
    with pytest.raises(ValidationError):
        TurnRequest(conversation_id='c', request_id='request-1', message='hello', messages=[])


def test_completed_research_is_not_an_unanswered_request():
    from backend.server.coordinator import conversation_context
    messages = [
        {'role': 'user', 'content': 'write and export PDF', 'created_at': 1},
        {'role': 'user', 'content': 'explain the report briefly', 'created_at': 3},
    ]
    history = conversation_context(messages, {'finished_at': 2}, [{'kind':'pdf','path':'outputs/test/report.pdf'}])
    assert len(history) == 2 and history[0]['role'] == 'assistant'
    assert json.loads(history[0]['content'])['artifacts'][0]['kind'] == 'pdf'
    assert history[1]['content'] == 'explain the report briefly'
    assert 'write and export PDF' not in str(history)


def test_intent_receives_conversation_context():
    from asteria_researcher.agentic.intent import analyze_intent
    async def model(system, payload):
        data = json.loads(payload)
        assert data['history'][0]['content'] == '设计测试用例'
        assert data['report'] == 'a report'
        return '{"capability":"general_chat","reason":"回答上下文追问"}'
    asyncio.run(analyze_intent('翻译刚才结果', model, [{'role': 'assistant', 'content': '设计测试用例'}], 'a report'))


def test_supplied_general_research_is_not_reclassified(monkeypatch):
    from backend.server import websocket_manager as module
    from asteria_researcher.agentic import intent
    class Report:
        def __init__(self, **kwargs): pass
        async def run(self): return 'result'
    class Sink:
        feedback_queue = object()
        skill_options = None
        async def send_json(self, data): pass
    async def forbidden(*args, **kwargs):
        pytest.fail('must not classify twice')
    import backend.report_type
    monkeypatch.setattr(backend.report_type, 'BasicReport', Report)
    monkeypatch.setattr(intent, 'analyze_intent', forbidden)
    assert asyncio.run(module.run_agent('task', 'research_report', 'web', [], [], 'Objective', None,
        logs_handler=Sink(), coordinator_capability='general_research')) == 'result'


def test_persisted_turn_lifecycle(monkeypatch):
    if os.getenv('ASTERIA_RUNS_DB_TESTS') != '1':
        pytest.skip('Requires opt-in isolated PostgreSQL schema')
    asyncio.run(exercise(monkeypatch))


def test_tool_chat_records_usage_and_does_not_fallback(monkeypatch):
    from types import SimpleNamespace
    from langchain_core.messages import AIMessage
    from asteria_researcher.utils.tools import create_chat_completion_with_tools
    from asteria_researcher.utils.usage_context import usage_sink
    from asteria_researcher.llm_provider.generic.base import GenericLLMProvider
    events = []
    class Model:
        failing = False
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            if self.failing:
                raise RuntimeError('model unavailable')
            return AIMessage(content='answer', usage_metadata={'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12})
    model = Model()
    monkeypatch.setattr(GenericLLMProvider, 'from_provider', lambda *args, **kwargs: SimpleNamespace(llm=model))
    async def run():
        async def record(event): events.append(event)
        token = usage_sink.set(record)
        try:
            result = await create_chat_completion_with_tools([{'role': 'user', 'content': 'report question'}], [], model='test', llm_provider='test')
            assert result == ('answer', [])
            assert events[0]['usage']['total_tokens'] == 12
            model.failing = True
            with pytest.raises(RuntimeError, match='model unavailable'):
                await create_chat_completion_with_tools([{'role': 'user', 'content': 'report question'}], [], model='test', llm_provider='test')
        finally:
            usage_sink.reset(token)
    asyncio.run(run())


async def exercise(monkeypatch):
    import asyncpg
    from dotenv import load_dotenv
    from backend.server import coordinator as module
    from backend.runs import store as runs
    from backend.server import agentic_runner
    from backend.chat.chat import ChatAgentWithMemory
    from asteria_researcher.utils.usage_context import record_usage
    load_dotenv()
    schema = 'test_coordinator_' + uuid4().hex
    admin = await asyncpg.connect(os.environ['DATABASE_URL'])
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    async def init(c):
        await c.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], init=init, min_size=1, max_size=5, server_settings={'search_path': schema})
    async def get_pool(): return pool
    monkeypatch.setattr(module, 'get_pool', get_pool)
    from backend.knowledge import managed
    monkeypatch.setattr(managed, 'get_pool', get_pool)
    from backend.memory import service as memory
    monkeypatch.setattr(memory, 'get_pool', get_pool)
    async def empty_memory(*args, **kwargs):
        return {'project_id': None, 'files': [], 'selection': 'test'}
    monkeypatch.setattr(memory, 'snapshot', empty_memory)
    monkeypatch.setattr(runs, 'get_pool', get_pool)
    capabilities, histories, configs = [], [], []
    capability = 'general_chat'
    def configured(config):
        configs.append(config)
        async def model(system, query):
            capabilities.append(query)
            await record_usage('test', 'test', 1, {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12})
            return json.dumps({'capability': capability, 'reason': 'test'})
        return model
    monkeypatch.setattr(agentic_runner, 'configured_model', configured)
    monkeypatch.setenv('CONFIG_PATH', 'test-config')
    def constructor(self, report, config_path, headers):
        self.report = report
        assert config_path == 'test-config'
    async def chat(self, messages, websocket, allow_tools):
        histories.append(messages)
        assert allow_tools == bool(self.report)
        await record_usage('test', 'test', 1, {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12})
        return ('Design test cases' if len(messages) > 1 else '设计测试用例'), []
    monkeypatch.setattr(ChatAgentWithMemory, '__init__', constructor)
    monkeypatch.setattr(ChatAgentWithMemory, 'chat', chat)
    try:
        async with pool.acquire() as c:
            for path in ('backend/auth/workspace_schema.sql','backend/auth/reports_schema.sql','backend/runs/schema.sql','backend/knowledge/schema.sql'):
                await c.execute(Path(path).read_text())
            await c.execute("INSERT INTO workspace_conversations(id,user_email,title,mode) VALUES('c','owner','test','chat')")
        body = TurnRequest(conversation_id='c', request_id='request-1', message='改写测试用例设计')
        assert sum(await asyncio.gather(*[module.submit_turn(body, 'owner') for _ in range(5)])) == 1
        with pytest.raises(HTTPException):
            await module.get_turn('intruder','c')
        with pytest.raises(HTTPException):
            await module.submit_turn(body.model_copy(update={'message':'changed'}), 'owner')
        with pytest.raises(HTTPException):
            await module.submit_turn(body.model_copy(update={'request_id':'request-2'}), 'owner')
        await module.execute_turn(body, 'owner')
        result = await module.get_turn('owner','c')
        assert result['status'] == 'completed' and len(result['usage']) == 2
        assert not await module.submit_turn(body, 'owner')
        followup = body.model_copy(update={'request_id':'request-2', 'message':'把刚才结果翻译成英文'})
        assert await module.submit_turn(followup, 'owner')
        await module.execute_turn(followup, 'owner')
        assert histories[-1][1]['content'] == '设计测试用例'
        async with pool.acquire() as c:
            assert [r['role'] for r in await c.fetch("SELECT role FROM workspace_messages ORDER BY sequence_no")] == ['user','assistant','user','assistant']
            assert await c.fetchval('SELECT count(*) FROM research_runs') == 0
            await c.execute("INSERT INTO reports(id,user_email,answer,timestamp) VALUES('c','owner','test report',0)")
        report_chat = body.model_copy(update={'request_id':'request-3','message':'解释报告'})
        await module.submit_turn(report_chat,'owner')
        await module.execute_turn(report_chat,'owner')
        assert (await module.get_turn('owner','c'))['status'] == 'completed'
        # Research is submitted by the server, without another browser action.
        capability = 'literature_review'
        research = body.model_copy(update={'request_id':'request-4','message':'write review', 'research_request':{'report_type':'research_report'}})
        await module.submit_turn(research,'owner')
        await module.execute_turn(research,'owner')
        routed = await module.get_turn('owner','c')
        assert routed['result']['run_id']
        assert len(capabilities) == 4 and configs == ['test-config'] * 4
        await module.submit_turn(research,'owner')  # completed replay, no duplicate Run
        async with pool.acquire() as c:
            assert await c.fetchval('SELECT count(*) FROM research_runs') == 1
            await c.execute("UPDATE research_runs SET status='cancelled'")
        # A failed generation keeps the user message and never fabricates an answer.
        async def failing(*args, **kwargs): raise ValueError('failed fixture')
        capability = 'general_chat'
        monkeypatch.setattr(ChatAgentWithMemory, 'chat', failing)
        failed = body.model_copy(update={'request_id':'request-5'})
        await module.submit_turn(failed,'owner')
        await module.execute_turn(failed,'owner')
        assert (await module.get_turn('owner','c'))['status'] == 'failed'
        assert not await module.submit_turn(failed,'owner')
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()
