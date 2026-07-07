"""
Postgres connection pool for the auth system.

Kept deliberately separate from asteria-agent's own config/LLM plumbing -
auth is a bolt-on feature, not part of the research pipeline.
"""
import os
import json
import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn: asyncpg.Connection):
    # asyncpg returns jsonb columns as raw strings by default - teach every
    # connection in the pool to decode/encode them as real Python objects,
    # so callers never have to remember json.loads() on the way out.
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        _pool = await asyncpg.create_pool(
            database_url, min_size=1, max_size=5, init=_init_connection
        )
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
