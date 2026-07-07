"""HybridSearch: the one entry point callers use.

    dense (pgvector) ─┐
                      ├─ RRF fusion ─ optional LLM rerank ─ results
    sparse (BM25)    ─┘
"""
import asyncio

from ..config import KHConfig
from .dense import DenseRetriever
from .sparse import SparseRetriever
from .fusion import rrf_fuse
from .rerank import LLMReranker
from .types import RetrievedChunk


class HybridSearch:
    def __init__(self, cfg: KHConfig | None = None):
        self.cfg = cfg or KHConfig()
        self.dense = DenseRetriever(self.cfg)
        self.sparse = SparseRetriever(self.cfg)
        self.reranker = LLMReranker(self.cfg)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        collection: str | None = None,
        mode: str = "hybrid",          # dense | sparse | hybrid | hybrid_rerank
        candidates_per_retriever: int = 20,
    ) -> list[RetrievedChunk]:
        if mode == "dense":
            return await self.dense.search(query, top_k, collection)
        if mode == "sparse":
            return await self.sparse.search(query, top_k, collection)

        dense_hits, sparse_hits = await asyncio.gather(
            self.dense.search(query, candidates_per_retriever, collection),
            self.sparse.search(query, candidates_per_retriever, collection),
        )
        fused = rrf_fuse([dense_hits, sparse_hits], k=self.cfg.rrf_k,
                         top_k=top_k if mode == "hybrid" else candidates_per_retriever)
        if mode == "hybrid":
            return fused
        return await self.reranker.rerank(query, fused, top_k=top_k)
