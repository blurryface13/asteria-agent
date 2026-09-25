"""Offline contracts for role credentials and cross-domain report routing."""
import asyncio
import sys
from types import SimpleNamespace

import pytest

from asteria_researcher.agentic.agent_orchestrator import AgentOrchestrator, Request
from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.intent import Intent
from asteria_researcher.agentic.primary_sources import source_type, validate_url
from asteria_researcher.agentic.library import PaperLibrary
from backend.server.financial_sources import search_financial_sources
from asteria_researcher.agentic.skill_catalog import SkillSession
from backend.model_settings import service
from backend.model_settings import routes as model_routes
from backend.runs.routes import validate_request


def test_financial_report_routes_to_durable_lead_but_short_question_stays_specialist():
    async def run():
        calls = []
        async def lead(req, intent):
            calls.append(('lead', intent.capability))
            return {'run_id': 'report-run'}
        async def specialist(req, intent):
            calls.append(('specialist', intent.capability))
            return {'response': {'content': '市盈率是价格与每股收益的比值'}}
        entry = AgentOrchestrator(None, {'research_lead': lead, 'financial_research': specialist})
        intent = Intent(capability='financial_research', reason='finance', report_requested=True)
        base = dict(message='分析一家公司的财报', user_id='u', conv_id='c', request_id='r', intent=intent)
        report = await entry.run(Request(**base, research_request={'task': base['message']}))
        brief = await entry.run(Request(**{**base, 'message': '解释市盈率',
                                          'intent': Intent(capability='financial_research',
                                                           reason='definition', report_requested=False)},
                                        research_request={'report_type': 'research_report'}))
        assert report['run_id'] == 'report-run'
        assert report['routing_decision']['primary_agent'] == 'research_lead'
        assert brief['routing_decision']['primary_agent'] == 'financial_research'
        assert calls == [('lead', 'financial_research'), ('specialist', 'financial_research')]
    asyncio.run(run())


def test_financial_report_uses_existing_research_contract_and_official_sources(tmp_path):
    validate_request({'task': '财报调研', 'report_type': 'research_report',
                      'headers': {'retrievers': ''}, 'coordinator_capability': 'financial_research'})
    assert source_type('https://www.sec.gov/Archives/edgar/data/1/report.htm') == 'financial_primary'
    assert source_type('https://www.federalreserve.gov/newsevents.htm') == 'financial_primary'
    with pytest.raises(ValueError):
        validate_url('https://127.0.0.1/secrets')
    with pytest.raises(ValueError):
        validate_url('http://www.sec.gov/Archives/edgar/data/1/report.htm')
    with pytest.raises(ValueError):
        validate_url('https://s201.q4cdn.com/another-company/file.pdf')
    async def model(*args): return '{}'
    async def emit(*args): pass
    async def approve(*args): return '确认'
    runtime = AutonomousReview(model, None, emit, approve, root=tmp_path,
                               online_rag=False, capability='financial_research')
    assert runtime.research_skill == 'finance_assistance'
    assert runtime.format_profile == 'brief'
    assert SkillSession('research').load('anthropic_sector_overview')['source'].startswith('anthropics/')


def test_financial_discovery_filters_news_and_reader_registers_official_link(monkeypatch, tmp_path):
    class FakeDDGS:
        def text(self, query, max_results):
            return [
                {'href': 'https://en.wikipedia.org/wiki/Nvidia', 'title': 'Nvidia', 'body': 'summary'},
                {'href': 'https://investor.nvidia.com/financial-info/annual-reports-and-proxies/default.aspx',
                 'title': 'NVIDIA annual reports', 'body': 'official'},
            ]
    monkeypatch.setitem(sys.modules, 'ddgs', SimpleNamespace(DDGS=FakeDDGS))
    async def run():
        rows = await search_financial_sources('NVIDIA annual report')
        assert len(rows) == 1 and rows[0]['url'].startswith('https://investor.nvidia.com/')
        from asteria_researcher.agentic import library
        async def fake_read(url, consume_bytes):
            return {'url': url, 'text': 'Annual reports', 'pages': [{'page': 1, 'text': 'Annual reports'}],
                    'bytes': 100, 'linked_sources': [{
                        'url': 'https://s201.q4cdn.com/141608511/files/doc_financials/2026/ar/report.pdf',
                        'title': '2026 Annual Report', 'linked_from': url}]}
        monkeypatch.setattr(library, 'read_paper', fake_read)
        source = PaperLibrary(tmp_path, None, None)
        source.add(rows[0])
        detail = await source.read(rows[0]['url'])
        assert detail['linked_sources'][0]['title'] == '2026 Annual Report'
        assert len(source.nodes) == 2
        assert next(iter(source.edges.values()))['relation'] == 'official_portal_links_to'
    asyncio.run(run())


class FakePool:
    def __init__(self): self.rows = {}

    async def execute(self, query, role, model, encrypted, tail, clear):
        current = self.rows.get(role, {})
        self.rows[role] = {'role': role, 'model': model,
            'encrypted_key': None if clear else encrypted or current.get('encrypted_key'),
            'key_tail': None if clear else tail or current.get('key_tail'), 'updated_at': None}

    async def fetchrow(self, query, role): return self.rows.get(role)

    async def fetch(self, query): return list(self.rows.values())


