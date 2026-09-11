"""Replay recorded public research evidence through assessment and publishing.

Not an end-to-end search test. Uses the configured LLM and (when enabled)
embedding provider. Input must be a previously collected local review folder.
"""
import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.library import canonical
from asteria_researcher.agentic.sufficiency import ReviewPlan, validate_contract
from backend.server.agentic_runner import configured_model


async def run(args):
    load_dotenv()
    source = Path(args.evidence).resolve()
    plan_path = Path(args.plan).resolve()
    root = Path("outputs").resolve()
    if root not in source.parents or root not in plan_path.parents:
        raise ValueError("Replay inputs must be existing outputs artifacts")
    metadata = json.loads((source / "run.json").read_text())
    plan = ReviewPlan.model_validate_json(plan_path.read_text())
    validate_contract(plan, metadata["task"])
    from asteria_researcher.config.config import Config
    from asteria_researcher.memory.embeddings import Memory
    cfg = Config()
    embeddings = Memory(cfg.embedding_provider, cfg.embedding_model, **cfg.embedding_kwargs).get_embeddings()
    async def emit(kind, value):
        if kind == "agent_action":
            print(value["tool"], value["status"], value["purpose"], value.get("error", ""), flush=True)
    runtime = AutonomousReview(configured_model(), embeddings, emit, None)
    runtime.query, runtime.plan = metadata["task"], plan.model_dump()
    graph = json.loads((source / "citations.json").read_text())
    runtime.library.nodes = {n["id"]: n for n in graph["nodes"]}
    runtime.library.edges = {(e["source"], e["target"]): e for e in graph["edges"]}
    for path in source.glob("paper-*.json"):
        paper = json.loads(path.read_text())
        runtime.library.papers[canonical(paper["url"])] = paper
    runtime.evidence = json.loads((source / "evidence.json").read_text())
    events = [json.loads(line) for line in (source / "events.jsonl").read_text().splitlines()]
    runtime.successful_searches = sum(e["tool"] == "search" and e["status"] == "completed" and bool(e.get("result")) for e in events)
    (runtime.folder / "replay.json").write_text(json.dumps({"kind": "sufficiency_writer_replay",
        "evidence_source": str(source), "plan_source": str(plan_path), "not_end_to_end": True}, indent=2))
    result = await runtime.lead_checkpoint()
    if not result or result["status"] != "completed":
        print("CORE GAPS", runtime.assessment_gaps(runtime.assessments[-1]), flush=True)
        return
    report = await runtime.write_report(result["summary"])
    from asteria_researcher.agentic.latex import publish
    artifacts = await publish(report, Path("outputs"))
    (runtime.folder / "replay-artifacts.json").write_text(json.dumps(artifacts, indent=2))
    print("REPLAY PASS", str(runtime.folder), json.dumps(artifacts), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--plan", required=True)
    asyncio.run(run(parser.parse_args()))
