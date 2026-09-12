"""Rename/move contracts; isolated PostgreSQL schema, no user data."""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_management_request_validation():
    from backend.auth.workspace_models import ConversationMoveRequest, ConversationUpdateRequest, ProjectUpdateRequest
    for model, field in [(ConversationUpdateRequest, 'title'), (ProjectUpdateRequest, 'name')]:
        with pytest.raises(ValidationError):
            model(**{field: '   '})
        assert getattr(model(**{field: '  New  '}), field) == 'New'
    with pytest.raises(ValidationError):
        ConversationMoveRequest()
    assert ConversationMoveRequest(project_id=None).project_id is None


def test_rename_move_preserve_content_and_enforce_ownership(monkeypatch):
    async def exercise():
        import asyncpg
        from dotenv import load_dotenv
        from backend.auth import workspace_store_pg as module
        load_dotenv('.env')
        schema = 'test_workspace_move_' + uuid4().hex
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
            a = await store.create_project('owner', 'A', '/unchanged', {'key': 'keep'})
            b = await store.create_project('owner', 'B', None, {})
            foreign = await store.create_project('other', 'Other', None, {})
            convo = await store.create_conversation('owner', 'Before', 'chat', {'keep': True}, a['id'])
            cid = convo['id']
            await store.append_message(cid, 'owner', 'user', 'original prompt', {})
            renamed = await store.update_project(a['id'], 'owner', 'Renamed', None, None)
            assert renamed['workspace_path'] == '/unchanged' and renamed['settings'] == {'key': 'keep'}
            with pytest.raises(module.WorkspaceNotFound):
                await store.rename_conversation(cid, 'other', 'denied')
            await store.rename_conversation(cid, 'owner', 'After')
            with pytest.raises(module.WorkspaceNotFound):
                await store.move_conversation(cid, 'other', None)
            with pytest.raises(module.WorkspaceNotFound):
                await store.move_conversation(cid, 'owner', foreign['id'])
            async with pool.acquire() as conn:
                await conn.execute("INSERT INTO coordinator_turns(conversation_id,request_id,request_hash,status) VALUES($1,'t','h','running')", cid)
            with pytest.raises(module.WorkspaceBusy):
                await store.move_conversation(cid, 'owner', b['id'])
            async with pool.acquire() as conn:
                await conn.execute("UPDATE coordinator_turns SET status='completed'")
                await conn.execute("INSERT INTO research_runs(id,user_email,conversation_id,request_key,request_hash,request,status) VALUES('run','owner',$1,'key','hash','{}','running')", cid)
            with pytest.raises(module.WorkspaceBusy):
                await store.move_conversation(cid, 'owner', b['id'])
            async with pool.acquire() as conn:
                await conn.execute("UPDATE research_runs SET status='completed'")
                await conn.execute("INSERT INTO reports(id,user_email,question,answer,timestamp) VALUES($1,'owner','original prompt','report',0)",cid)
                await conn.execute("INSERT INTO research_events(run_id,sequence,payload) VALUES('run',1,'{}')")
            for target in (b['id'], None, a['id']):
                moved = await store.move_conversation(cid, 'owner', target)
                assert moved['project_id'] == target and moved['title'] == 'After'
                assert moved['id'] == cid and moved['metadata'] == {'keep': True}
                assert (await store.list_messages(cid, 'owner'))[0]['content'] == 'original prompt'
            async with pool.acquire() as conn:
                assert await conn.fetchval('SELECT answer FROM reports WHERE id=$1', cid) == 'report'
                assert await conn.fetchval('SELECT count(*) FROM research_events') == 1
                assert await conn.fetchval('SELECT conversation_id FROM research_runs') == cid
        finally:
            if pool:
                await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(exercise())
