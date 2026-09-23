import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import HTTPException


def test_password_and_fail_closed(monkeypatch):
    from backend.auth import lab
    from backend.auth.dependencies import _local_auth_bypass_enabled
    password='a-real-test-password-123'
    first=lab.password_hash(password)
    assert first!=lab.password_hash(password) and lab.password_matches(password,first)
    assert not lab.password_matches('wrong-password-123',first)
    with pytest.raises(ValueError): lab.password_hash('short')
    monkeypatch.setenv('ASTERIA_SHARED_MODE','1');monkeypatch.setenv('ASTERIA_DEV_AUTH_BYPASS','1')
    assert not _local_auth_bypass_enabled()
    with pytest.raises(RuntimeError): asyncio.run(lab.check_shared_config())


def test_file_boundary_and_conflict(tmp_path,monkeypatch):
    from backend.files import service
    monkeypatch.setenv('ASTERIA_WORKSPACES_ROOT',str(tmp_path))
    for name in ('../secret.txt','/tmp/a.md','.env','a/b.py','x.exe'):
        with pytest.raises(HTTPException): service.read('owner',name)
    row={'id':'proposal1','path':'notes.md','operation':'write','content':'v1','expected_version':None}
    service.apply_file('owner',row)
    assert service.read('other','notes.md')['exists'] is False
    with pytest.raises(HTTPException): service.apply_file('owner',dict(row,content='overwrite'))
    old=service.read('owner','notes.md')
    service.apply_file('owner',dict(row,id='proposal2',operation='delete',expected_version=old['version']))
    assert not service.read('owner','notes.md')['exists']
    assert (service.directory('owner')/'.trash/proposal2-notes.md').read_text()=='v1'
    (service.directory('owner')/'link.md').symlink_to(tmp_path/'external')
    with pytest.raises(HTTPException): service.read('owner','link.md')


def test_specialists_contract_and_mcp_allowlist(monkeypatch):
    from backend.server import specialists
    from asteria_researcher.agentic.capabilities import PROFILES
    from asteria_researcher.agentic.skill_catalog import SkillSession
    for p in PROFILES.values(): assert SkillSession('assistance').load(p.skill_id)
    async def exercise():
        async def bad(*args): return json.dumps({'action':'tool','tool':'run_shell','query':'whoami'})
        with pytest.raises(ValueError): await specialists.run_specialist('financial_research','q',[],bad,'owner')
        responses=iter([{'action':'tool','tool':'search_public_sources','query':'official info'},
                        {'action':'answer','content':'检索暂不可用，无法确认当前日期。'}])
        async def model(*args): return json.dumps(next(responses))
        async def unavailable(*args): raise TimeoutError('sensitive provider detail')
        monkeypatch.setattr(specialists,'search_public_sources',unavailable)
        content,meta=await specialists.run_specialist('submission_consulting','q',[],model,'owner')
        assert meta['tool_calls'][0]['status']=='failed' and not meta['sources']
        assert 'sensitive' not in str(meta)
    asyncio.run(exercise())


def test_execution_slot_yields_during_approval():
    from backend.runs.worker import ExecutionSlot,DurableSink
    async def exercise():
        sem=asyncio.Semaphore(1);slot=ExecutionSlot(sem);await slot.acquire()
        class Store:
            async def ask(self,*args): return 'approval'
            async def response(self,*args):
                assert not sem.locked()
                return True,'approved'
        sink=DurableSink(Store(),{'id':'run'},'worker',slot)
        assert await sink.request_feedback('question')=='approved'
        assert sem.locked();slot.release();slot.release();assert sem._value==1
    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv('ASTERIA_RUNS_DB_TESTS')!='1',reason='real isolated PostgreSQL and Redis')
