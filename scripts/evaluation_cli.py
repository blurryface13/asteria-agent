#!/usr/bin/env python3
"""Offline CLI for the evaluation asset loop.

Examples:
  python scripts/evaluation_cli.py import-traces eval/samples/production_trace.jsonl
  python scripts/evaluation_cli.py analyze <trace-id>
  python scripts/evaluation_cli.py preview <task-id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from asteria_researcher.evaluation.badcase import BadCaseAnalyzer, trace_to_seed
from asteria_researcher.evaluation.generation import preview_task
from asteria_researcher.evaluation.models import BadCase, EvalTask, SeedCase, TraceEnvelope
from asteria_researcher.evaluation.store import EvaluationStore
from asteria_researcher.evaluation.trace import TraceIngestor


def main() -> None:
    parser = argparse.ArgumentParser(description="Asteria Agent evaluation asset CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-traces")
    imp.add_argument("path", type=Path)
    imp.add_argument("--batch-id")
    analyze = sub.add_parser("analyze")
    analyze.add_argument("trace_id")
    seed = sub.add_parser("seed-from-badcase")
    seed.add_argument("badcase_id")
    prev = sub.add_parser("preview")
    prev.add_argument("task_id")
    args = parser.parse_args()
    store = EvaluationStore()

    if args.command == "import-traces":
        traces = TraceIngestor().ingest_jsonl(args.path.read_text(encoding="utf-8"), batch_id=args.batch_id, source_system="cli")
        for trace in traces:
            store.upsert("traces", trace)
        print(json.dumps({"count": len(traces), "trace_ids": [item.trace_id for item in traces]}, ensure_ascii=False, indent=2))
    elif args.command == "analyze":
        raw = store.get("traces", args.trace_id)
        if not raw:
            raise SystemExit(f"trace not found: {args.trace_id}")
        badcase = BadCaseAnalyzer().analyze(TraceEnvelope.model_validate(raw))
        if not badcase:
            print(json.dumps({"created": False}, ensure_ascii=False))
            return
        store.upsert("badcases", badcase)
        print(json.dumps(badcase.model_dump(mode="json"), ensure_ascii=False, indent=2))
    elif args.command == "seed-from-badcase":
        raw = store.get("badcases", args.badcase_id)
        if not raw:
            raise SystemExit(f"badcase not found: {args.badcase_id}")
        value = trace_to_seed(BadCase.model_validate(raw))
        store.upsert("seeds", value)
        print(json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        raw = store.get("tasks", args.task_id)
        if not raw:
            raise SystemExit(f"task not found: {args.task_id}")
        task = EvalTask.model_validate(raw)
        seeds = [SeedCase.model_validate(item) for item in store.list("seeds") if item.get("seed_id") in task.seed_ids]
        print(json.dumps(preview_task(task, seeds), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
