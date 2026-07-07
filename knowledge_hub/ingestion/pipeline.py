"""Ingestion orchestrator: load -> chunk -> embed (bge-m3) -> upsert (pgvector).

Idempotent by design: doc_id is a content hash, chunk ids derive from it,
and both upserts are ON CONFLICT DO NOTHING / UPDATE - re-running on the
same corpus is safe and cheap (already-ingested docs are skipped upfront).
One bad PDF never aborts the batch.
"""
import asyncio
import logging
from pathlib import Path

from langchain_ollama import OllamaEmbeddings

from ..config import KHConfig
from ..db import get_pool
from .loader import load_pdf
from .chunker import chunk_document

logger = logging.getLogger(__name__)

EMBED_BATCH = 32


async def ingest_paths(paths: list[str | Path], collection: str, cfg: KHConfig) -> dict:
    pool = await get_pool(cfg.database_url)
    embedder = OllamaEmbeddings(model=cfg.embedding_model, base_url=cfg.ollama_base_url)

    stats = {"ingested": 0, "skipped_existing": 0, "failed": 0, "chunks": 0}
    for path in paths:
        try:
            await _ingest_one(path, collection, cfg, pool, embedder, stats)
        except Exception as e:
            logger.error(f"failed on {path}: {type(e).__name__}: {e}")
            stats["failed"] += 1
    return stats


async def _ingest_one(path, collection: str, cfg: KHConfig, pool, embedder, stats: dict):
    doc = await asyncio.to_thread(load_pdf, path)
    if doc is None:
        logger.warning(f"unreadable/scanned pdf, skipped: {path}")
        stats["failed"] += 1
        return

    already = await pool.fetchval("SELECT 1 FROM kh_documents WHERE id = $1", doc.doc_id)
    if already:
        stats["skipped_existing"] += 1
        return

    chunks = chunk_document(doc, cfg.chunk_size, cfg.chunk_overlap)
    if not chunks:
        stats["failed"] += 1
        return

    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = [c.content for c in chunks[i:i + EMBED_BATCH]]
        vectors.extend(await asyncio.to_thread(embedder.embed_documents, batch))

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO kh_documents (id, title, source_path, collection, num_pages)
                   VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING""",
                doc.doc_id, doc.title, doc.source_path, collection, len(doc.pages),
            )
            await conn.executemany(
                """INSERT INTO kh_chunks (id, doc_id, chunk_index, content, page_start, embedding)
                   VALUES ($1, $2, $3, $4, $5, $6::vector)
                   ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, embedding = EXCLUDED.embedding""",
                [
                    (c.chunk_id, c.doc_id, c.index, c.content, c.page_start,
                     "[" + ",".join(f"{x:.6f}" for x in v) + "]")
                    for c, v in zip(chunks, vectors)
                ],
            )
    stats["ingested"] += 1
    stats["chunks"] += len(chunks)
    logger.info(f"ingested: {doc.title[:60]} ({len(chunks)} chunks)")
