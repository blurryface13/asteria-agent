"""Knowledge Hub HTTP API - RAG Q&A over the lab paper corpus.

Thin web layer over knowledge_hub's HybridSearch: retrieve with the
hybrid pipeline, then have the LLM answer strictly from the retrieved
passages with [n] citations. Same auth model as every other route.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_searcher = None


def _get_searcher():
    global _searcher
    if _searcher is None:
        from knowledge_hub.retrieval.hybrid import HybridSearch
        _searcher = HybridSearch()
    return _searcher


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    collection: str | None = None
    mode: str = "hybrid_rerank"
    top_k: int = Field(default=5, ge=1, le=10)


_ANSWER_PROMPT = """You are a research assistant answering questions about a corpus of academic papers.

Answer the question using ONLY the passages below. Cite passages inline as [1], [2] etc. If the passages do not contain the answer, say so plainly - do not invent content.
Answer in the same language as the question.

Question: {question}

Passages:
{passages}
"""


@router.post("/ask")
async def ask_knowledge(req: AskRequest, _email: str = Depends(get_current_user_email)):
    try:
        chunks = await _get_searcher().search(
            req.question, top_k=req.top_k, collection=req.collection, mode=req.mode)
    except Exception as e:
        logger.error(f"knowledge search failed: {e}")
        raise HTTPException(status_code=502, detail="knowledge base search failed")

    sources = [
        {
            "index": i + 1,
            "title": c.title,
            "page": c.page_start,
            "content": c.content[:600],
            "scores": {k: round(v, 4) for k, v in c.provenance.items()},
        }
        for i, c in enumerate(chunks)
    ]
    if not chunks:
        return {"answer": "知识库中没有找到相关内容。", "sources": []}

    passages = "\n\n".join(
        f"[{i + 1}] ({c.title}, p.{c.page_start})\n{c.content[:1200]}"
        for i, c in enumerate(chunks)
    )
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    try:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": _ANSWER_PROMPT.format(
                question=req.question, passages=passages)}],
            max_tokens=1500,
            temperature=0.2,
        )
        answer = resp.choices[0].message.content
    except Exception as e:
        logger.error(f"knowledge answer generation failed: {e}")
        raise HTTPException(status_code=502, detail="answer generation failed")

    return {"answer": answer, "sources": sources}


@router.get("/collections")
async def list_collections(_email: str = Depends(get_current_user_email)):
    from knowledge_hub.config import KHConfig
    from knowledge_hub.db import get_pool

    pool = await get_pool(KHConfig().database_url)
    rows = await pool.fetch(
        """SELECT d.collection, count(DISTINCT d.id) AS docs, count(c.id) AS chunks
           FROM kh_documents d LEFT JOIN kh_chunks c ON c.doc_id = d.id
           GROUP BY d.collection ORDER BY docs DESC""")
    return {"collections": [dict(r) for r in rows]}
