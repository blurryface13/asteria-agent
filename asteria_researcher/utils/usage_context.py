"""Request-local usage sink inherited by parallel asyncio research tasks."""
from contextvars import ContextVar

usage_sink = ContextVar('research_usage_sink', default=None)


async def record_usage(model, provider, attempt, metadata, error=None):
    sink = usage_sink.get()
    if sink:
        await sink({'type': 'usage', 'model': model, 'provider': provider,
                    'attempt': attempt, 'usage': metadata or None,
                    'available': bool(metadata), 'error': error})
