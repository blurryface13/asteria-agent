"""Deletion contracts in a disposable PostgreSQL schema, never user records."""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest


def test_workspace_deletion_preserves_children_and_blocks_active_work(monkeypatch):
    async def exercise():
        import asyncpg
        from dotenv import load_dotenv
        from backend.auth import workspace_store_pg as module
        load_dotenv()
        schema = 'test_workspace_delete_' + uuid4().hex
        admin = await asyncpg.connect(os.environ['DATABASE_URL'])
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = None
        try:
            async def init(conn):
                await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
            pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=2, init=init, server_settings={'search_path': schema})
            async def get_pool():
                return pool
            monkeypatch.setattr(module, 'get_pool', get_pool)
            async with pool.acquire() as conn:
                for path in ('backend/auth/workspace_schema.sql', 'backend/auth/reports_schema.sql', 'backend/runs/schema.sql'):
                    await conn.execute(Path(path).read_text())
            store = module.PgWorkspaceStore()
            project = await store.create_project('owner', 'test', None, {})
            convo = await store.create_conversation('owner', 'test', 'chat', {}, project['id'])
            cid = convo['id']
            with pytest.raises(module.WorkspaceNotFound):
                await store.delete_project(project['id'], 'other')
            await store.delete_project(project['id'], 'owner')
            assert (await store.get_conversation(cid, 'owner'))['project_id'] is None
            with pytest.raises(module.WorkspaceNotFound):
                await store.delete_conversation(cid, 'other')
            async with pool.acquire() as conn:
                await conn.execute("INSERT INTO coordinator_turns(conversation_id,request_id,request_hash,status) VALUES($1,'t','h','running')", cid)
            with pytest.raises(module.WorkspaceBusy):
                await store.delete_conversation(cid, 'owner')
            async with pool.acquire() as conn:
                await conn.execute("UPDATE coordinator_turns SET status='completed' WHERE conversation_id=$1", cid)
                await conn.execute("INSERT INTO research_runs(id,user_email,conversation_id,request_key,request_hash,request,status) VALUES('run','owner',$1,'key','hash','{}','running')", cid)
            with pytest.raises(module.WorkspaceBusy):
                await store.delete_conversation(cid, 'owner')
            async with pool.acquire() as conn:
                await conn.execute("UPDATE research_runs SET status='completed' WHERE id='run'")
                await conn.execute("INSERT INTO reports(id,user_email,question,answer,timestamp) VALUES($1,'owner','q','a',0)",cid)
                await conn.execute("INSERT INTO research_events(run_id,sequence,payload) VALUES('run',1,'{}')")
            await store.delete_conversation(cid, 'owner')
            with pytest.raises(module.WorkspaceNotFound):
                await store.get_conversation(cid, 'owner')
            async with pool.acquire() as conn:
                for table in ('reports', 'coordinator_turns', 'research_runs', 'research_events'):
                    assert await conn.fetchval(f'SELECT COUNT(*) FROM {table}') == 0
        finally:
            if pool:
                await pool.close()
            # Only this test's generated, isolated schema is disposable.
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(exercise())
