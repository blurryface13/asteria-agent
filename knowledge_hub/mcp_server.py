"""Knowledge Hub as an MCP server (stdio transport).

Exposes the hybrid-retrieval knowledge base as standard MCP tools so any
MCP client (Claude Code / Desktop, asteria-agent's own MCP retriever, or
other agents) can query the lab's paper corpus.

Register e.g. in Claude Code:
    claude mcp add knowledge-hub -- \
        /path/to/.venv/bin/python -m knowledge_hub.mcp_server

Constraint: stdio transport means stdout belongs to the protocol - all
logging must go to stderr, never print().
"""
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mcp.server.fastmcp import FastMCP  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

mcp = FastMCP("knowledge-hub")

_searcher = None


def _get_searcher():
    global _searcher
    if _searcher is None:
        from knowledge_hub.retrieval.hybrid import HybridSearch
        _searcher = HybridSearch()
    return _searcher


@mcp.tool()
async def query_knowledge_hub(
    query: str,
    top_k: int = 5,
    collection: str | None = None,
    mode: str = "hybrid_rerank",
) -> str:
    """Search the lab's research-paper knowledge base (digital watermarking:
    screen-shooting / print-camera robustness). Returns the most relevant
    passages with paper title and page for citation.

    Args:
        query: natural-language research question (English works best)
        top_k: number of passages to return (default 5)
        collection: restrict to a collection, e.g. "watermark"; None = all
        mode: dense | sparse | hybrid | hybrid_rerank (default, most accurate)
    """
    chunks = await _get_searcher().search(query, top_k=top_k, collection=collection, mode=mode)
    if not chunks:
        return "No relevant passages found."
    blocks = []
    for i, c in enumerate(chunks, 1):
        blocks.append(f"[{i}] {c.title} (p.{c.page_start})\n{c.content}")
    return "\n\n---\n\n".join(blocks)


@mcp.tool()
async def list_collections() -> str:
    """List available collections in the knowledge base with document counts."""
    from knowledge_hub.config import KHConfig
    from knowledge_hub.db import get_pool

    cfg = KHConfig()
    pool = await get_pool(cfg.database_url)
    rows = await pool.fetch(
        """SELECT d.collection, count(DISTINCT d.id) AS docs, count(c.id) AS chunks
           FROM kh_documents d LEFT JOIN kh_chunks c ON c.doc_id = d.id
           GROUP BY d.collection ORDER BY docs DESC""")
    return "\n".join(f"{r['collection']}: {r['docs']} documents, {r['chunks']} chunks" for r in rows)


if __name__ == "__main__":
    mcp.run(transport="stdio")
