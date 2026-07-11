"""Query understanding layer for the knowledge-base QA path.

Real user queries are colloquial, often Chinese, and full of unexpanded
domain abbreviations - while the corpus is largely English papers. Without
preprocessing, the BM25 leg gets almost no lexical overlap and retrieval
degrades to dense-only. This layer rewrites the query into a retrieval-
friendly form before hybrid search:

  - normalize to English (the corpus language)
  - expand domain abbreviations (PSNR -> peak signal-to-noise ratio, ...)
  - keep the original key terms alongside the expansion (both legs benefit)

One cheap LLM call (deepseek, temperature 0), with a graceful fallback to
the original query on any failure - understanding must never break retrieval.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = """You are a query rewriter for a research-paper retrieval system. \
The corpus is English academic papers on digital watermarking, image processing and AI.

Rewrite the user's query into ONE English retrieval query:
- translate to English if needed
- expand domain abbreviations (e.g. PSNR -> peak signal-to-noise ratio PSNR)
- keep the core technical terms; you may append 2-4 closely related keywords
- output ONLY the rewritten query text, no explanations

User query: {query}"""


async def rewrite_query(query: str) -> str:
    """Return a retrieval-friendly rewrite of the query (original on failure)."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key or not query.strip():
        return query
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": _REWRITE_PROMPT.format(query=query)}],
            max_tokens=120,
            temperature=0,
        )
        rewritten = (resp.choices[0].message.content or "").strip().strip('"')
        return rewritten or query
    except Exception as e:
        logger.warning(f"query rewrite failed, using original: {e}")
        return query
