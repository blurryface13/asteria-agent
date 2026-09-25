"""Public financial discovery. Only allowlisted official URLs reach the reader."""
import asyncio
from urllib.parse import urlparse

from asteria_researcher.agentic.primary_sources import FINANCIAL_HOSTS


async def search_financial_sources(terms):
    """Search snippets identify candidates, never substantiate report facts."""
    async def search(query):
        try:
            from ddgs import DDGS
            records = await asyncio.wait_for(asyncio.to_thread(
                lambda: list(DDGS().text(query, max_results=12))), 25)
            return [{'url': row.get('href'), 'title': str(row.get('title') or '')[:300],
                     'content': str(row.get('body') or '')[:1200]} for row in records]
        except Exception:
            from backend.server.specialists import search_public_sources
            return await search_public_sources(query)

    def official(rows):
        return [row for row in rows if urlparse(row.get('url') or '').hostname in FINANCIAL_HOSTS][:5]

    result = official(await search(terms))
    if result:
        return result
    return official(await search(f'{terms} official annual report filings investor relations regulator'))
