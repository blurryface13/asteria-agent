"""Dense retrieval: bge-m3 query embedding + pgvector cosine search (HNSW)."""
import asyncio

from langchain_ollama import OllamaEmbeddings

from ..config import KHConfig
from ..db import get_pool
from .types import RetrievedChunk


class DenseRetriever:
    def __init__(self, cfg: KHConfig):
        self.cfg = cfg
        self._embedder = OllamaEmbeddings(model=cfg.embedding_model, base_url=cfg.ollama_base_url)

    async def search(self, query: str, top_k: int = 10, collection: str | None = None) -> list[RetrievedChunk]:
        vector = await asyncio.to_thread(self._embedder.embed_query, query)
        vector_literal = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
        pool = await get_pool(self.cfg.database_url)
        rows = await pool.fetch(
            """SELECT c.id, c.doc_id, d.title, c.content, c.page_start,
                      1 - (c.embedding <=> $1::vector) AS score
               FROM kh_chunks c JOIN kh_documents d ON d.id = c.doc_id
               WHERE ($2::text IS NULL OR d.collection = $2)
               ORDER BY c.embedding <=> $1::vector
               LIMIT $3""",
            vector_literal, collection, top_k,
        )
        return [
            RetrievedChunk(
                chunk_id=r["id"], doc_id=r["doc_id"], title=r["title"],
                content=r["content"], page_start=r["page_start"],
                score=float(r["score"]), provenance={"dense": float(r["score"])},
            )
            for r in rows
        ]
