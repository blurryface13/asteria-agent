"""Qwen/DashScope adapters for the external Modular RAG engine."""
from __future__ import annotations

import os
from typing import Any


QWEN_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _dashscope_key(explicit: str | None = None) -> str:
    api_key = explicit or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "DashScope API key not provided. Set DASHSCOPE_API_KEY in the environment."
        )
    return api_key


def register_qwen_providers() -> None:
    """Register Qwen text and vision providers in the external LLMFactory."""
    from src.libs.llm.llm_factory import LLMFactory
    from src.libs.llm.openai_llm import OpenAILLM
    from src.libs.llm.openai_vision_llm import OpenAIVisionLLM
    from src.libs.reranker.base_reranker import BaseReranker
    from src.libs.reranker.reranker_factory import RerankerFactory

    class QwenLLM(OpenAILLM):
        """OpenAI-compatible Qwen text provider via DashScope."""

        def __init__(self, settings: Any, **kwargs: Any) -> None:
            llm_settings = getattr(settings, "llm", None)
            api_key = kwargs.pop(
                "api_key",
                getattr(llm_settings, "api_key", None) if llm_settings else None,
            )
            base_url = kwargs.pop(
                "base_url",
                getattr(llm_settings, "base_url", None) if llm_settings else None,
            )
            super().__init__(
                settings=settings,
                api_key=_dashscope_key(api_key),
                base_url=base_url or QWEN_COMPAT_BASE_URL,
                **kwargs,
            )

    class QwenVisionLLM(OpenAIVisionLLM):
        """OpenAI-compatible Qwen vision provider via DashScope."""

        def __init__(self, settings: Any, **kwargs: Any) -> None:
            vision_settings = getattr(settings, "vision_llm", None)
            api_key = kwargs.pop(
                "api_key",
                getattr(vision_settings, "api_key", None) if vision_settings else None,
            )
            base_url = kwargs.pop(
                "base_url",
                getattr(vision_settings, "base_url", None) if vision_settings else None,
            )
            super().__init__(
                settings=settings,
                api_key=_dashscope_key(api_key),
                base_url=base_url or QWEN_COMPAT_BASE_URL,
                **kwargs,
            )

    class QwenReranker(BaseReranker):
        """DashScope qwen3-rerank provider for candidate reranking."""

        DEFAULT_RERANK_URL = (
            "https://dashscope.aliyuncs.com/api/v1/services/rerank/"
            "text-rerank/text-rerank"
        )

        def __init__(self, settings: Any, **kwargs: Any) -> None:
            self.settings = settings
            self.model = (
                kwargs.get("model")
                or getattr(getattr(settings, "rerank", None), "model", None)
                or "qwen3-rerank"
            )
            self.api_key = _dashscope_key(kwargs.get("api_key"))
            self.endpoint = kwargs.get("endpoint") or os.getenv(
                "DASHSCOPE_RERANK_URL",
                self.DEFAULT_RERANK_URL,
            )

        def rerank(self, query: str, candidates: list[dict], trace=None, **kwargs: Any) -> list[dict]:
            self.validate_query(query)
            self.validate_candidates(candidates)
            import httpx

            top_n = min(int(kwargs.get("top_k") or len(candidates)), len(candidates))
            documents = [
                str(candidate.get("text") or candidate.get("content") or "")[:4000]
                for candidate in candidates
            ]
            payload = {
                "model": self.model,
                "input": {
                    "query": query,
                    "documents": documents,
                },
                "parameters": {
                    "top_n": top_n,
                    "return_documents": False,
                },
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            with httpx.Client(timeout=60.0) as client:
                response = client.post(self.endpoint, json=payload, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Qwen rerank failed ({response.status_code}): {response.text[:500]}"
                )

            data = response.json()
            ranked = []
            seen = set()
            for item in data.get("output", {}).get("results", []):
                index = int(item["index"])
                if 0 <= index < len(candidates):
                    candidate = candidates[index].copy()
                    candidate["rerank_score"] = float(item.get("relevance_score", 0.0))
                    ranked.append(candidate)
                    seen.add(index)

            # Preserve any candidates omitted by top_n after the reranked prefix.
            ranked.extend(candidate for i, candidate in enumerate(candidates) if i not in seen)
            return ranked

    LLMFactory.register_provider("qwen", QwenLLM)
    LLMFactory.register_provider("dashscope", QwenLLM)
    LLMFactory.register_vision_provider("qwen", QwenVisionLLM)
    LLMFactory.register_vision_provider("dashscope", QwenVisionLLM)
    RerankerFactory.register_provider("qwen_rerank", QwenReranker)
    RerankerFactory.register_provider("qwen3_rerank", QwenReranker)
