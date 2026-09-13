import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from backend.memory import service
from asteria_researcher.utils.memory_context import memory_context, inject_memory


@pytest.fixture
def directory(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTERIA_WORKSPACES_ROOT', str(tmp_path))
    return tmp_path / 'workspace' / '.asteria'


def test_markdown_versions_external_edit_and_path_boundaries(directory):
    first = service.write_file(directory, 'PROJECT.md', '# First', None)
    assert service.read_file(directory, 'PROJECT.md')['content'] == '# First'
    Path(first['path']).write_text('# Local edit')
    with pytest.raises(HTTPException) as conflict:
        service.write_file(directory, 'PROJECT.md', '# Stale browser', first['version'])
    assert conflict.value.status_code == 409
    latest = service.read_file(directory, 'PROJECT.md')
    assert latest['content'] == '# Local edit'
    service.write_file(directory, 'PROJECT.md', '# Merged', latest['version'])
    for name in ['../../secret.md', '/tmp/secret.md', 'memory/../secret.md']:
        with pytest.raises(HTTPException):
            service.read_file(directory, name)
    outside = directory.parent / 'secret.md'
    outside.write_text('private')
    (directory / 'memory').mkdir(exist_ok=True)
    (directory / 'memory' / 'escape.md').symlink_to(outside)
    with pytest.raises(HTTPException):
        service.read_file(directory, 'memory/escape.md')
    (directory / 'memory' / 'escape.md').unlink()
    os.link(outside, directory / 'memory' / 'hard.md')
    with pytest.raises(HTTPException):
        service.read_file(directory, 'memory/hard.md')
    with pytest.raises(HTTPException) as large:
        service.write_file(directory, 'memory/large.md', '文'*12000, None)
    assert large.value.status_code == 413


def test_injection_is_scoped_and_does_not_mutate_messages():
    messages = [{'role':'system','content':'Return JSON'}, {'role':'user','content':'question'}]
    async def task(text):
        token = memory_context.set({'files':[{'name':'PROJECT.md','content':text}]})
        try:
            await asyncio.sleep(0)
            injected = inject_memory(messages)
            assert injected[0] == messages[0] and injected[-1] == messages[-1]
            return injected[1]['content']
        finally:
            memory_context.reset(token)
    async def exercise():
        a,b = await asyncio.gather(task('alpha-only'), task('beta-only'))
        assert 'alpha-only' in a and 'beta-only' not in a
        assert 'beta-only' in b and 'alpha-only' not in b
    asyncio.run(exercise())
    assert len(messages) == 2 and inject_memory(messages) is messages
    token = memory_context.set({'files':[{'name':'PROJECT.md','content':'new value'}]})
    try:
        history = messages[:1]+[{'role':'user','content':'old question'},{'role':'assistant','content':'old value'},messages[-1]]
        injected=inject_memory(history)
        assert injected[:3]==history[:3]
        assert 'CURRENT-TURN' in injected[-2]['content'] and 'new value' in injected[-2]['content']
        assert injected[-1]==history[-1]
    finally: memory_context.reset(token)


def test_both_llm_entrypoints_inject_same_memory_once(monkeypatch):
    from types import SimpleNamespace
    from langchain_core.messages import AIMessage
    from asteria_researcher.utils import llm, tools
    from asteria_researcher.llm_provider.generic.base import GenericLLMProvider
    captured = []
    class Fake:
        llm = None
        def __init__(self): self.llm = self
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            captured.append([{'role':m.type, 'content':m.content} for m in messages])
            return AIMessage(content='{"ok":true}')
        async def get_chat_response(self, messages, *args, **kwargs):
            captured.append(messages)
            return '{"ok":true}'
    monkeypatch.setattr(llm, 'get_llm', lambda *a, **kw: Fake())
    monkeypatch.setattr(GenericLLMProvider, 'from_provider', lambda *a, **kw: Fake())
    async def exercise():
        token = memory_context.set({'files':[{'name':'PROJECT.md','content':'memory-boundary-marker'}]})
        messages = [{'role':'system','content':'Return JSON only'}, {'role':'user','content':'current task'}]
        try:
            await llm.create_chat_completion(messages, model='fake', llm_provider='fake')
            await tools.create_chat_completion_with_tools(messages, [], model='fake', llm_provider='fake')
        finally: memory_context.reset(token)
        assert len(messages)==2
        for sent in captured:
            assert len(sent)==3 and sent[0]['content']=='Return JSON only'
            assert sent[-1]['content']=='current task'
            assert sum('memory-boundary-marker' in m['content'] for m in sent)==1
    asyncio.run(exercise())


def test_research_worker_loads_owner_snapshot_and_resets_context(monkeypatch):
    from backend.runs import worker
    from backend.server import server_utils, agentic_runner
    expected = {'files':[{'name':'PROJECT.md','content':'worker-scoped'}]}
    async def snapshot(email, conversation, query, model):
        assert (email, conversation, query)==('owner','conversation','task')
        return expected
    async def handle(sink, command, manager, queue):
        assert memory_context.get()==expected
        async def child(): assert memory_context.get()==expected
        await asyncio.gather(child(),child())
        sink.paths={'md':'test-only'}
    class Sink:
        run={'user_email':'owner','conversation_id':'conversation'}
        error=None
        paths={}
        async def send_json(self, data):
            assert data=={'type':'memory_loaded','output':expected}
    monkeypatch.setattr(service,'snapshot',snapshot)
    monkeypatch.setattr(agentic_runner,'configured_model',lambda *a:None)
    monkeypatch.setattr(server_utils,'handle_start_command',handle)
    async def exercise():
        assert memory_context.get() is None
        await worker.research(Sink(),{'task':'task'})
        assert memory_context.get() is None
        async def fail(*a): raise RuntimeError('test-only')
        monkeypatch.setattr(server_utils,'handle_start_command',fail)
        with pytest.raises(RuntimeError): await worker.research(Sink(),{'task':'task'})
        assert memory_context.get() is None
    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv('ASTERIA_RUNS_DB_TESTS') != '1', reason='requires PostgreSQL')
