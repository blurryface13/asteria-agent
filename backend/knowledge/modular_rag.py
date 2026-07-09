"""Bridge to jerry-ai-dev/MODULAR-RAG-MCP-SERVER.

The bridge keeps the external project as the actual RAG engine. Asteria only
normalizes HTTP responses for the local UI/API.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(
    "/Users/dora/Documents/Codex/2026-07-07/wome/work/MODULAR-RAG-MCP-SERVER"
)
DEFAULT_CONFIG = Path(__file__).resolve().with_name("modular_rag_settings.yaml")
ASTERIA_ROOT = Path(__file__).resolve().parents[2]


class ModularRAGError(RuntimeError):
    """Raised when the external Modular RAG engine cannot be used."""


def get_modular_root() -> Path:
    return Path(os.getenv("MODULAR_RAG_MCP_ROOT", str(DEFAULT_ROOT))).expanduser().resolve()


def get_modular_config() -> Path:
    return Path(os.getenv("MODULAR_RAG_MCP_CONFIG", str(DEFAULT_CONFIG))).expanduser().resolve()


def _ensure_project_path() -> Path:
    root = get_modular_root()
    if not root.exists():
        raise ModularRAGError(f"MODULAR_RAG_MCP_ROOT does not exist: {root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _load_settings():
    _ensure_project_path()
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=ASTERIA_ROOT / ".env", override=False)
    except Exception:
        pass
    config_path = get_modular_config()
    if not config_path.exists():
        raise ModularRAGError(f"MODULAR_RAG_MCP_CONFIG does not exist: {config_path}")
    from src.core.settings import load_settings

    return load_settings(str(config_path))


def _result_to_item(result: Any, rank: int) -> dict[str, Any]:
    metadata = getattr(result, "metadata", {}) or {}
    return {
        "rank": rank,
        "chunk_id": getattr(result, "chunk_id", ""),
        "doc_id": metadata.get("source_ref") or metadata.get("doc_hash") or "",
        "title": metadata.get("title") or Path(metadata.get("source_path", "")).stem,
        "page": metadata.get("page_num") or metadata.get("page"),
        "content": (getattr(result, "text", "") or "")[:600],
        "score": round(float(getattr(result, "score", 0.0) or 0.0), 4),
        "scores": {
            key: round(float(value), 4)
            for key, value in {
                "score": getattr(result, "score", 0.0),
                "original_score": metadata.get("original_score"),
                "rerank_score": metadata.get("rerank_score"),
            }.items()
            if value is not None
        },
        "metadata": metadata,
    }


class ModularRAGBridge:
    """Small facade over the external project's query, trace, ingest, and eval APIs."""

    def __init__(self) -> None:
        self._query_tool = None
        self._settings = None

    @property
    def root(self) -> Path:
        return get_modular_root()

    @property
    def config_path(self) -> Path:
        return get_modular_config()

    @property
    def settings(self):
        if self._settings is None:
            self._settings = _load_settings()
            # LLM providers are registered in src.libs.llm.__init__.
            import src.libs.llm  # noqa: F401
            from backend.knowledge.modular_qwen import register_qwen_providers

            register_qwen_providers()
        return self._settings

    def status(self) -> dict[str, Any]:
        settings = self.settings
        return {
            "engine": "modular",
            "root": str(self.root),
            "config": str(self.config_path),
            "available": self.root.exists() and self.config_path.exists(),
            "models": {
                "llm": {
                    "provider": settings.llm.provider,
                    "model": settings.llm.model,
                },
                "embedding": {
                    "provider": settings.embedding.provider,
                    "model": settings.embedding.model,
                    "dimensions": settings.embedding.dimensions,
                },
                "rerank": {
                    "enabled": settings.rerank.enabled,
                    "provider": settings.rerank.provider,
                    "model": settings.rerank.model,
                },
                "vision": {
                    "enabled": bool(settings.vision_llm and settings.vision_llm.enabled),
                    "provider": settings.vision_llm.provider if settings.vision_llm else None,
                    "model": settings.vision_llm.model if settings.vision_llm else None,
                },
            },
            "storage": {
                "vector_store": settings.vector_store.provider,
                "persist_directory": settings.vector_store.persist_directory,
                "collection_name": settings.vector_store.collection_name,
            },
            "retrieval": {
                "dense_top_k": settings.retrieval.dense_top_k,
                "sparse_top_k": settings.retrieval.sparse_top_k,
                "fusion_top_k": settings.retrieval.fusion_top_k,
                "rrf_k": settings.retrieval.rrf_k,
            },
        }

    def _get_query_tool(self):
        if self._query_tool is None:
            _ensure_project_path()
            from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool

            self._query_tool = QueryKnowledgeHubTool(settings=self.settings)
        return self._query_tool

    async def ask(
        self,
        query: str,
        top_k: int = 5,
        collection: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        response = await self._get_query_tool().execute(
            query=query,
            top_k=top_k,
            collection=collection,
        )
        return {
            "engine": "modular",
            "answer": response.content,
            "sources": [citation.to_dict() for citation in response.citations],
            "metadata": response.metadata,
            "latency_s": round(time.perf_counter() - started, 3),
        }

    def _build_components(self, collection: str):
        _ensure_project_path()
        from src.core.query_engine.query_processor import QueryProcessor
        from src.core.query_engine.hybrid_search import create_hybrid_search
        from src.core.query_engine.dense_retriever import create_dense_retriever
        from src.core.query_engine.sparse_retriever import create_sparse_retriever
        from src.core.query_engine.reranker import create_core_reranker
        from src.core.settings import resolve_path
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory

        settings = self.settings
        vector_store = VectorStoreFactory.create(settings, collection_name=collection)
        embedding_client = EmbeddingFactory.create(settings)
        dense_retriever = create_dense_retriever(
            settings=settings,
            embedding_client=embedding_client,
            vector_store=vector_store,
        )
        bm25_indexer = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
        sparse_retriever = create_sparse_retriever(
            settings=settings,
            bm25_indexer=bm25_indexer,
            vector_store=vector_store,
        )
        sparse_retriever.default_collection = collection
        hybrid_search = create_hybrid_search(
            settings=settings,
            query_processor=QueryProcessor(),
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
        )
        reranker = create_core_reranker(settings=settings)
        return hybrid_search, reranker

    async def trace(
        self,
        query: str,
        top_k: int = 5,
        collection: str | None = None,
    ) -> dict[str, Any]:
        _ensure_project_path()
        from src.core.trace import TraceContext, TraceCollector

        effective_collection = collection or self.settings.vector_store.collection_name or "default"
        started = time.perf_counter()
        trace = TraceContext(trace_type="query")
        trace.metadata.update(
            {"query": query[:200], "top_k": top_k, "collection": effective_collection}
        )

        def _run():
            hybrid_search, reranker = self._build_components(effective_collection)
            hybrid_result = hybrid_search.search(
                query=query,
                top_k=max(top_k * 2, self.settings.retrieval.fusion_top_k),
                trace=trace,
                return_details=True,
            )
            final_results = hybrid_result.results
            rerank_used = False
            if reranker.is_enabled and final_results:
                rerank_result = reranker.rerank(
                    query=query,
                    results=final_results,
                    top_k=top_k,
                    trace=trace,
                )
                rerank_used = not rerank_result.used_fallback
                final_results = rerank_result.results
            else:
                final_results = final_results[:top_k]
            TraceCollector().collect(trace)
            return hybrid_result, final_results, rerank_used

        hybrid_result, final_results, rerank_used = await asyncio.to_thread(_run)
        elapsed = time.perf_counter() - started
        return {
            "engine": "modular",
            "query": query,
            "collection": effective_collection,
            "mode": "hybrid_rerank" if rerank_used else "hybrid",
            "rrf_k": self.settings.retrieval.rrf_k,
            "latency_s": round(elapsed, 3),
            "stages": {
                "dense": [
                    _result_to_item(item, index + 1)
                    for index, item in enumerate((hybrid_result.dense_results or [])[:top_k])
                ],
                "sparse": [
                    _result_to_item(item, index + 1)
                    for index, item in enumerate((hybrid_result.sparse_results or [])[:top_k])
                ],
                "rrf": [
                    _result_to_item(item, index + 1)
                    for index, item in enumerate((hybrid_result.results or [])[:top_k])
                ],
                "rerank": [
                    _result_to_item(item, index + 1)
                    for index, item in enumerate(final_results)
                ],
            },
            "mcp_tool_call": {
                "server": "modular-rag-mcp-server",
                "tool": "query_knowledge_hub",
                "arguments": {
                    "query": query,
                    "top_k": top_k,
                    "collection": effective_collection,
                },
                "status": "ready",
            },
        }

    async def collections(self) -> dict[str, Any]:
        _ensure_project_path()
        from src.core.settings import resolve_path
        from src.mcp_server.tools.list_collections import (
            ListCollectionsConfig,
            ListCollectionsTool,
        )

        persist_directory = resolve_path(self.settings.vector_store.persist_directory)
        tool = ListCollectionsTool(
            settings=self.settings,
            config=ListCollectionsConfig(persist_directory=str(persist_directory)),
        )
        collections = await asyncio.to_thread(tool.list_collections, True)
        return {
            "engine": "modular",
            "collections": [
                {
                    "collection": item.name,
                    "docs": item.count or 0,
                    "chunks": item.count or 0,
                    "metadata": item.metadata or {},
                }
                for item in collections
            ],
        }

    async def ingest(
        self,
        path: str,
        collection: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        _ensure_project_path()
        from src.core.trace import TraceCollector, TraceContext
        from src.ingestion.pipeline import IngestionPipeline

        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise ModularRAGError(f"ingest path does not exist: {target}")
        effective_collection = collection or self.settings.vector_store.collection_name or "default"

        def _discover_files() -> list[Path]:
            if target.is_file():
                return [target]
            return sorted(set(target.rglob("*.pdf")) | set(target.rglob("*.PDF")))

        def _run():
            pipeline = IngestionPipeline(
                settings=self.settings,
                collection=effective_collection,
                force=force,
            )
            collector = TraceCollector()
            results = []
            for file_path in _discover_files():
                trace = TraceContext(trace_type="ingestion")
                trace.metadata["source_path"] = str(file_path)
                result = pipeline.run(str(file_path), trace=trace)
                collector.collect(trace)
                results.append(result.to_dict())
            return results

        results = await asyncio.to_thread(_run)
        return {
            "engine": "modular",
            "collection": effective_collection,
            "processed": len(results),
            "successful": sum(1 for item in results if item.get("success")),
            "failed": sum(1 for item in results if not item.get("success")),
            "results": results,
        }

    async def evaluation(
        self,
        collection: str | None = None,
        top_k: int = 10,
        test_set_path: str | None = None,
    ) -> dict[str, Any]:
        _ensure_project_path()
        from src.libs.evaluator.evaluator_factory import EvaluatorFactory
        from src.observability.evaluation.eval_runner import EvalRunner

        effective_collection = collection or self.settings.vector_store.collection_name or "default"
        test_set = Path(
            test_set_path
            or self.root / "tests" / "fixtures" / "golden_test_set.json"
        ).expanduser()

        def _run():
            hybrid_search, reranker = self._build_components(effective_collection)
            evaluator = EvaluatorFactory.create(self.settings)
            runner = EvalRunner(
                settings=self.settings,
                hybrid_search=hybrid_search,
                evaluator=evaluator,
                reranker=reranker,
            )
            return runner.run(
                test_set_path=str(test_set),
                top_k=top_k,
                collection=effective_collection,
            )

        report = await asyncio.to_thread(_run)
        return {"engine": "modular", **report.to_dict()}

    async def ragas_score(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run no-reference Ragas metrics with Qwen/DashScope-compatible clients."""
        if not contexts:
            raise ModularRAGError("Ragas requires at least one retrieved context")
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ModularRAGError("DASHSCOPE_API_KEY is required for Qwen Ragas evaluation")

        def _run() -> dict[str, float]:
            # Ragas 0.4 imports a legacy LangChain VertexAI path that newer
            # langchain-community no longer ships. We do not use VertexAI here;
            # this shim only keeps the optional import path from aborting.
            import types

            vertexai_mod = "langchain_community.chat_models.vertexai"
            if vertexai_mod not in sys.modules:
                module = types.ModuleType(vertexai_mod)

                class ChatVertexAI:  # pragma: no cover - import shim only
                    pass

                module.ChatVertexAI = ChatVertexAI
                sys.modules[vertexai_mod] = module

            from openai import AsyncOpenAI
            from ragas.embeddings import OpenAIEmbeddings
            from ragas.llms import llm_factory
            from ragas.metrics.collections import (
                AnswerRelevancy,
                ContextPrecisionWithoutReference,
                Faithfulness,
            )

            selected = metrics or ["faithfulness", "answer_relevancy", "context_precision"]
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            llm = llm_factory("qwen-plus", client=client, max_tokens=4096)
            embeddings = OpenAIEmbeddings(model="text-embedding-v4", client=client)
            scores: dict[str, float] = {}
            for metric in selected:
                name = metric.strip().lower()
                if name == "faithfulness":
                    result = Faithfulness(llm=llm).score(
                        user_input=query,
                        response=answer,
                        retrieved_contexts=contexts,
                    )
                elif name == "answer_relevancy":
                    result = AnswerRelevancy(llm=llm, embeddings=embeddings).score(
                        user_input=query,
                        response=answer,
                    )
                elif name == "context_precision":
                    result = ContextPrecisionWithoutReference(llm=llm).score(
                        user_input=query,
                        response=answer,
                        retrieved_contexts=contexts,
                    )
                else:
                    continue
                scores[name] = float(result.value) if result.value is not None else 0.0
            return scores

        started = time.perf_counter()
        scores = await asyncio.to_thread(_run)
        return {
            "engine": "modular",
            "provider": "ragas",
            "llm": "qwen-plus",
            "embedding": "text-embedding-v4",
            "metrics": scores,
            "latency_s": round(time.perf_counter() - started, 3),
        }


_bridge: ModularRAGBridge | None = None


def get_modular_bridge() -> ModularRAGBridge:
    global _bridge
    if _bridge is None:
        _bridge = ModularRAGBridge()
    return _bridge
