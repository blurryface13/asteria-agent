"""Sparse retrieval: in-memory BM25 (Okapi) over all chunks.

The corpus is small (a few hundred papers -> low tens of thousands of
chunks), so we rebuild the index from Postgres on first use and keep it in
memory. Persisting the index adds moving parts without measurable benefit
at this scale.
"""
import re

from rank_bm25 import BM25Okapi

from ..config import KHConfig
from ..db import get_pool
from .types import RetrievedChunk

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class SparseRetriever:
    def __init__(self, cfg: KHConfig):
        self.cfg = cfg
        self._bm25: BM25Okapi | None = None
        self._chunks: list[dict] = []
        self._collection: str | None = "___unloaded___"

    async def _ensure_index(self, collection: str | None):
        if self._bm25 is not None and collection == self._collection:
            return
        pool = await get_pool(self.cfg.database_url)
        rows = await pool.fetch(
            """SELECT c.id, c.doc_id, d.title, c.content, c.page_start
               FROM kh_chunks c JOIN kh_documents d ON d.id = c.doc_id
               WHERE ($1::text IS NULL OR d.collection = $1)""",
            collection,
        )
        self._chunks = [dict(r) for r in rows]
        self._bm25 = BM25Okapi([tokenize(c["content"]) for c in self._chunks] or [["_"]])
        self._collection = collection

    async def search(self, query: str, top_k: int = 10, collection: str | None = None) -> list[RetrievedChunk]:
        await self._ensure_index(collection)
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                chunk_id=self._chunks[i]["id"], doc_id=self._chunks[i]["doc_id"],
                title=self._chunks[i]["title"], content=self._chunks[i]["content"],
                page_start=self._chunks[i]["page_start"],
                score=float(scores[i]), provenance={"bm25": float(scores[i])},
            )
            for i in ranked if scores[i] > 0
        ]
