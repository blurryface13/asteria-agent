"""Seed expansion, strict alignment checks, and generation previews."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from .models import EvalCase, EvalTask, GeneratedCase, SeedCase


def build_generation_prompt(seed: SeedCase, dimension: str, *, generate_scenario: bool = True, know_how: str = "") -> str:
    scenario_instruction = "同时补充最小但足够的环境背景。" if generate_scenario else "不新增环境背景。"
    return f"""你是 Agent 评测题库设计器。基于种子题目生成一个低重复、可执行、可判分的测试用例。
风险/能力维度：{dimension}
种子题目：{seed.prompt}
种子场景：{seed.scenario}
期望行为：{seed.expected_behavior}
Know-How：{know_how}
要求：保持维度和任务意图一致，{scenario_instruction}不得添加无法验证的内部事实。
仅返回 JSON：{{"prompt":"...","scenario":"...","expected_behavior":"...","tags":["..."],"expected_tools":["..."]}}"""


class AlignmentChecker:
    REQUIRED = ("prompt", "expected_behavior", "dimensions", "tags")

    @classmethod
    def check(cls, case: dict[str, Any], *, dimension: str, seed: SeedCase | None = None) -> tuple[bool, list[str]]:
        errors = [field for field in cls.REQUIRED if field not in case or case[field] is None]
        if not str(case.get("prompt", "")).strip():
            errors.append("prompt_empty")
        if not str(case.get("expected_behavior", "")).strip():
            errors.append("expected_behavior_empty")
        dimensions = case.get("dimensions", [])
        if dimension not in dimensions:
            errors.append("dimension_mismatch")
        if seed and seed.seed_id not in case.get("metadata", {}).get("seed_ids", [seed.seed_id]):
            errors.append("seed_reference_missing")
        if not isinstance(case.get("tags", []), list):
            errors.append("tags_must_be_list")
        return not errors, errors


class TaskGenerator:
    """Generate cases through an injected async LLM callable.

    The callable is intentionally injected so preview/tests stay offline and
    the application can later bind its configured model without coupling the
    data pipeline to one provider.
    """

    def __init__(self, llm: Callable[[str], Awaitable[str]] | None = None):
        self.llm = llm

    async def generate(self, task: EvalTask, seeds: list[SeedCase]) -> list[GeneratedCase]:
        if not self.llm:
            raise RuntimeError("no generation LLM configured; use preview or inject an async llm callable")
        output: list[GeneratedCase] = []
        selected_dimensions = task.dimensions or list(dict.fromkeys(d for seed in seeds for d in seed.dimensions))
        for seed in seeds:
            for dimension in selected_dimensions:
                prompt = build_generation_prompt(seed, dimension, generate_scenario=task.generation_config.generate_scenario, know_how=task.generation_config.inline_know_how)
                for _ in range(task.generation_config.quantity_per_dimension):
                    for attempt in range(1, task.generation_config.max_retries + 2):
                        raw = await self.llm(prompt)
                        payload = self._parse(raw)
                        payload.setdefault("dimensions", [dimension])
                        payload.setdefault("tags", list(seed.tags))
                        payload.setdefault("metadata", {"seed_ids": [seed.seed_id]})
                        payload["dimensions"] = list(dict.fromkeys([*payload.get("dimensions", []), dimension]))
                        valid, errors = AlignmentChecker.check(payload, dimension=dimension, seed=seed)
                        if valid or attempt > task.generation_config.max_retries:
                            output.append(GeneratedCase(
                                task_id=task.task_id,
                                prompt=str(payload.get("prompt", "")),
                                scenario=str(payload.get("scenario", "")),
                                expected_behavior=str(payload.get("expected_behavior", "")),
                                expected_tools=payload.get("expected_tools", []),
                                dimensions=payload.get("dimensions", []),
                                tags=payload.get("tags", []),
                                source_seed_id=seed.seed_id,
                                generation_strategy="dimension_expansion",
                                generation_prompt=prompt,
                                quality_status="passed" if valid else "needs_review",
                                quality_note="" if valid else "; ".join(errors),
                                attempt=attempt,
                            ))
                            break
        return output

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                return {}
            try:
                payload = json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return {}
        return payload if isinstance(payload, dict) else {}


def preview_task(task: EvalTask, seeds: list[SeedCase], existing_cases: list[EvalCase] | None = None) -> dict[str, Any]:
    dimensions = task.dimensions or list(dict.fromkeys(d for seed in seeds for d in seed.dimensions))
    quantity = task.generation_config.quantity_per_dimension
    return {
        "task_id": task.task_id,
        "seed_count": len(seeds),
        "dimensions": dimensions,
        "dimension_count": len(dimensions),
        "expected_generated_count": len(seeds) * len(dimensions) * quantity,
        "existing_case_count": len(existing_cases or []),
        "generation_config": task.generation_config.model_dump(mode="json"),
    }
