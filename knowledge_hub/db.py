"""asyncpg pool for the knowledge hub tables (kh_documents / kh_chunks).

Kept separate from backend/auth/db.py on purpose: the knowledge hub is a
standalone module (also runs as an MCP server outside the web app), so it
must not import from the web layer.
"""
import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool(database_url: str) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
