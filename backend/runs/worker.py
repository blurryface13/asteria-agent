"""Run with dora: python -m backend.runs.worker (from repository root).

No browser references and no automatic replay after a lost process. The API
can restart independently while this worker continues its current research.
"""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import shutil
import sys
from uuid import uuid4

from backend.runs.store import RunStore

logger = logging.getLogger(__name__)


class DurableSink:
    def __init__(self, store, run, worker_id):
        self.store, self.run, self.worker_id = store, run, worker_id
        self.paths = {}
        self.error = None

    async def send_json(self, payload):
        if payload.get('type') == 'error':
            self.error = str(payload.get('output', 'Research failed'))
        if payload.get('type') == 'path':
            self.paths.update(payload.get('output') or {})
        await self.store.append(self.run['id'], self.worker_id, payload)

    async def request_feedback(self, question):
        approval = await self.store.ask(self.run['id'], self.worker_id, question)
        # Approval remains durable until answered or explicit cancellation.
        while True:
            answered, response = await self.store.response(self.run['id'], self.worker_id, approval)
            if answered:
                return response
            await asyncio.sleep(1)


def artifact_index(paths):
    root = Path('outputs').resolve()
    result = []
    for kind, value in paths.items():
        path = Path(value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Invalid artifact path for {kind}')
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        result.append({'kind': kind, 'path': str(path.relative_to(Path.cwd())), 'sha256': digest.hexdigest(), 'size_bytes': path.stat().st_size})
    return result


async def research(sink, request):
    from backend.server.server_utils import handle_start_command
    from backend.server.websocket_manager import WebSocketManager
    await handle_start_command(sink, 'start ' + json.dumps(request), WebSocketManager(), asyncio.Queue())
    if sink.error:
        raise RuntimeError(sink.error)
    if not sink.paths:
        raise RuntimeError('Research returned without deliverable artifacts')


async def execute(store, run, worker_id, execute_research=research):
    from asteria_researcher.utils.usage_context import usage_sink
    sink = DurableSink(store, run, worker_id)
    token = usage_sink.set(sink.send_json)
    async def work():
        await execute_research(sink, run['request'])
        # Hashing can take time; keep the lease alive through artifact indexing.
        return await asyncio.to_thread(artifact_index, sink.paths)
    task = asyncio.create_task(work())
    async def watch():
        while not task.done():
            state = await store.heartbeat(run['id'], worker_id)
            if state == 'cancel_requested':
                task.cancel()
                return
            await asyncio.sleep(2)
    monitor = asyncio.create_task(watch())
    state, error = 'completed', None
    artifacts = []
    try:
        done, _ = await asyncio.wait({task, monitor}, return_when=asyncio.FIRST_COMPLETED)
        if monitor in done:
            await monitor  # Lost lease/DB failure must stop execution, not go unnoticed.
        artifacts = await task
    except asyncio.CancelledError:
        state = 'cancelled'
    except Exception as exc:
        state, error = 'failed', f'{type(exc).__name__}: {exc}'
        logger.exception('Research job failed: %s', run['id'])
    finally:
        task.cancel()
        monitor.cancel()
        await asyncio.gather(task, monitor, return_exceptions=True)
        usage_sink.reset(token)
    try:
        await store.finish(run['id'], worker_id, state, error, artifacts)
    except Exception as exc:
        if state != 'completed':
            raise
        await store.finish(run['id'], worker_id, 'failed', f'Finalization failed: {exc}')


async def main():
    from backend.auth.schema_bootstrap import initialize_database
    from backend.auth.db import close_pool
    # Fail before claiming a paid research job, not at final publication.
    if not shutil.which('xelatex'):
        raise RuntimeError('xelatex is missing from worker PATH; configure the existing TeX installation before starting the worker')
    await initialize_database()
    store, worker_id = RunStore(), uuid4().hex
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    logger.info('Research worker ready: %s', worker_id)
    # Graceful shutdown drains the current job. Hard death expires its lease.
    try:
        while not stop.is_set():
            try:
                await store.reap()
                run = await store.claim(worker_id)
                if run:
                    await execute(store, run, worker_id)
                else:
                    try:
                        await asyncio.wait_for(stop.wait(), 1)
                    except asyncio.TimeoutError:
                        pass
            except Exception:
                logger.exception('Worker iteration failed; no job will be blindly retried')
                await asyncio.sleep(2)
    finally:
        await close_pool()


if __name__ == '__main__':
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    sys.path.insert(0, str(root / 'backend'))
    load_dotenv(root / '.env')
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
