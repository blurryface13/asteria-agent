"""Reciprocal Rank Fusion: combine rankings from heterogeneous retrievers.

RRF(d) = sum over rankings r of 1 / (k + rank_r(d)).
Rank-based rather than score-based, so BM25 scores (unbounded) and cosine
similarities (0-1) never need to be calibrated against each other.
"""
from .types import RetrievedChunk


def rrf_fuse(rankings: list[list[RetrievedChunk]], k: int = 60, top_k: int = 10) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    best: dict[str, RetrievedChunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            if chunk.chunk_id in best:
                best[chunk.chunk_id].provenance.update(chunk.provenance)
            else:
                best[chunk.chunk_id] = chunk
    fused = sorted(best.values(), key=lambda c: scores[c.chunk_id], reverse=True)[:top_k]
    for c in fused:
        c.provenance["rrf"] = scores[c.chunk_id]
        c.score = scores[c.chunk_id]
    return fused
