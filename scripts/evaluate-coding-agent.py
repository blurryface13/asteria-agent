"""Isolated live acceptance: Coding Agent behavior and a no-code Research regression.

Loads existing dotenv files by path without copying their contents. Creates only
new outputs/coding-agent-eval-* folders and Docker scratch containers. Does not
start/replace the live API/Worker, alter user workspaces, or change model settings.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


CASES = ("coding_create", "coding_repair", "research_regression")


async def run(args):
    from dotenv import load_dotenv
    for path in args.env_file:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        load_dotenv(path, override=True)

    from backend.server.agentic_runner import configured_model
    from asteria_researcher.agentic.autonomous import AutonomousReview
    from asteria_researcher.agentic.coding import run_coding
    from asteria_researcher.agentic.collaboration import Assignment
    from asteria_researcher.agentic.experiment_tools import build_experiment_tools, DockerExperimentWorkspace
    from asteria_researcher.agentic.repository_tools import repository_tools
    from asteria_researcher.utils.usage_context import track_usage_stage

    selected = CASES if args.case == "all" else (args.case,)
    if any(case.startswith("coding_") for case in selected):
        if not args.live or not args.allow_local_docker:
            raise ValueError("Live coding evaluation requires --live and --allow-local-docker")
        os.environ["ASTERIA_EXPERIMENT_EXECUTOR"] = "local_docker"

    folder = ROOT / "outputs" / ("coding-agent-eval-" + uuid4().hex[:10])
    folder.mkdir(parents=True)
    raw_model = configured_model()
    model_calls = 0
    records = []
    started = time.monotonic()

    async def model(system, user):
        nonlocal model_calls
        if model_calls >= args.max_model_calls:
            raise RuntimeError("Evaluation model-call budget exhausted")
        model_calls += 1
        return await raw_model(system, user if isinstance(user, str) else json.dumps(user, ensure_ascii=False))

    async def emit(*parts, **kwargs):
        if len(parts) >= 4:
            agent, tool, status, purpose = parts[:4]
            records.append({"agent": agent, "tool": tool, "status": status, "purpose": str(purpose)[:160]})
        elif len(parts) == 2 and parts[0] == "agent_action" and isinstance(parts[1], dict):
            action = parts[1]
            records.append({key: action.get(key) for key in ("agent", "tool", "status", "purpose")})

    async def approve(_question):
        return "确认"  # Scope confirmation only; no workspace write approval.

    async def coding_case(case):
        scratch = folder / case / "scratch"
        if case == "coding_repair":
            workspace = DockerExperimentWorkspace(scratch)
            workspace.write({"path": "broken.py", "content":
                "from pathlib import Path\nvalue = 1 / 0\nPath('result.txt').write_text(str(value))\nprint(value)\n"})
            prompt = ("请先读取隔离实验区的 broken.py，再实际运行定位错误；修改该实验区文件，"
                      "使它输出 42 并生成 result.txt，然后重新运行核验。原工作区不得改动。")
        else:
            prompt = ("只在隔离实验区编写 demo.py，运行后输出 42 并生成 result.txt。"
                      "请检查真实退出码与产物，不要声称修改了原工作区。")
        assignment = Assignment(name=case, role="coding", objective=prompt,
                                goal_ids=["c1", "c2"], focus="隔离实验区的代码与实际执行",
                                expected_output="代码、运行观察、结果产物及原工作区状态")
        async def no_research(*_):
            raise RuntimeError("These self-contained coding probes do not require paper delegation")
        with track_usage_stage("coding_subagent"):
            result = await run_coding(assignment, model, build_experiment_tools(scratch), no_research, emit,
                                      max_turns=18, allow_research_request=False,
                                      context={"goals": [{"id": "c1", "kind": "code_change"},
                                                         {"id": "c2", "kind": "experiment_execution"}]})
        runs = [t["result"] for t in result.get("tool_results", []) if t["tool"] == "run_experiment_command"]
        result_file = scratch / "result.txt"
        has_result = result_file.is_file() and result_file.read_text().strip() == "42"
        failures = sum(row.get("exit_code", 0) != 0 for row in runs)
        passed = (result.get("status") == "completed" and result.get("execution_performed") and
                  has_result and (case != "coding_repair" or failures >= 1))
        case_dir = folder / case
        case_dir.mkdir(exist_ok=True)
        (case_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return {"case": case, "passed": bool(passed), "status": result.get("status"),
                "tool_calls": len(result.get("tool_traces", [])), "runs": len(runs),
                "failed_runs": failures, "result_42": has_result,
                "note": "Live isolated Docker run; original workspace was never mounted."}

    async def research_case():
        prompt = ("请阅读 ReAct（https://arxiv.org/abs/2210.03629）和 AutoGen "
                  "（https://arxiv.org/abs/2308.08155）的原文，比较两者的任务循环与多智能体协作设计，"
                  "写约900字中文研究综述。明确各自边界并在正文标出来源；本任务无需运行代码或修改文件。")
        runtime = AutonomousReview(model, None, emit, approve, folder, online_rag=False,
                                   max_actions=42, coding_tools=repository_tools())
        report = await runtime.run(prompt)
        cited = all(url in report for url in ("2210.03629", "2308.08155"))
        passed = bool(report.strip() and cited and not runtime.coding_results and
                      (runtime.folder / "report-with-citations.md").is_file())
        return {"case": "research_regression", "passed": passed,
                "status": json.loads((runtime.folder / "run.json").read_text())["status"],
                "read_papers": len(runtime.library.papers), "report_chars": len(report),
                "both_sources_cited": cited, "coding_children": len(runtime.coding_results),
                "report_path": str(runtime.folder / "report-with-citations.md")}

    for case in selected:
        calls_before = model_calls
        try:
            outcome = await asyncio.wait_for(
                research_case() if case == "research_regression" else coding_case(case), args.timeout)
        except Exception as error:
            outcome = {"case": case, "passed": False, "status": "error",
                       "error_type": type(error).__name__, "error_summary": str(error)[:400]}
        outcome["model_calls"] = model_calls - calls_before
        outcome["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (folder / (case + ".json")).write_text(json.dumps(outcome, ensure_ascii=False, indent=2))
        print(json.dumps(outcome, ensure_ascii=False), flush=True)
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "commit": os.getenv("ASTERIA_BUILD_REVISION", "local"),
               "cases": selected, "model_calls": model_calls, "elapsed_seconds": round(time.monotonic() - started, 2),
               "results": {case: json.loads((folder / (case + ".json")).read_text()) for case in selected},
               "events": len(records), "root": str(folder)}
    (folder / "events.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("SUMMARY " + str(folder / "summary.json"), flush=True)
    return all(row["passed"] for row in summary["results"].values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=(*CASES, "all"), default="all")
    parser.add_argument("--env-file", action="append", default=[])
    parser.add_argument("--live", action="store_true", help="Allows configured paid model calls")
    parser.add_argument("--allow-local-docker", action="store_true", help="Allows isolated Docker command execution")
    parser.add_argument("--max-model-calls", type=int, default=70)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if not args.live:
        parser.error("Real-model evaluation requires --live")
    if not asyncio.run(run(args)):
        raise SystemExit(1)