def test_scopes_snapshot_topic_selection_and_delete(directory, monkeypatch):
    async def exercise():
        import asyncpg
        from dotenv import load_dotenv
        load_dotenv('.env')
        admin = await asyncpg.connect(os.environ['DATABASE_URL'])
        schema = 'test_memory_' + uuid4().hex
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], server_settings={'search_path':schema}, min_size=1, max_size=3)
        async def get_pool(): return pool
        monkeypatch.setattr(service, 'get_pool', get_pool)
        try:
            await pool.execute(Path('backend/auth/workspace_schema.sql').read_text())
            await pool.execute("INSERT INTO workspace_projects(id,user_email,name) VALUES('a','owner','A'),('b','owner','B'),('secret','other','Secret')")
            await pool.execute("INSERT INTO workspace_conversations(id,user_email,project_id,title) VALUES('c','owner','a','C'),('standalone','owner',NULL,'S')")
            await service.save('owner',None,'preferences.md','默认中文',None)
            await service.save('owner','a','PROJECT.md','项目A，固定seed23',None)
            await service.save('owner','a','memory/MEMORY.md','实验经验见 experiments.md',None)
            topic = await service.save('owner','a','memory/experiments.md','实验记录：训练211步，来源：实验日志A',None)
            await service.save('owner','b','PROJECT.md','项目B私有术语',None)
            with pytest.raises(HTTPException):
                await service.list_files('owner','secret')
            async def model(system,payload):
                assert json.loads(payload)['topics'][0]['name']=='memory/experiments.md'
                return '{"names":["memory/experiments.md"]}'
            snap = await service.snapshot('owner','c','实验多少步',model)
            assert len(snap['files']) == 4 and '211' in str(snap)
            assert '项目B' not in str(snap) and 'other' not in str(snap)
            assert len((await service.snapshot('owner','standalone','hello',model))['files'])==1
            assert await pool.fetchval("SELECT workspace_path FROM workspace_projects WHERE id='a'")
            removed = await service.remove('owner','a','memory/experiments.md',topic['version'])
            assert Path(removed['trash_path']).read_text()==topic['content']
            assert len((await service.snapshot('owner','c','hello',model))['files'])==3
            await pool.execute("UPDATE workspace_conversations SET project_id='b' WHERE id='c'")
            moved = await service.snapshot('owner','c','hello',model)
            assert '项目B' in str(moved) and 'seed23' not in str(moved)
            await pool.execute("UPDATE workspace_projects SET workspace_path='/untrusted/outside' WHERE id='b'")
            with pytest.raises(HTTPException) as denied:
                await service.save('owner','b','PROJECT.md','oops',None)
            assert denied.value.status_code==409
        finally:
            await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(exercise())
