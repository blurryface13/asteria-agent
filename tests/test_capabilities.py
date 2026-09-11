import asyncio

import pytest

from asteria_researcher.capabilities import (
    IntentResult,
    IntentRouter,
    SourceMode,
    TaskIntent,
    TaskSpec,
    build_default_registry,
)


def test_default_router_infers_academic_research_without_selector():
    result = asyncio.run(IntentRouter().route("整理近三年的 Agent 评测论文并写一份带引用的综述"))

    assert result.intent == TaskIntent.ACADEMIC_RESEARCH.value
    assert result.source_mode == SourceMode.ONLINE
    assert "citation_verification" in result.required_skills


def test_router_detects_offline_rag_and_experiment_intents():
    router = IntentRouter()

    async def run():
        return (
            await router.route("基于本地知识库回答这篇论文中的方法问题"),
            await router.route("在 GPU 上复现实验并读取 checkpoint 指标"),
        )

    rag, experiment = asyncio.run(run())

    assert rag.intent == TaskIntent.OFFLINE_RAG.value
    assert experiment.intent == TaskIntent.EXPERIMENT.value
    assert experiment.source_mode == SourceMode.OFFLINE


def test_task_spec_is_constructed_from_intent_result():
    result = IntentResult(
        intent="academic_research",
        confidence=0.9,
        required_skills=["survey_writing", "survey_writing"],
        rationale="test",
    )
    task = TaskSpec.from_intent("写一份综述", result, project_id="demo")

    assert task.intent == "academic_research"
    assert task.required_skills == ["survey_writing"]
    assert task.metadata["intent_confidence"] == 0.9
    assert task.project_id == "demo"


def test_default_registry_resolves_fine_grained_academic_skills():
    registry = build_default_registry()
    skills = registry.resolve_skills(TaskIntent.ACADEMIC_RESEARCH.value)
    skill_ids = {skill.id for skill in skills}

    assert {"academic_research", "literature_search", "survey_writing", "report_writing"}.issubset(skill_ids)
    assert "experiment_execution" not in skill_ids

    assert {"report_structure_check", "citation_audit", "latex_compile"}.issubset(registry.tools)


def test_registry_rejects_duplicate_capability_ids():
    registry = build_default_registry()
    with pytest.raises(ValueError, match="duplicate skill id"):
        registry.register_skill(registry.get_skill("academic_research"))


def test_router_accepts_injected_structured_classifier():
    async def classifier(_: str) -> IntentResult:
        return IntentResult(
            intent=TaskIntent.OFFLINE_RAG.value,
            confidence=0.99,
            source_mode=SourceMode.OFFLINE,
            required_skills=["offline_rag_qa"],
        )

    result = asyncio.run(IntentRouter(classifier=classifier).route("anything"))

    assert result.intent == TaskIntent.OFFLINE_RAG.value
    assert result.confidence == 0.99
