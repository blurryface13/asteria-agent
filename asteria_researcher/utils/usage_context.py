"""Request-local usage sink inherited by parallel asyncio research tasks."""
from contextlib import contextmanager
from contextvars import ContextVar

usage_sink = ContextVar('research_usage_sink', default=None)
usage_stage = ContextVar('research_usage_stage', default=None)


@contextmanager
def track_usage_stage(stage):
    """Attribute model calls in one coroutine without leaking across siblings."""
    token = usage_stage.set(stage)
    try:
        yield
    finally:
        usage_stage.reset(token)


async def record_usage(model, provider, attempt, metadata, error=None, latency_ms=None):
    sink = usage_sink.get()
    if sink:
        await sink({'type': 'usage', 'model': model, 'provider': provider,
                    'attempt': attempt, 'stage': usage_stage.get(), 'usage': metadata or None,
                    'available': bool(metadata), 'error': error,
                    'latency_ms': latency_ms})
