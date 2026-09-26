"""Export a small, safe AstaBench run packet for Git review.

Only allowlisted fields are copied. Official gated prompts, model responses,
credentials, raw Inspect logs and Asteria artifact contents stay on the host.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SAFE_EVENT = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
STATES = {"queued", "running", "waiting_approval", "completed", "failed", "cancelled", "interrupted"}


def safe_name(value: object) -> str:
    text = str(value)
    if not SAFE_NAME.fullmatch(text):
        raise ValueError("Unsafe label or sample ID")
    return text


def safe_event(value: object) -> str:
    text = str(value or "")
    return text if SAFE_EVENT.fullmatch(text) else "unknown"


def number(value: object) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def export(state_path: Path, score_path: Path, events_path: Path, out_dir: Path, label: str) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    score = json.loads(score_path.read_text(encoding="utf-8"))
    if state.get("sample_id") != score.get("sample_id") or state.get("run_id") != score.get("run_id"):
        raise ValueError("State and score identify different runs")
    status = state.get("status")
    if status not in STATES:
        raise ValueError("Unknown run status")
    usage = state.get("usage") or {}
    timing = state.get("timing") or {}
    summary = {
        "schema_version": 1,
        "benchmark": "AstaBench E2E Discovery",
        "split": "validation",
        "sample_id": safe_name(state["sample_id"]),
        "run_id": safe_name(state["run_id"]),
        "status": status,
        "score": number(score.get("score")),
        "score_method": "official_early_zero_no_judge" if status == "failed" and score.get("score") == 0 else "see_local_record",
        "official_sandbox_used": bool(state.get("official_sandbox_used")),
        "usage": {key: number(usage.get(key)) for key in
                  ("calls_recorded", "input_tokens", "output_tokens", "total_tokens")},
        "timing_seconds": {key: number(timing.get(key)) for key in
                           ("queued_seconds", "execution_seconds", "approval_seconds")},
        "artifacts": [{"kind": safe_event(item.get("kind")), "size_bytes": number(item.get("size_bytes"))}
                      for item in state.get("artifacts") or []],
        "privacy": "Allowlisted metadata only; no prompts, responses, keys, artifact paths or raw logs",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{label}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = []
    for raw in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        lines.append(json.dumps({
            "agent": safe_event(event.get("agent")),
            "tool": safe_event(event.get("tool")),
            "status": safe_event(event.get("status")),
        }, ensure_ascii=False))
    (out_dir / f"{label}.events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Exported {label}: {len(lines)} safe events")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    export(args.state, args.score, args.events, args.out, safe_name(args.label))
