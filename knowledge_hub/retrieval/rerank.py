"""LLM-based reranking via DeepSeek (OpenAI-compatible).

Chosen over a local cross-encoder deliberately: no extra model download
(disk-constrained dev machine), and the listwise-scoring prompt costs
fractions of a cent per query at deepseek-chat prices. Falls back to the
input order if the API key is missing or the call/parse fails - reranking
must never break retrieval.
"""
import json
import logging

from ..config import KHConfig
from .types import RetrievedChunk

logger = logging.getLogger(__name__)

_PROMPT = """You are a relevance judge. Score how relevant each passage is to the query on a 0-10 scale.

Query: {query}

Passages:
{passages}

Reply with ONLY a JSON array of numbers, one score per passage, in order. Example: [7, 2, 9]"""


class LLMReranker:
    def __init__(self, cfg: KHConfig):
        self.cfg = cfg
        self._client = None
        if cfg.deepseek_api_key:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=cfg.deepseek_api_key, base_url="https://api.deepseek.com")

    async def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]:
        if self._client is None or not chunks:
            return chunks[:top_k]
        passages = "\n".join(
            f"[{i}] ({c.title[:60]}) {c.content[:400]}" for i, c in enumerate(chunks)
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self.cfg.rerank_model,
                messages=[{"role": "user", "content": _PROMPT.format(query=query, passages=passages)}],
                max_tokens=200,
                temperature=0,
            )
            text = resp.choices[0].message.content.strip()
            text = text[text.index("["):text.rindex("]") + 1]
            scores = json.loads(text)
            if len(scores) != len(chunks):
                raise ValueError(f"expected {len(chunks)} scores, got {len(scores)}")
        except Exception as e:
            logger.warning(f"rerank failed, falling back to fusion order: {e}")
            return chunks[:top_k]

        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        result = []
        for i in order[:top_k]:
            chunks[i].provenance["rerank"] = float(scores[i])
            result.append(chunks[i])
        return result
