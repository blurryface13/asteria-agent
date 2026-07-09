"""Knowledge Hub HTTP API - RAG Q&A over the lab paper corpus.

Thin web layer over the Modular RAG engine (Chroma + qwen3-rerank): retrieve
with the hybrid pipeline, answer strictly from retrieved passages with [n]
citations. Same auth model as every other route.
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
    """RAG Q&A: retrieve with the Modular RAG engine (Chroma hybrid + qwen3-
    rerank), then synthesize a cited answer with the LLM. Upstream's query tool
    only returns formatted retrieval dumps, so we do answer synthesis here."""
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        trace = await get_modular_bridge().trace(
            query=req.question, top_k=req.top_k, collection=req.collection)
    except Exception as e:
        logger.error(f"knowledge search failed: {e}")
        raise HTTPException(status_code=502, detail="knowledge base search failed")

    chunks = trace.get("stages", {}).get("rerank") or []
    sources = [
        {
            "index": i + 1,
            "title": c.get("title") or f"source {i + 1}",
            "page": c.get("page"),
            "content": (c.get("content") or "")[:600],
            "scores": c.get("scores") or {"score": c.get("score")},
        }
        for i, c in enumerate(chunks)
    ]
    if not chunks:
        return {"answer": "知识库中没有找到相关内容。", "sources": []}

    passages = "\n\n".join(
        f"[{i + 1}] ({s['title']}) {s['content']}" for i, s in enumerate(sources))
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


@router.post("/trace")
async def trace_knowledge(req: TraceRequest, _email: str = Depends(get_current_user_email)):
    """Expose the retrieval pipeline stages (dense/sparse/RRF/rerank) for the
    RAG workspace UI, served by the Modular RAG engine."""
    from backend.knowledge.modular_rag import get_modular_bridge

    try:
        return await get_modular_bridge().trace(
            query=req.query, top_k=req.top_k, collection=req.collection)
    except Exception as e:
        logger.error(f"knowledge trace failed: {e}")
        raise HTTPException(status_code=502, detail="knowledge retrieval trace failed")


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
    results_path = Path(__file__).resolve().parents[2] / "eval" / "EVAL_METHODOLOGY.md"
    markdown = results_path.read_text(encoding="utf-8") if results_path.exists() else ""
    formal = _load_formal_report()
    fc = (formal or {}).get("corpus") or {}
    return {
        "formal": formal,
        "corpus": {
            "documents": fc.get("total_docs"),
            "chunks": fc.get("total_chunks"),
            "golden_queries": (formal or {}).get("golden_queries"),
        },
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
    """The knowledge base presented to the UI: the single research-paper
    collection served by the Modular RAG engine."""
    from backend.knowledge.modular_rag import get_modular_bridge, DEFAULT_COLLECTION

    try:
        data = await get_modular_bridge().collections()
    except Exception as e:
        logger.error(f"modular collections failed: {e}")
        raise HTTPException(status_code=502, detail="failed to list collections")

    cols = [c for c in (data.get("collections") or []) if c.get("collection") == DEFAULT_COLLECTION]
    return {"collections": [
        {"collection": c["collection"], "docs": c.get("docs"), "chunks": c.get("chunks")}
        for c in cols
    ]}