def test_accounts_scope_logout_quotas_and_proposals(monkeypatch,tmp_path):
    async def exercise():
        import asyncpg
        from dotenv import load_dotenv
        from backend.auth import db,lab,routes
        from backend.knowledge import managed,managed_routes
        from backend.files import service
        from backend.runs import store
        from backend.memory.working import recent
        from httpx import AsyncClient,ASGITransport
        from fastapi import FastAPI
        load_dotenv('.env')
        schema='test_lab_'+uuid4().hex
        monkeypatch.setenv('ASTERIA_REDIS_NAMESPACE',schema)
        monkeypatch.setenv('ASTERIA_ADMIN_EMAILS','admin@example.org')
        monkeypatch.setenv('ASTERIA_DEV_AUTH_BYPASS','0')
        monkeypatch.setenv('ASTERIA_SHARED_MODE','1')
        monkeypatch.setenv('ASTERIA_PUBLISH_PAPER_CORPUS','0')
        monkeypatch.setenv('ASTERIA_WORKSPACES_ROOT',str(tmp_path))
        admin=await asyncpg.connect(os.environ['DATABASE_URL'])
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool=await asyncpg.create_pool(os.environ['DATABASE_URL'],min_size=1,max_size=5,init=db._init_connection,server_settings={'search_path':schema})
        async def get_pool(): return pool
        for module in (lab,routes,managed,managed_routes,service,store): monkeypatch.setattr(module,'get_pool',get_pool)
        try:
            for file in ('backend/auth/schema.sql','backend/auth/workspace_schema.sql','backend/auth/reports_schema.sql','backend/runs/schema.sql','backend/knowledge/schema.sql','backend/files/schema.sql'):
                await pool.execute(Path(file).read_text())
            password='lab-test-password-123'
            await lab.provision('admin@example.org',password)
            app=FastAPI();app.include_router(routes.router);app.include_router(managed_routes.router)
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
                login=await client.post('/api/auth/login',json={'email':'admin@example.org','password':password})
                assert login.status_code==200
                admin_token=login.json()['access_token']
                assert 'HttpOnly' in login.headers['set-cookie']
                assert (await client.get('/api/auth/me')).json()['is_admin']
                assert (await client.post('/api/auth/accounts',json={'email':'member@example.org','password':password})).status_code==201
                public=await client.post('/api/knowledge/libraries',json={'name':'Shared','visibility':'lab'})
                private=await client.post('/api/knowledge/libraries',json={'name':'Private'})
                assert public.status_code==201
                p=public.json()['id'];private_id=private.json()['id']
                await client.post('/api/auth/logout')
                assert await lab.session_email(admin_token) is None
                assert (await client.get('/api/auth/me')).status_code==401
                await client.post('/api/auth/login',json={'email':'member@example.org','password':password})
                ids=[x['id'] for x in (await client.get('/api/knowledge/libraries')).json()['libraries']]
                assert p in ids and private_id not in ids
                assert (await client.get('/api/auth/accounts')).status_code==403
                assert (await client.patch('/api/knowledge/libraries/'+p,json={'name':'tamper','visibility':'lab'})).status_code==403
                token=client.cookies.get(lab.COOKIE)
                await lab.provision('member@example.org',password+'reset')
                assert await lab.session_email(token) is None
            # Cache ownership checked before cache hit; a second identity cannot read.
            for i in range(3):
                await pool.execute("INSERT INTO workspace_conversations(id,user_email,title) VALUES($1,'admin@example.org','test')",str(i))
            await pool.execute("INSERT INTO workspace_messages(id,conversation_id,role,content) VALUES('msg','0','user','private')")
            assert (await recent(pool,'admin@example.org','0'))[-1]['content']=='private'
            assert (await recent(pool,'admin@example.org','0'))[-1]['content']=='private'
            with pytest.raises(HTTPException): await recent(pool,'member@example.org','0')
            s=store.RunStore()
            for i in range(2): await s.submit('admin@example.org','request-'+str(i),str(i),{'task':'test'})
            with pytest.raises(HTTPException) as quota: await s.submit('admin@example.org','third','2',{'task':'test'})
            assert quota.value.status_code==429
            assert (await s.submit('admin@example.org','request-0','0',{'task':'test'}))['id']
            proposal=await service.propose('admin@example.org','hello.py','print(1)')
            assert not service.read('admin@example.org','hello.py')['exists']
            with pytest.raises(HTTPException): await service.resolve('member@example.org',proposal['id'],True)
            assert (await service.resolve('admin@example.org',proposal['id'],True))['state']=='applied'
            assert service.read('admin@example.org','hello.py')['content']=='print(1)'
            assert (await service.resolve('admin@example.org',proposal['id'],True))['state']=='applied'
        finally:
            async with lab.redis_connection() as redis:
                keys=[key async for key in redis.scan_iter(match=schema+':*')]
                if keys: await redis.delete(*keys)
            await pool.close();await admin.execute(f'DROP SCHEMA "{schema}" CASCADE');await admin.close()
    asyncio.run(exercise())
