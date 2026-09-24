"""A failed run retains diagnostics but must never become a successful report."""
import asyncio

from backend.runs.worker import execute


def test_worker_indexes_diagnostics_on_model_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "outputs" / "review_fixture"
    folder.mkdir(parents=True)
    draft = folder / "draft-1.md"
    draft.write_text("未通过最终引文处理的草稿")

    class Store:
        def __init__(self):
            self.events, self.result = [], None

        async def append(self, run, worker, payload):
            self.events.append(payload)

        async def heartbeat(self, run, worker):
            return "running"

        async def finish(self, run, worker, state, error=None, artifacts=None):
            self.result = state, error, artifacts

    async def research(sink, request):
        await sink.send_json({"type": "diagnostic_paths", "output": {"diagnostic_draft": str(draft)}})
        raise RuntimeError("HTTP 402")

    store = Store()
    asyncio.run(execute(store, {"id": "test-run", "request": {}}, "test-worker", research))
    state, error, artifacts = store.result
    assert state == "failed" and "402" in error
    assert artifacts[0]["kind"] == "diagnostic_draft"
    assert artifacts[0]["size_bytes"] == draft.stat().st_size
    assert len(artifacts[0]["sha256"]) == 64
    assert not any(e.get("type") == "report" for e in store.events)
