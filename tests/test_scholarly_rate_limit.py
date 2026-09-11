import asyncio

import pytest

from asteria_researcher.agentic.primary_sources import retry_after_seconds, ScholarlyRateLimit
from asteria_researcher.agentic import library


def test_retry_after_supports_seconds_dates_and_missing_header():
    assert retry_after_seconds("25") == 25
    assert retry_after_seconds("Thu, 01 Jan 1970 00:01:30 GMT", now=30) == 60
    assert retry_after_seconds(None) == 60
    assert retry_after_seconds("bad header") == 60


def test_rate_limit_waits_then_retries_same_query(tmp_path, monkeypatch):
    ticks, calls, sleeps = [100.], [], []
    async def sleep(delay):
        sleeps.append(delay)
        ticks[0] += delay
    async def search(query, **kwargs):
        calls.append(query)
        if len(calls) == 1:
            raise ScholarlyRateLimit(30)
        return []
    monkeypatch.setattr(library.time, "monotonic", lambda: ticks[0])
    monkeypatch.setattr(library.asyncio, "sleep", sleep)
    monkeypatch.setattr(library, "search_papers", search)
    monkeypatch.setattr(library, "_search_cooldown_until", 0.)
    result = asyncio.run(library.PaperLibrary(tmp_path, None, None).search("watermark"))
    assert result == [] and calls == ["watermark", "watermark"]
    assert 30 in sleeps


def test_long_provider_cooldown_is_not_shortened_or_bypassed(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "_search_cooldown_until", library.time.monotonic() + 600)
    async def search(*args, **kwargs):
        pytest.fail("must not send request before provider retry-after")
    monkeypatch.setattr(library, "search_papers", search)
    with pytest.raises(ScholarlyRateLimit):
        asyncio.run(library.PaperLibrary(tmp_path, None, None).search("another query"))
