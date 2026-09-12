"""Real PostgreSQL contract tests in a disposable isolated schema.

Enable with ASTERIA_RUNS_DB_TESTS=1. No model calls, production tables or data.
"""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException


def test_durable_lifecycle(monkeypatch):
    asyncio.run(durable_lifecycle(monkeypatch))


async def durable_lifecycle(monkeypatch):
    if os.environ.get('ASTERIA_RUNS_DB_TESTS') != '1':
        pytest.skip('Opt in to isolated local PostgreSQL contract tests')
    import asyncpg
    from dotenv import load_dotenv
    import backend.runs.store as module
    from backend.runs.worker import execute
    load_dotenv()
    schema = 'test_runs_' + uuid4().hex
    admin = await asyncpg.connect(os.environ['DATABASE_URL'])
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    async def init(c):
        await c.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=5, init=init, server_settings={'search_path': schema})
    async def get_pool():
        return pool
    monkeypatch.setattr(module, 'get_pool', get_pool)
    try:
        async with pool.acquire() as c:
            for file in ('backend/auth/workspace_schema.sql', 'backend/auth/reports_schema.sql', 'backend/runs/schema.sql'):
                await c.execute(Path(file).read_text())
            for id in ('c1','c2','c3','c4','c5'):
                await c.execute("INSERT INTO workspace_conversations(id,user_email,title) VALUES($1,'test-owner','test')", id)
        store = module.RunStore()
        body = {'task': 'Contract test, not research', 'report_type': 'research_report'}
        results = await asyncio.gather(*[store.submit('test-owner', 'same-request', 'c1', body) for _ in range(5)])
        assert len({r['id'] for r in results}) == 1
        run_id = results[0]['id']
        with pytest.raises(HTTPException) as e:
            await store.get('other-user', run_id)
        assert e.value.status_code == 404
        with pytest.raises(HTTPException):
            await store.submit('test-owner', 'same-request', 'c1', {**body,'task':'different'})
        with pytest.raises(HTTPException):
            await store.submit('test-owner', 'new-request', 'c1', body)
        claims = await asyncio.gather(store.claim('worker-1'), store.claim('worker-2'))
        claimed = [r for r in claims if r]
        assert len(claimed) == 1
        worker = 'worker-1' if claims[0] else 'worker-2'
        approval = await store.ask(run_id, worker, 'Confirm test plan')
        assert (await store.get('test-owner', run_id))['status'] == 'waiting_approval'
        with pytest.raises(HTTPException):
            await store.answer('other-user', run_id, approval, None)
        await store.answer('test-owner', run_id, approval, None)
        await store.answer('test-owner', run_id, approval, None)
        assert await store.response(run_id, worker, approval) == (True, None)
        with pytest.raises(HTTPException):
            await store.answer('test-owner', run_id, approval, 'different')
        await asyncio.gather(*[store.append(run_id, worker, {'type':'logs','output':str(i)}) for i in range(20)])
        events = await store.events('test-owner', run_id)
        assert [r['sequence'] for r in events] == list(range(1, len(events)+1))
        cursor = events[-1]['sequence']
        await store.append(run_id, worker, {'type':'report','output':'Verified fixture report'})
        await store.finish(run_id, worker, 'completed')
        assert len(await store.events('test-owner', run_id, cursor)) == 2
        async with pool.acquire() as c:
            assert await c.fetchval("SELECT answer FROM reports WHERE id='c1'") == 'Verified fixture report'
        with pytest.raises(RuntimeError):
            await store.append(run_id, worker, {'type':'logs','output':'stale'})
        # Cancel before a worker can claim; cancellation is idempotent.
        queued = await store.submit('test-owner','queue-cancel','c2',body)
        await store.cancel('test-owner', queued['id'])
        await store.cancel('test-owner', queued['id'])
        assert await store.claim('worker-3') is None
        # Hard death: a new worker interrupts, but never reclaims executing work.
        lost = await store.submit('test-owner','lost-worker','c3',body)
        await store.claim('dead-worker')
        async with pool.acquire() as c:
            await c.execute("UPDATE research_jobs SET lease_until=now()-interval '1 second' WHERE run_id=$1", lost['id'])
        with pytest.raises(RuntimeError):
            await store.append(lost['id'], 'dead-worker', {'type':'report','output':'stale'})
        assert await store.reap() == 1
        assert (await store.get('test-owner', lost['id']))['status'] == 'interrupted'
        assert await store.claim('new-worker') is None
        # Worker cancellation tears down the coroutine before confirming cancelled.
        cancelled = await store.submit('test-owner','active-cancel','c4',body)
        active = await store.claim('cancel-worker')
        started = asyncio.Event()
        stopped = asyncio.Event()
        async def slow(sink, request):
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                stopped.set()
        execution = asyncio.create_task(execute(store, active, 'cancel-worker', slow))
        await started.wait()
        await store.cancel('test-owner', cancelled['id'])
        await asyncio.wait_for(execution, 5)
        assert stopped.is_set()
        assert (await store.get('test-owner', cancelled['id']))['status'] == 'cancelled'
        # Finishing without a report is failed, never a green empty result.
        empty = await store.submit('test-owner','empty-report','c5',body)
        active = await store.claim('empty-worker')
        async def empty_result(sink, request):
            pass
        await execute(store, active, 'empty-worker', empty_result)
        assert (await store.get('test-owner', empty['id']))['status'] == 'failed'
        import backend.auth.workspace_store_pg as workspace
        monkeypatch.setattr(workspace, 'get_pool', get_pool)
        deletion = workspace.PgWorkspaceStore()
        busy = await store.submit('test-owner', 'delete-busy', 'c5', body)
        with pytest.raises(workspace.WorkspaceBusy):
            await deletion.delete_conversation('c5', 'test-owner')
        await store.cancel('test-owner', busy['id'])
        await deletion.delete_conversation('c5', 'test-owner')
        async with pool.acquire() as c:
            assert not await c.fetchval("SELECT EXISTS(SELECT 1 FROM research_runs WHERE conversation_id='c5')")
    finally:
        await pool.close()
        # This schema was created above, contains only this test's disposable data.
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


def test_request_does_not_store_credentials():
    from backend.runs.routes import validate_request
    body = {'task':'test','report_type':'research_report'}
    assert validate_request(body) == body
    with pytest.raises(HTTPException):
        validate_request({**body, 'headers': {'Authorization':'secret'}})
    with pytest.raises(HTTPException):
        validate_request({**body, 'mcp_configs':[{'env':{'KEY':'secret'}}]})
    for invalid in ({'headers': None}, {'headers': {'retrievers': {}}}, {'source_urls': 'not-a-list'}):
        with pytest.raises(HTTPException) as error:
            validate_request({**body, **invalid})
        assert error.value.status_code == 422


def test_usage_context_parallel():
    asyncio.run(usage_context_parallel())


async def usage_context_parallel():
    from asteria_researcher.utils.usage_context import usage_sink, record_usage
    events = []
    async def collect(value):
        events.append(value)
    token = usage_sink.set(collect)
    try:
        await asyncio.gather(*[record_usage('test','test',1,{'input_tokens':i}) for i in (1,2,3)])
    finally:
        usage_sink.reset(token)
    assert len(events) == 3
    await record_usage('test','test',1,None)
    assert len(events) == 3
