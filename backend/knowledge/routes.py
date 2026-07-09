"""Knowledge Hub HTTP API - RAG Q&A over the lab paper corpus.

Thin web layer over knowledge_hub's HybridSearch: retrieve with the
hybrid pipeline, then have the LLM answer strictly from the retrieved
passages with [n] citations. Same auth model as every other route.
"""
import logging
import os
import sys
import time
from pathlib import Path

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


class TraceRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    collection: str | None = None
    mode: str = "hybrid_rerank"
    top_k: int = Field(default=5, ge=1, le=10)
    candidates_per_retriever: int = Field(default=20, ge=5, le=50)


class ModularIngestRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4000)
    collection: str | None = None
    force: bool = False


class ModularEvaluationRequest(BaseModel):
    collection: str | None = None
    top_k: int = Field(default=10, ge=1, le=20)
    test_set_path: str | None = None


class ModularRagasRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    answer: str = Field(min_length=2, max_length=8000)
    contexts: list[str] = Field(min_length=1, max_length=20)
    metrics: list[str] | None = None


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


def _chunk_to_trace_item(chunk, rank: int):
    return {
        "rank": rank,
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "title": chunk.title,
        "page": chunk.page_start,
        "content": chunk.content[:420],
        "score": round(float(chunk.score), 4),
        "scores": {k: round(float(v), 4) for k, v in chunk.provenance.items()},
    }


@router.post("/trace")
async def trace_knowledge(req: TraceRequest, _email: str = Depends(get_current_user_email)):
    """Expose the retrieval pipeline stages for the RAG workspace UI."""
    import asyncio
    from knowledge_hub.retrieval.fusion import rrf_fuse

    searcher = _get_searcher()
    started = time.perf_counter()

    try:
        dense_hits, sparse_hits = await asyncio.gather(
            searcher.dense.search(req.query, req.candidates_per_retriever, req.collection),
            searcher.sparse.search(req.query, req.candidates_per_retriever, req.collection),
        )
        fused_hits = rrf_fuse(
            [dense_hits, sparse_hits],
            k=searcher.cfg.rrf_k,
            top_k=req.candidates_per_retriever if req.mode == "hybrid_rerank" else req.top_k,
        )
        final_hits = (
            await searcher.reranker.rerank(req.query, fused_hits, top_k=req.top_k)
            if req.mode == "hybrid_rerank"
            else fused_hits[: req.top_k]
        )
    except Exception as e:
        logger.error(f"knowledge trace failed: {e}")
        raise HTTPException(status_code=502, detail="knowledge retrieval trace failed")

    elapsed = time.perf_counter() - started
    return {
        "query": req.query,
        "collection": req.collection,
        "mode": req.mode,
        "rrf_k": searcher.cfg.rrf_k,
        "latency_s": round(elapsed, 3),
        "stages": {
            "dense": [_chunk_to_trace_item(c, i + 1) for i, c in enumerate(dense_hits[: req.top_k])],
            "sparse": [_chunk_to_trace_item(c, i + 1) for i, c in enumerate(sparse_hits[: req.top_k])],
            "rrf": [_chunk_to_trace_item(c, i + 1) for i, c in enumerate(fused_hits[: req.top_k])],
            "rerank": [_chunk_to_trace_item(c, i + 1) for i, c in enumerate(final_hits)],
        },
        "mcp_tool_call": {
            "server": "knowledge-hub",
            "tool": "query_knowledge_hub",
            "arguments": {
                "query": req.query,
                "top_k": req.top_k,
                "collection": req.collection,
                "mode": req.mode,
            },
            "status": "ready",
        },
    }


def _load_formal_report() -> dict | None:
    """Read the combined-corpus Hit Rate + Ragas Faithfulness report produced by
    scripts/formal_full_kb_ragas_eval.py, if a run has been persisted."""
    report_path = (
        Path(__file__).resolve().parents[2]
        / "outputs" / "full_kb_rag_eval" / "full_kb_ragas_eval_report.json"
    )
    if not report_path.exists():
        return None
    try:
        import json
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    hit = (raw.get("hit_rate") or {}).get("summary") or {}
    faith = (raw.get("faithfulness") or {}).get("summary") or raw.get("faithfulness") or {}
    return {
        "golden_queries": raw.get("golden_query_count"),
        "corpus": raw.get("corpus"),
        "hit_rate10": {mode: round(v.get("hit_rate@10"), 4) for mode, v in hit.items() if isinstance(v, dict)},
        "faithfulness": {
            "average": round(faith["average"], 4) if faith.get("average") is not None else None,
            "min": faith.get("min"),
            "max": faith.get("max"),
            "sample_count": faith.get("sample_count"),
            "errors": faith.get("errors"),
        },
        "elapsed_s": raw.get("elapsed_s"),
    }


