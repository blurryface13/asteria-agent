"""Idempotently create Asteria's PostgreSQL tables at application startup."""

import asyncio
from pathlib import Path

from backend.auth.db import get_pool

_initialized = False
_lock = asyncio.Lock()


async def initialize_database() -> None:
    global _initialized
    if _initialized:
        return

    async with _lock:
        if _initialized:
            return
        schema_dir = Path(__file__).resolve().parent
        schema_files = (
            schema_dir / "schema.sql",
            schema_dir / "reports_schema.sql",
            schema_dir / "workspace_schema.sql",
            schema_dir.parent / "runs" / "schema.sql",
            schema_dir.parent / "knowledge" / "schema.sql",
        )
        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            # API and worker may boot concurrently against the same database.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('asteria-schema-bootstrap', 0))")
            for schema_file in schema_files:
                await conn.execute(schema_file.read_text(encoding="utf-8"))
        _initialized = True
