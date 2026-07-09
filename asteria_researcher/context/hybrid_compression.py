"""Hybrid context compression: BM25 + dense + RRF over scraped web content.

Upgrades ContextCompressor's single-signal dense filtering. Same problem
shape as knowledge_hub's hybrid retrieval, applied to an ephemeral corpus
(this round's scraped pages) instead of a persistent vector store - the
fusion/dedup logic is deliberately re-implemented inline (~40 lines) so the
engine package stays self-contained.

Improvements over the dense-threshold pipeline:
- adds a BM25 lexical signal (method names, dataset names, model numbers
  in sub-queries are strong relevance evidence that embeddings smear out)
- rank-based RRF selection replaces the brittle absolute similarity
  threshold (0.35) - never returns an empty context because a threshold
  happened to be miscalibrated for this query's score distribution
- near-duplicate removal (syndicated/mirrored articles) frees context
  budget: greedy cosine > 0.95 suppression over already-selected chunks
- optional listwise LLM rerank (CONTEXT_RERANK=true) for the final cut

Selected via CONTEXT_FILTER_MODE=hybrid (default remains the original
dense pipeline; see skills/context_manager.py).
"""
import asyncio
import json
import logging
import os
import re

import numpy as np
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from ..memory.embeddings import OPENAI_EMBEDDING_MODEL
from ..prompts import PromptFamily
from ..utils.costs import estimate_embedding_cost

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")
_DEDUP_COSINE = 0.95
_RRF_K = 60
_CANDIDATES_PER_SIGNAL = 20


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("%s=%r is invalid, using %s", name, raw, default)
        return default


_EMBED_BATCH = _env_int("CONTEXT_EMBED_BATCH", 32)
_EMBED_CONCURRENCY = _env_int("CONTEXT_EMBED_CONCURRENCY", 1)
_EMBED_SEMAPHORE = asyncio.Semaphore(_EMBED_CONCURRENCY)


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _rrf(rankings: list[list[int]], k: int = _RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return scores


def _cosine_similarity(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    vector = np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0)
    matrix = np.clip(matrix, -1e6, 1e6)
    vector = np.clip(vector, -1e6, 1e6)
    matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    vector_norm = np.linalg.norm(vector)
    matrix_unit = matrix / np.maximum(matrix_norms, 1e-12)
    vector_unit = vector / max(vector_norm, 1e-12)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        cosine = matrix_unit @ vector_unit
    return np.clip(np.nan_to_num(cosine, nan=-1.0, posinf=1.0, neginf=-1.0), -1.0, 1.0)


class HybridContextCompressor:
    """Drop-in replacement for ContextCompressor (same constructor/method
    signatures, same pretty-printed output format)."""

    def __init__(
        self,
        documents,
        embeddings,
        max_results: int = 5,
        prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
        **kwargs,
    ):
        self.documents = documents
        self.embeddings = embeddings
        self.max_results = max_results
        self.prompt_family = prompt_family
        self.kwargs = kwargs

    def _split(self) -> list[Document]:
        docs = [
            Document(
                page_content=page.get("raw_content") or "",
                metadata={k: v for k, v in page.items() if k != "raw_content"},
            )
            for page in self.documents
            if page.get("raw_content")
        ]
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        return [c for c in splitter.split_documents(docs) if len(c.page_content) >= 80]

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed all texts while protecting local Ollama from request storms.

        The research pipeline processes sub-queries concurrently. A single
        sub-query can also produce hundreds or thousands of chunks when a PDF is
        scraped. Sending every chunk as one huge request, and doing that from
        several sub-queries at once, can wedge the local Ollama runner. We keep
        dense retrieval intact by embedding every chunk, but serialize and batch
        calls to the embedding backend.
        """
        if not texts:
            return []

        batch_size = max(1, _EMBED_BATCH)
        vectors: list[list[float]] = []
        async with _EMBED_SEMAPHORE:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                if hasattr(self.embeddings, "aembed_documents"):
                    batch_vectors = await self.embeddings.aembed_documents(batch)
                else:
                    batch_vectors = await asyncio.to_thread(self.embeddings.embed_documents, batch)
                vectors.extend(batch_vectors)
        return vectors

    async def _maybe_rerank(self, query: str, chunks: list[Document], top_k: int) -> list[Document]:
        if os.environ.get("CONTEXT_RERANK", "").lower() != "true":
            return chunks[:top_k]
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key or not chunks:
            return chunks[:top_k]
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            passages = "\n".join(
                f"[{i}] {c.page_content[:400]}" for i, c in enumerate(chunks))
            resp = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content":
                    f"Score each passage's relevance to the query on 0-10.\n\n"
                    f"Query: {query}\n\nPassages:\n{passages}\n\n"
                    f"Reply with ONLY a JSON array of numbers, one per passage."}],
                max_tokens=200, temperature=0,
            )
            text = resp.choices[0].message.content.strip()
            scores = json.loads(text[text.index("["):text.rindex("]") + 1])
            if len(scores) != len(chunks):
                raise ValueError("score count mismatch")
            order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
            return [chunks[i] for i in order[:top_k]]
        except Exception as e:
            logger.warning(f"context rerank failed, keeping fusion order: {e}")
            return chunks[:top_k]

    async def async_get_context(self, query: str, max_results: int = 5, cost_callback=None) -> str:
        # Fast path: identical to ContextCompressor - tiny corpora skip filtering
        total_chars = sum(len(str(d.get("raw_content", ""))) for d in self.documents)
        chunk_threshold = int(os.environ.get("COMPRESSION_THRESHOLD", "8000"))
        if total_chars < chunk_threshold and len(self.documents) <= max_results:
            direct = [Document(page_content=d.get("raw_content", ""), metadata=d)
                      for d in self.documents[:max_results]]
            return self.prompt_family.pretty_print_docs(direct, max_results)

        chunks = self._split()
        if not chunks:
            return ""

        if cost_callback:
            cost_callback(estimate_embedding_cost(model=OPENAI_EMBEDDING_MODEL, docs=self.documents))

        # dense signal
        texts = [c.page_content for c in chunks]
        all_vecs = await self._embed_texts([query] + texts)
        query_vec = all_vecs[0]
        chunk_vecs = all_vecs[1:]
        matrix = np.asarray(chunk_vecs, dtype=np.float64)
        q = np.asarray(query_vec, dtype=np.float64)
        cosine = _cosine_similarity(matrix, q)
        dense_ranking = list(np.argsort(-cosine)[:_CANDIDATES_PER_SIGNAL])

        # sparse signal
        bm25 = BM25Okapi([_tokenize(t) for t in texts])
        bm25_scores = bm25.get_scores(_tokenize(query))
        sparse_ranking = [i for i in np.argsort(-bm25_scores)[:_CANDIDATES_PER_SIGNAL]
                          if bm25_scores[i] > 0]

        # rank fusion, then near-duplicate suppression
        fused = sorted(_rrf([dense_ranking, sparse_ranking]).items(),
                       key=lambda kv: kv[1], reverse=True)
        selected: list[int] = []
        for idx, _score in fused:
            if any(float(_cosine_similarity(matrix[idx:idx + 1], matrix[j])[0]) > _DEDUP_COSINE
                   for j in selected):
                continue
            selected.append(idx)
            if len(selected) >= _CANDIDATES_PER_SIGNAL:
                break

        final = await self._maybe_rerank(query, [chunks[i] for i in selected], max_results)
        return self.prompt_family.pretty_print_docs(final, max_results)