@router.get("/evaluation")
async def get_evaluation_summary(_email: str = Depends(get_current_user_email)):
    """Return the latest offline RAG evaluation snapshot."""
    results_path = Path(__file__).resolve().parents[2] / "knowledge_hub" / "eval" / "RESULTS.md"
    markdown = results_path.read_text(encoding="utf-8") if results_path.exists() else ""
    return {
        "formal": _load_formal_report(),
        "corpus": {
            "documents": 321,
            "chunks": 23269,
            "collections": [
                {"name": "watermark", "documents": 174},
                {"name": "general", "documents": 147},
            ],
            "golden_queries": 60,
        },
        "metrics": [
            {"scenario": "watermark", "mode": "dense", "hit10": 0.933, "mrr10": 0.661, "latency_s": 0.12},
            {"scenario": "watermark", "mode": "sparse", "hit10": 0.933, "mrr10": 0.765, "latency_s": 0.06},
            {"scenario": "watermark", "mode": "hybrid", "hit10": 0.983, "mrr10": 0.685, "latency_s": 0.09},
            {"scenario": "watermark", "mode": "hybrid_rerank", "hit10": 0.967, "mrr10": 0.718, "latency_s": 1.55},
            {"scenario": "full_corpus", "mode": "dense", "hit10": 0.933, "mrr10": 0.642, "latency_s": 0.09},
            {"scenario": "full_corpus", "mode": "sparse", "hit10": 0.933, "mrr10": 0.760, "latency_s": 0.11},
            {"scenario": "full_corpus", "mode": "hybrid", "hit10": 0.983, "mrr10": 0.683, "latency_s": 0.10},
            {"scenario": "full_corpus", "mode": "hybrid_rerank", "hit10": 0.950, "mrr10": 0.702, "latency_s": 1.53},
        ],
        "markdown": markdown,
    }


@router.get("/mcp/presets")
async def get_mcp_presets(_email: str = Depends(get_current_user_email)):
    """Expose server-side MCP presets that can be sent through the research request."""
    from backend.knowledge.modular_rag import get_modular_config, get_modular_root

    modular_root = str(get_modular_root())
    modular_config = str(get_modular_config())
    return {
        "presets": [
            {
                "name": "knowledge_hub",
                "label": "Local Knowledge Hub",
                "description": "Query this project's pgvector/BM25 research-paper RAG system through stdio MCP.",
                "config": {
                    "name": "knowledge_hub",
                    "command": sys.executable,
                    "args": ["-m", "knowledge_hub.mcp_server"],
                    "env": {},
                },
            },
            {
                "name": "modular_rag",
                "label": "Modular RAG MCP",
                "description": "Launch jerry-ai-dev/MODULAR-RAG-MCP-SERVER as a stdio MCP server.",
                "available": Path(modular_root).exists(),
                "config": {
                    "name": "modular_rag",
                    "command": "bash",
                    "args": [
                        "-lc",
                        f"cd {modular_root} && MODULAR_RAG_MCP_CONFIG={modular_config} python -m src.mcp_server.server",
                    ],
                    "env": {
                        "MODULAR_RAG_MCP_ROOT": modular_root,
                        "MODULAR_RAG_MCP_CONFIG": modular_config,
                    },
                },
            },
        ]
    }


@router.get("/modular/status")
async def get_modular_status(_email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return get_modular_bridge().status()
    except Exception as e:
        logger.error(f"modular rag status failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/modular/ask")
async def ask_modular_knowledge(req: AskRequest, _email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().ask(
            query=req.question,
            top_k=req.top_k,
            collection=req.collection,
        )
    except Exception as e:
        logger.error(f"modular rag query failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/modular/trace")
async def trace_modular_knowledge(req: TraceRequest, _email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().trace(
            query=req.query,
            top_k=req.top_k,
            collection=req.collection,
        )
    except Exception as e:
        logger.error(f"modular rag trace failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/modular/collections")
async def list_modular_collections(_email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().collections()
    except Exception as e:
        logger.error(f"modular rag collections failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/modular/ingest")
async def ingest_modular_documents(req: ModularIngestRequest, _email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().ingest(
            path=req.path,
            collection=req.collection,
            force=req.force,
        )
    except Exception as e:
        logger.error(f"modular rag ingestion failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/modular/evaluation")
async def evaluate_modular_rag(req: ModularEvaluationRequest, _email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().evaluation(
            collection=req.collection,
            top_k=req.top_k,
            test_set_path=req.test_set_path,
        )
    except Exception as e:
        logger.error(f"modular rag evaluation failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/modular/ragas")
async def evaluate_modular_ragas(req: ModularRagasRequest, _email: str = Depends(get_current_user_email)):
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().ragas_score(
            query=req.query,
            answer=req.answer,
            contexts=req.contexts,
            metrics=req.metrics,
        )
    except Exception as e:
        logger.error(f"modular ragas evaluation failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


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
