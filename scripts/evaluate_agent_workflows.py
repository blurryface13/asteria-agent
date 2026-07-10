"""Run regression evaluation across Basic and LangGraph research workflows.

The script intentionally separates retrieval evaluation from agent evaluation:
it measures plan coverage, citation support against each run's retrieved
evidence, and end-to-end completion/latency for comparable research tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import json_repair


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from asteria_researcher.config.config import Config
from asteria_researcher.utils.enum import Tone
from asteria_researcher.utils.llm import create_chat_completion
from backend.report_type.basic_report.basic_report import BasicReport
from multi_agents.agents import ChiefEditorAgent
from multi_agents.evaluation import (
    AgentEvalResult,
    cited_claims,
    count_citations,
    load_cases,
    outline_coverage,
)


GOLDEN_PATH = PROJECT_ROOT / "eval" / "agent_golden.json"
OUT_DIR = PROJECT_ROOT / "outputs" / "agent_eval"
CHECKPOINT_PATH = OUT_DIR / "agent_eval_checkpoint.json"


def load_multi_agent_task() -> dict[str, Any]:
    task = json.loads((PROJECT_ROOT / "multi_agents" / "task.json").read_text(encoding="utf-8"))
    task.update(
        {
            "include_human_feedback": False,
            "follow_guidelines": False,
            "publish_formats": {"markdown": False, "pdf": False, "docx": False},
            "verbose": False,
        }
    )
    return task


async def run_basic(query: str) -> tuple[str, str]:
    report = BasicReport(
        query=query,
        query_domains=[],
        report_type="research_report",
        report_source="web",
        source_urls=[],
        document_urls=[],
        tone=Tone.Objective,
        config_path="default",
        websocket=None,
    )
    output = await report.run()
    return output, str(report.asteria_researcher.context)


async def run_multi_agent(query: str, perspectives_enabled: bool) -> tuple[str, str]:
    task = load_multi_agent_task()
    task.update({"query": query, "perspective_guided_research": perspectives_enabled})
    result = await ChiefEditorAgent(task=task, tone=Tone.Objective).run_research_task()
    return result.get("report", ""), str(result.get("research_data", ""))


async def judge_citation_support(claims: list[str], evidence: str) -> float | None:
    if not claims or not evidence.strip():
        return None

    cfg = Config()
    prompt = f"""Judge whether each cited claim is supported by the retrieved research evidence.
Return JSON only: {{"supported": [true, false, ...]}}. Do not reward plausible but unsupported claims.

Claims:
{json.dumps(claims, ensure_ascii=False)}

Retrieved evidence:
{evidence[:18000]}"""
    response = await create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=cfg.smart_llm_model,
        llm_provider=cfg.smart_llm_provider,
        temperature=0,
        max_tokens=300,
        llm_kwargs=cfg.llm_kwargs,
    )
    try:
        verdict = json_repair.loads(response)
    except Exception:
        return None
    supported = verdict.get("supported", [])
    if not isinstance(supported, list) or not supported:
        return None
    return sum(bool(value) for value in supported[:len(claims)]) / min(len(supported), len(claims))


async def evaluate_case(case, variant: str, judge_citations: bool) -> AgentEvalResult:
    started = time.perf_counter()
    if variant == "basic":
        report, evidence = await run_basic(case.query)
    elif variant == "multi_agent":
        report, evidence = await run_multi_agent(case.query, perspectives_enabled=False)
    elif variant == "multi_agent_perspectives":
        report, evidence = await run_multi_agent(case.query, perspectives_enabled=True)
    else:
        raise ValueError(f"Unknown agent variant: {variant}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / f"{case.case_id}_{variant}.md"
    report_path.write_text(report, encoding="utf-8")
    claims = cited_claims(report)
    citation_support = await judge_citation_support(claims, evidence) if judge_citations else None
    return AgentEvalResult(
        case_id=case.case_id,
        variant=variant,
        outline_coverage=outline_coverage(report, case.expected_sections),
        citation_count=count_citations(report),
        citation_support_precision=citation_support,
        success=len(report.strip()) >= 300,
        latency_s=round(time.perf_counter() - started, 3),
        report_path=str(report_path),
    )


async def run(variants: list[str], limit: int | None, judge_citations: bool) -> dict[str, Any]:
    cases = load_cases(json.loads(GOLDEN_PATH.read_text(encoding="utf-8")))
    if limit is not None:
        cases = cases[:limit]

    results: list[AgentEvalResult] = []
    for variant in variants:
        for case in cases:
            results.append(await evaluate_case(case, variant, judge_citations))
            CHECKPOINT_PATH.write_text(
                json.dumps(
                    {
                        "cases": len(cases),
                        "variants": variants,
                        "results": [row.to_dict() for row in results],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    summary: dict[str, dict[str, float]] = {}
    for variant in variants:
        rows = [row for row in results if row.variant == variant]
        if not rows:
            continue
        judged = [row.citation_support_precision for row in rows if row.citation_support_precision is not None]
        latencies = sorted(row.latency_s for row in rows)
        # nearest-rank P95; with small n this degenerates to max - reported as-is
        p95_index = max(0, min(len(latencies) - 1, int(round(0.95 * len(latencies))) - 1))
        summary[variant] = {
            "outline_coverage": sum(row.outline_coverage for row in rows) / len(rows),
            "citation_count": sum(row.citation_count for row in rows) / len(rows),
            "citation_support_precision": sum(judged) / len(judged) if judged else None,
            "task_success_rate": sum(row.success for row in rows) / len(rows),
            "average_latency_s": sum(row.latency_s for row in rows) / len(rows),
            "p95_latency_s": latencies[p95_index],
        }

    report = {"cases": len(cases), "variants": variants, "summary": summary, "results": [row.to_dict() for row in results]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "agent_eval_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", nargs="+", default=["basic", "multi_agent", "multi_agent_perspectives"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--judge-citations", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.variants, args.limit, args.judge_citations)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
