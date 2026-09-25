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
    def __init__(self, store, run, worker_id, slot=None):
        self.store, self.run, self.worker_id = store, run, worker_id
        self.slot=slot
        self.paths = {}
        self.error = None

    async def send_json(self, payload):
        if payload.get('type') == 'error':
            self.error = str(payload.get('output', 'Research failed'))
        if payload.get('type') in {'path', 'diagnostic_paths'}:
            self.paths.update(payload.get('output') or {})
        await self.store.append(self.run['id'], self.worker_id, payload)

    async def request_feedback(self, question):
        approval = await self.store.ask(self.run['id'], self.worker_id, question)
        if self.slot:
            self.slot.release()
        async def wait():
            while True:
                answered, response = await self.store.response(self.run['id'], self.worker_id, approval)
                if answered:
                    return response
                await asyncio.sleep(1)
        response=await asyncio.wait_for(wait(),float(os.getenv('ASTERIA_APPROVAL_TIMEOUT_SECONDS','3600')))
        if self.slot:
            await self.slot.acquire()
        return response


class ExecutionSlot:
    """One running compute slot, temporarily yielded while waiting for a human."""
    def __init__(self,semaphore):
        self.semaphore,self.held=semaphore,False

    async def acquire(self):
        if not self.held:
            await self.semaphore.acquire()
            self.held=True

    def release(self):
        if self.held:
            self.held=False
            self.semaphore.release()


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
    from backend.memory.service import snapshot
    from backend.server.agentic_runner import configured_model
    from asteria_researcher.utils.memory_context import memory_context
    memory = await snapshot(sink.run['user_email'], sink.run['conversation_id'], request['task'], configured_model(os.getenv('CONFIG_PATH')))
    token = memory_context.set(memory)
    try:
        await sink.send_json({'type': 'memory_loaded', 'output': memory})
        await handle_start_command(sink, 'start ' + json.dumps(request), WebSocketManager(), asyncio.Queue())
    finally:
        memory_context.reset(token)
    if sink.error:
        raise RuntimeError(sink.error)
    if not sink.paths:
        raise RuntimeError('Research returned without deliverable artifacts')


async def execute(store, run, worker_id, execute_research=research, slot=None):
    from asteria_researcher.utils.usage_context import usage_sink
    sink = DurableSink(store, run, worker_id,slot)
    token = usage_sink.set(sink.send_json)
    async def work():
        from asteria_researcher.agentic.delivery_state import runtime_identity
        await sink.send_json({'type': 'runtime_version', 'output': runtime_identity()})
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
        if sink.paths:
            try:
                artifacts = await asyncio.to_thread(artifact_index, sink.paths)
            except Exception:
                logger.exception('Failed to index research diagnostics: %s', run['id'])
    finally:
        task.cancel()
        monitor.cancel()
        await asyncio.gather(task, monitor, return_exceptions=True)
        usage_sink.reset(token)
        if slot:
            slot.release()
    try:
        await store.finish(run['id'], worker_id, state, error, artifacts)
    except Exception as exc:
        if state != 'completed':
            raise
        await store.finish(run['id'], worker_id, 'failed', f'Finalization failed: {exc}')


async def main():
    from backend.auth.schema_bootstrap import initialize_database
    from backend.auth.db import close_pool
    from backend.auth.db import get_pool
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
    # A single deployment worker owns the configured compute budget. Additional
    # processes wait for its DB lock rather than multiplying paid concurrency.
    pool=await get_pool()
    limit=max(1,min(8,int(os.getenv('ASTERIA_RESEARCH_CONCURRENCY','2'))))
    semaphore=asyncio.Semaphore(limit)
    pending=set()
    def finished(task):
        pending.discard(task)
        if not task.cancelled() and task.exception():
            logger.error('Research execution finalization failed; lease reaper will retain failure state')
    try:
        async with pool.acquire() as lease:
            while not stop.is_set() and not await lease.fetchval("SELECT pg_try_advisory_lock(hashtextextended(current_schema() || ':research-worker',0))"):
                await asyncio.sleep(1)
            try:
                while not stop.is_set():
                    try:
                        await store.reap()
                        if not semaphore.locked() and len(pending)<max(limit,8):
                            slot=ExecutionSlot(semaphore)
                            await slot.acquire()
                            try:
                                run=await store.claim(worker_id)
                            except BaseException:
                                slot.release()
                                raise
                            if run:
                                task=asyncio.create_task(execute(store,run,worker_id,slot=slot))
                                pending.add(task)
                                task.add_done_callback(finished)
                            else:
                                slot.release()
                        try:
                            await asyncio.wait_for(stop.wait(),.5)
                        except asyncio.TimeoutError:
                            pass
                    except Exception:
                        logger.exception('Worker iteration failed; no job will be blindly retried')
                        await asyncio.sleep(2)
                await asyncio.gather(*pending,return_exceptions=True)
            finally:
                await lease.execute("SELECT pg_advisory_unlock(hashtextextended(current_schema() || ':research-worker',0))")
    finally:
        await close_pool()


if __name__ == '__main__':
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    sys.path.insert(0, str(root / 'backend'))
    load_dotenv(root / '.env')
    load_dotenv(root / '.env.lab',override=True)
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