def test_role_keys_are_encrypted_not_echoed_and_can_be_cleared(monkeypatch):
    async def run():
        pool = FakePool()
        async def get_pool(): return pool
        monkeypatch.setattr(service, 'get_pool', get_pool)
        monkeypatch.setenv('ASTERIA_MODEL_SETTINGS_SECRET', 'stable-test-secret-with-at-least-32-characters')
        await service.save('writer', 'deepseek-reasoner', 'sk-test-private-key')
        assert 'sk-test-private-key' not in str(pool.rows)
        assert await service.resolve('writer', 'default') == ('deepseek-reasoner', 'sk-test-private-key')
        listing = await service.listing()
        writer = next(row for row in listing if row['role'] == 'writer')
        assert writer['has_key'] and writer['key_tail'] == '-key'
        assert 'encrypted_key' not in writer
        await service.save('writer', 'deepseek-chat', clear_key=True)
        assert await service.resolve('writer', 'default') == ('deepseek-chat', None)
        with pytest.raises(ValueError):
            await service.save('unknown-role', 'deepseek-chat', 'private-key')
    asyncio.run(run())


def test_first_boot_can_set_one_key_for_all_roles_atomically(monkeypatch):
    class BulkPool(FakePool):
        async def execute(self, query, roles, model, encrypted, tail):
            assert 'unnest($1::text[])' in query
            for role in roles:
                self.rows[role] = {'role': role, 'model': model,
                    'encrypted_key': encrypted, 'key_tail': tail, 'updated_at': None}

    async def run():
        pool = BulkPool()
        async def get_pool(): return pool
        monkeypatch.setattr(service, 'get_pool', get_pool)
        monkeypatch.setenv('ASTERIA_MODEL_SETTINGS_SECRET', 'stable-test-secret-with-at-least-32-characters')
        await service.save_all('deepseek-chat', 'sk-test-shared-key')
        assert len(pool.rows) == len(service.ROLES)
        assert 'sk-test-shared-key' not in str(pool.rows)
        assert all([(await service.resolve(role, 'default')) == ('deepseek-chat', 'sk-test-shared-key')
                    for role in service.ROLES])
        with pytest.raises(ValueError):
            await service.save_all('deepseek-chat', 'short')
    asyncio.run(run())


def test_model_settings_endpoint_requires_admin_and_never_returns_secret(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.auth.dependencies import get_current_user_email, require_admin
    app = FastAPI()
    app.include_router(model_routes.router)
    app.dependency_overrides[get_current_user_email] = lambda: 'member@example.test'
    with TestClient(app) as client:
        assert client.get('/api/admin/agent-models').status_code == 403
        assert client.put('/api/admin/agent-models/bulk', json={
            'model': 'deepseek-chat', 'api_key': 'sk-test-shared-key'}).status_code == 403
    app.dependency_overrides[require_admin] = lambda: 'admin@example.test'
    async def fake_listing():
        return [{'role': 'writer', 'model': 'deepseek-chat', 'has_key': True, 'key_tail': '1234'}]
    monkeypatch.setattr(model_routes, 'listing', fake_listing)
    async def fake_save_all(model, key):
        assert (model, key) == ('deepseek-chat', 'sk-test-shared-key')
    monkeypatch.setattr(model_routes, 'save_all', fake_save_all)
    with TestClient(app) as client:
        response = client.get('/api/admin/agent-models')
        assert response.status_code == 200
        assert 'encrypted_key' not in response.text
        assert 'api_key' not in response.text
        bulk = client.put('/api/admin/agent-models/bulk', json={
            'model': 'deepseek-chat', 'api_key': 'sk-test-shared-key'})
        assert bulk.status_code == 200
        assert 'sk-test-shared-key' not in bulk.text


def test_model_selection_is_role_scoped_and_frozen_for_a_task(monkeypatch):
    from asteria_researcher.config import config as config_module
    from asteria_researcher.utils import llm as llm_module
    from asteria_researcher.utils.usage_context import track_usage_stage

    class FakeConfig:
        smart_llm_model = 'deepseek-chat'
        smart_llm_provider = 'deepseek'
        llm_kwargs = {}
        embedding_provider = 'ollama'
        embedding_model = 'bge-m3'
        embedding_kwargs = {}

        def __init__(self, path=None): pass

    calls, snapshots = [], []

    async def fake_completion(**kwargs):
        calls.append((kwargs['model'], kwargs['llm_kwargs'].get('openai_api_key')))
        return 'ok'

    async def fake_snapshot():
        snapshots.append(True)
        return {'research_lead': ('deepseek-reasoner', 'lead-secret'),
                'writer': ('deepseek-chat', 'writer-secret')}

    monkeypatch.setattr(config_module, 'Config', FakeConfig)
    monkeypatch.setattr(llm_module, 'create_chat_completion', fake_completion)
    monkeypatch.setattr(service, 'snapshot', fake_snapshot)
    from backend.server.agentic_runner import configured_model
    async def run():
        model = configured_model()
        with track_usage_stage('research_lead'):
            await model('system', 'user')
        with track_usage_stage('writer'):
            await model('system', 'user')
        with track_usage_stage('intent_router'):
            await model('system', 'user')
        assert calls == [('deepseek-reasoner', 'lead-secret'),
                         ('deepseek-chat', 'writer-secret'), ('deepseek-chat', None)]
        assert len(snapshots) == 1
    asyncio.run(run())
