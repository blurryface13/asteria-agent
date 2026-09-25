import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


spec = importlib.util.spec_from_file_location("research_acceptance", Path(__file__).parents[1] / "scripts/accept-research-chain.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


@pytest.mark.parametrize("bad_hash", [False, True])
def test_acceptance_requires_downloadable_matching_deliverables(bad_hash):
    bodies = {"md": b"# Report", "latex_pdf": b"%PDF-1.7 fixture",
              "citation_review": b'{"status":"completed"}', "lead_decisions": b'[{"tool":"finish"}]'}
    artifacts = [{"kind": k, "path": "outputs/test/" + k, "size_bytes": len(v),
                  "sha256": "invalid" if bad_hash else hashlib.sha256(v).hexdigest()} for k, v in bodies.items()]

    def handle(request):
        assert request.headers["Authorization"] == "Bearer test-only"
        return httpx.Response(200, content=bodies[request.url.path.rsplit("/", 1)[1]])

    async def run():
        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handle),
                                     headers={"Authorization": "Bearer test-only"}) as client:
            return await acceptance.verify_deliverables(client, {"artifacts": artifacts})

    if bad_hash:
        with pytest.raises(ValueError, match="differs"):
            asyncio.run(run())
    else:
        assert len(asyncio.run(run())) == 4


@pytest.mark.parametrize('has_matrix', [False, True])
def test_acceptance_can_enforce_requested_method_matrix(has_matrix):
    charts = ([{'id': 'method-map', 'kind': 'matrix'}] if has_matrix
              else [{'id': 'comparison-bar', 'kind': 'bar'}])
    bodies = {'md': b'# Report\n![map](figures/method-map.png)',
              'latex_pdf': b'%PDF-1.7 fixture',
              'citation_review': b'{"status":"completed"}',
              'lead_decisions': b'[]',
              'data_analysis': json.dumps({'charts': charts}).encode(),
              'chart_method-map': b'\x89PNGtest'}
    artifacts = [{'kind': kind, 'path': f'outputs/test/{kind}', 'size_bytes': len(body),
                  'sha256': hashlib.sha256(body).hexdigest()} for kind, body in bodies.items()]
    def handle(request):
        kind = request.url.path.rsplit('/', 1)[1]
        return httpx.Response(200, content=bodies[kind],
                              headers={'content-type': 'image/png' if kind.startswith('chart_') else 'application/octet-stream'})
    async def run():
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(handle)) as client:
            return await acceptance.verify_deliverables(client, {'artifacts': artifacts}, require_matrix=True)
    if has_matrix:
        assert len(asyncio.run(run())) == len(bodies)
    else:
        with pytest.raises(ValueError, match='comparison matrix'):
            asyncio.run(run())


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_routing_failure_saved_before_run_and_not_masked(tmp_path, monkeypatch, cleanup_failure):
    from backend.auth import lab, db

    async def noop(*args):
        pass

    monkeypatch.setattr(lab, "provision", noop)
    monkeypatch.setattr(db, "close_pool", noop)
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    original_client = httpx.AsyncClient
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "must-not-be-saved"})
        if request.url.path == "/api/workspace/conversations":
            return httpx.Response(200, json={"id": "test-conversation"})
        if request.url.path == "/api/coordinator/route":
            return httpx.Response(200, json={"status": "running"})
        if request.url.path == "/api/coordinator/turn":
            return httpx.Response(200, json={"turn": {"status": "failed", "error": "HTTP 402", "usage": {}}})
        if request.url.path == "/api/auth/logout":
            return httpx.Response(503 if cleanup_failure else 200, json={})
        raise AssertionError("Unexpected request: " + request.url.path)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original_client(
        **kw, transport=httpx.MockTransport(handle)))
    args = SimpleNamespace(url="http://test", task_file=None, direct_read=False, timeout=10, approve_plan=True)
    with pytest.raises(RuntimeError, match="HTTP 402"):
        asyncio.run(acceptance.run(args))
    folder = next((tmp_path / "outputs").iterdir())
    assert json.loads((folder / "routing.json").read_text())["status"] == "failed"
    failure = json.loads((folder / "failure.json").read_text())
    assert failure["stage"] == "routing" and failure["run_id"] is None
    assert (folder / "cleanup-errors.json").exists() == cleanup_failure
    assert calls.count("/api/coordinator/route") == 1
    assert calls[-1] == "/api/auth/logout"
    assert not any("must-not-be-saved" in file.read_text() for file in folder.iterdir())


@pytest.mark.parametrize('owner_matches', [True, False])
def test_resume_observes_same_run_without_submission_or_foreign_reset(tmp_path, monkeypatch, owner_matches):
    from backend.auth import lab, db
    folder = tmp_path / 'outputs' / 'acceptance_0123456789'
    folder.mkdir(parents=True)
    (folder / 'request.json').write_text(json.dumps({'conversation_id': 'existing'}))
    (folder / 'events.jsonl').write_text(json.dumps({'sequence': 4}) + '\n')
    resets, paths = [], []

    class Pool:
        async def fetchval(self, *args):
            return 'acceptance-0123456789@example.com' if owner_matches else 'real-user@example.com'

    async def pool():
        return Pool()

    async def provision(*args):
        resets.append(args[0])

    async def noop(*args, **kwargs):
        return []

    monkeypatch.setattr(db, 'get_pool', pool)
    monkeypatch.setattr(db, 'close_pool', noop)
    monkeypatch.setattr(lab, 'provision', provision)
    monkeypatch.setattr(acceptance, 'verify_deliverables', noop)
    monkeypatch.setattr(acceptance, 'ROOT', tmp_path)
    original_client = httpx.AsyncClient

    def handle(request):
        paths.append(request.url.path)
        if request.url.path == '/api/auth/login':
            return httpx.Response(200, json={'access_token': 'temporary-test-token'})
        if request.url.path == '/api/coordinator/turn':
            return httpx.Response(200, json={'turn': {'status': 'completed', 'result': {'run_id': 'original-run'}}})
        if request.url.path == '/api/workspace/runs/original-run':
            return httpx.Response(200, json={'status': 'completed', 'artifacts': []})
        if request.url.path.endswith('/events'):
            assert request.url.params['after'] == '4'
            return httpx.Response(200, json={'events': [{'sequence': 5, 'payload': {'type': 'run_state'}}]})
        if request.url.path == '/api/auth/logout':
            return httpx.Response(200, json={})
        raise AssertionError('Must not submit, create a conversation or cancel: ' + request.url.path)

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original_client(**kw, transport=httpx.MockTransport(handle)))
    args = SimpleNamespace(url='http://test', resume=str(folder), timeout=5, approve_plan=True)
    if not owner_matches:
        with pytest.raises(ValueError, match='non-acceptance'):
            asyncio.run(acceptance.run(args))
        assert not resets and not paths
    else:
        asyncio.run(acceptance.run(args))
        assert resets == ['acceptance-0123456789@example.com']
        assert [json.loads(line)['sequence'] for line in (folder / 'events.jsonl').read_text().splitlines()] == [4, 5]
        assert json.loads((folder / 'result.json').read_text())['status'] == 'completed'
