import asyncio
import json

from asteria_researcher.agentic.delivery_state import record_delivery


def test_publication_status_is_not_user_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTERIA_RUNTIME_REVISION', 'test-revision')
    record_delivery(tmp_path, 'publishing')
    path = record_delivery(tmp_path, 'failed', error_type='CompileError')
    value = json.loads(path.read_text())
    assert value['status'] == 'failed'
    assert value['scope'] == 'artifact_generation'
    assert value['authoritative_task_status'] == 'research_runs.status'
    assert value['runtime']['revision'] == 'test-revision'
    assert not (tmp_path/'delivery-state.tmp').exists()


def test_research_completion_does_not_claim_pdf_delivered(tmp_path):
    from asteria_researcher.agentic.autonomous import AutonomousReview
    async def emit(*args): pass
    async def completed(): return 'final cited report'
    runtime = AutonomousReview(None, None, emit, None, tmp_path, online_rag=False)
    runtime.folder.mkdir(parents=True, exist_ok=True)
    runtime._run = completed
    assert asyncio.run(runtime.run('task')) == 'final cited report'
    state = json.loads((runtime.folder/'run.json').read_text())
    assert state['status'] == 'research_completed'
    assert state['status_scope'] == 'research_and_citation_only'
