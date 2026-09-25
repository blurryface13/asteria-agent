"""Authenticated research tool adapters; model-supplied arguments never choose a KB."""
from __future__ import annotations

import asyncio


def build_knowledge_search(owner: str | None, knowledge_ids: list[str] | None):
    """Bind accessible libraries at submission time, then verify ownership per call.

    The shared paper collection is served through the Modular RAG MCP engine;
    user/lab libraries use the managed hybrid Chroma path. Both return actual
    indexed chunks with version/page provenance, never an LLM-generated answer.
    """
    if not owner or not knowledge_ids:
        return None
    ids = tuple(dict.fromkeys(knowledge_ids))

    async def search(query: str):
        from backend.knowledge.mcp_client import search as mcp_search
        if not query.strip():
            raise ValueError("知识库检索词不能为空")
        return await asyncio.wait_for(mcp_search(owner, ids, query), timeout=55)

    return search
