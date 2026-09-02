"""Adapters that execute Asteria's existing workflows under a TraceRecorder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AgentRunOutput, EvalCase
from .trace import TraceRecorder


def build_asteria_executor(variant: str = "basic"):
    """Return an async executor for ``EvaluationRunner``.

    Imports are lazy so data preview and offline ingestion do not import the
    full research stack or make model calls.
    """
    if variant not in {"basic", "multi_agent", "multi_agent_perspectives"}:
        raise ValueError(f"unsupported Asteria variant: {variant}")

    async def execute(case: EvalCase, recorder: TraceRecorder) -> AgentRunOutput:
        if variant == "basic":
            from asteria_researcher.utils.enum import Tone
            from backend.report_type.basic_report.basic_report import BasicReport

            report = BasicReport(
                query=case.prompt, query_domains=[], report_type="research_report",
                report_source="web", source_urls=[], document_urls=[], tone=Tone.Objective,
                config_path="default", websocket=None,
            )
            text = await report.run()
            return AgentRunOutput(report=text, metadata={"variant": variant, "evidence": str(report.asteria_researcher.context)})

        from multi_agents.agents import ChiefEditorAgent
        from asteria_researcher.utils.enum import Tone

        task_path = Path(__file__).resolve().parents[2] / "multi_agents" / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task.update({
            "query": case.prompt,
            "include_human_feedback": False,
            "follow_guidelines": False,
            "perspective_guided_research": variant == "multi_agent_perspectives",
            "publish_formats": {"markdown": False, "pdf": False, "docx": False},
            "verbose": False,
        })
        result: dict[str, Any] = await ChiefEditorAgent(task=task, tone=Tone.Objective).run_research_task()
        return AgentRunOutput(report=result.get("report", ""), metadata={"variant": variant, "evidence": str(result.get("research_data", ""))})

    return execute
