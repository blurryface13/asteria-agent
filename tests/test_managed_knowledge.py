"""Publication and scope contracts in an isolated PostgreSQL schema."""
import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException


@pytest.mark.skipif(os.getenv('ASTERIA_RUNS_DB_TESTS') != '1', reason='requires local PostgreSQL')
def test_library_scope_versions_and_failed_update(monkeypatch):
    async def exercise():
        import asyncpg
        from dotenv import load_dotenv
        from backend.knowledge import managed, managed_routes
        load_dotenv('.env')
        schema = 'test_knowledge_' + uuid4().hex
        admin = await asyncpg.connect(os.environ['DATABASE_URL'])
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=3, server_settings={'search_path': schema})
        async def get_pool(): return pool
        monkeypatch.setattr(managed, 'get_pool', get_pool)
        monkeypatch.setattr(managed_routes, 'get_pool', get_pool)
        class Collection:
            def delete(self, **kwargs): pass
        monkeypatch.setattr(managed, 'collection', lambda _: Collection())
        def index(job):
            if job['payload'] == b'broken': raise ValueError('no extractable content')
            return [{'id':job['id']+'_0','content':bytes(job['payload']).decode(),'page':1}]
        monkeypatch.setattr(managed, 'index_payload', index)
        task = None
        try:
            await pool.execute(Path('backend/knowledge/schema.sql').read_text())
            await pool.execute("INSERT INTO knowledge_bases(id,owner,name) VALUES('a','owner','A'),('b','other','B')")
            with pytest.raises(HTTPException) as denied:
                await managed.upload('other','a','test.md',b'private')
            assert denied.value.status_code == 404
            assert [k['id'] for k in await managed.libraries('owner')] == ['a']
            first = await managed.upload('owner','a','test.md',b'v1')
            assert (await managed.upload('owner','a','test.md',b'v1'))['unchanged']
            with pytest.raises(HTTPException) as conflict:
                await managed.upload('owner','a','test.md',b'v2')
            assert conflict.value.status_code == 409
            task = asyncio.create_task(managed.index_loop())
            async def terminal(version):
                for _ in range(80):
                    state = await pool.fetchval('SELECT status FROM knowledge_versions WHERE id=$1',version)
                    if state in {'ready','failed'}: return state
                    await asyncio.sleep(.05)
                raise AssertionError('indexer did not publish')
            assert await terminal(first['version_id']) == 'ready'
            assert (await managed.upload('owner','a','test.md',b'v1'))['unchanged']
            failed = await managed.upload('owner','a','test.md',b'broken')
            assert await terminal(failed['version_id']) == 'failed'
            doc = (await managed.documents('owner','a'))[0]
            assert doc['active_version'] == first['version_id'] and doc['status'] == 'failed'
            second = await managed.upload('owner','a','test.md',b'v2')
            assert second['document_id'] == first['document_id']
            assert await terminal(second['version_id']) == 'ready'
            assert (await managed.documents('owner','a'))[0]['active_version'] == second['version_id']
            with pytest.raises(HTTPException):
                await managed_routes.source('a',first['document_id'],email='other')
            assert (await managed_routes.source('a',first['document_id'],email='owner')).body == b'v2'
            # Import must check both the library and the report owner, and use
            # the same versioned ingestion path as a file upload.
            await pool.execute('CREATE TABLE reports(id text PRIMARY KEY,user_email text,answer text)')
            await pool.execute("INSERT INTO reports VALUES('report-a','owner','report evidence'),('report-b','other','private evidence')")
            with pytest.raises(HTTPException) as denied_report:
                await managed_routes.import_report('a', managed_routes.ReportImport(conversation_id='report-b'), email='owner')
            assert denied_report.value.status_code == 404
            imported = await managed_routes.import_report('a', managed_routes.ReportImport(conversation_id='report-a'), email='owner')
            assert await terminal(imported['version_id']) == 'ready'
            assert (await managed_routes.source('a', imported['document_id'], email='owner')).body == b'report evidence'
            await managed_routes.delete_document('a', imported['document_id'], email='owner')
            await managed_routes.delete_document('a',first['document_id'],email='owner')
            assert await managed.documents('owner','a') == []
            assert await pool.fetchval('SELECT count(*) FROM knowledge_chunks') == 0
            assert await managed.retrieve('owner',['a'],'question') == []
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(exercise())


def test_legacy_routes_cannot_address_managed_collections():
    from pydantic import ValidationError
    from backend.knowledge.routes import AskRequest, TraceRequest, ModularIngestRequest
    for model, fields in ((AskRequest, {'question':'valid question'}), (TraceRequest, {'query':'valid query'}), (ModularIngestRequest, {'path':'/tmp/file.md'})):
        assert model(**fields, collection='research_papers').collection == 'research_papers'
        with pytest.raises(ValidationError) as error:
            model(**fields,collection='asteria_private')
        assert any(item['loc'] == ('collection',) for item in error.value.errors())
