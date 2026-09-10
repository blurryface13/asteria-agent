"""Intent routing with a provider-independent fallback classifier."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from .models import IntentResult, SourceMode, TaskIntent
from .registry import CapabilityRegistry, build_default_registry

Classifier = Callable[[str], IntentResult | Awaitable[IntentResult]]


class IntentRouter:
    """Infer task intent without requiring a user-facing task-type selector.

    A structured LLM classifier can be injected later. The deterministic fallback
    keeps local development, tests, and offline operation usable today.
    """

    def __init__(self, registry: CapabilityRegistry | None = None, classifier: Classifier | None = None):
        self.registry = registry or build_default_registry()
        self.classifier = classifier

    async def route(self, user_request: str) -> IntentResult:
        request = user_request.strip()
        if not request:
            raise ValueError("user_request cannot be blank")

        if self.classifier is not None:
            result = self.classifier(request)
            if inspect.isawaitable(result):
                result = await result
            return self._validate_result(result)

        return self._fallback_route(request)

    def _fallback_route(self, request: str) -> IntentResult:
        text = request.lower()

        if any(word in text for word in ("股票", "公司", "财报", "行业", "竞品", "估值")):
            return IntentResult(
                intent=TaskIntent.COMPANY_RESEARCH.value,
                confidence=0.72,
                deliverable="research_report",
                source_mode=SourceMode.ONLINE,
                required_skills=["literature_search", "citation_verification"],
                rationale="matched company or financial research terms",
            )
        if any(word in text for word in ("训练", "实验", "复现", "运行代码", "checkpoint", "gpu")):
            return IntentResult(
                intent=TaskIntent.EXPERIMENT.value,
                confidence=0.72,
                deliverable="experiment_artifacts",
                source_mode=SourceMode.OFFLINE,
                required_skills=["experiment_execution"],
                rationale="matched experiment execution terms",
            )
        if any(word in text for word in ("数据分析", "统计", "数据集", "画图", "可视化", "指标")):
            return IntentResult(
                intent=TaskIntent.DATA_ANALYSIS.value,
                confidence=0.72,
                deliverable="analysis_report",
                source_mode=SourceMode.OFFLINE,
                required_skills=["data_analysis"],
                rationale="matched data analysis terms",
            )
        if any(word in text for word in ("知识库", "本地资料", "离线", "已有论文", "本地文档")):
            return IntentResult(
                intent=TaskIntent.OFFLINE_RAG.value,
                confidence=0.72,
                deliverable="grounded_answer",
                source_mode=SourceMode.OFFLINE,
                required_skills=["offline_rag_qa"],
                rationale="matched local knowledge-base terms",
            )

        return IntentResult(
            intent=TaskIntent.ACADEMIC_RESEARCH.value,
            confidence=0.55,
            deliverable="research_report",
            source_mode=SourceMode.ONLINE,
            required_skills=["academic_research", "literature_search", "evidence_extraction", "citation_verification", "survey_writing"],
            rationale="defaulted to the existing academic research path",
        )

    @staticmethod
    def _validate_result(result: Any) -> IntentResult:
        if isinstance(result, IntentResult):
            return result
        raise TypeError("classifier must return IntentResult")
