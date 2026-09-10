"""Live smoke test. Consumes model/search quota; use --approve-plan for test plans only."""
import argparse
import asyncio
import json

import websockets


async def run(args):
    async with websockets.connect(args.url, max_size=8_000_000, proxy=None) as socket:
        await socket.send("start " + json.dumps({
            "task": args.task, "report_type": "research_report", "report_source": "web",
            "tone": "Objective", "headers": {}, "mcp_enabled": False, "max_search_results": 2,
        }))
        async def receive():
            while True:
                event = json.loads(await socket.recv())
                kind = event.get("type")
                if kind == "human_feedback":
                    print("HITL request received", flush=True)
                    if not args.approve_plan:
                        raise RuntimeError("Re-run with --approve-plan only after reviewing the test scope")
                    await socket.send(json.dumps({"type": "human_feedback", "content": None}))
                elif kind == "error":
                    raise RuntimeError(str(event.get("output")))
                elif kind == "path":
                    paths = event["output"]
                    if not all(paths.get(key) for key in ("tex", "latex_pdf", "md", "compile_log")):
                        raise RuntimeError("Missing scientific artifacts")
                    print("PASS", json.dumps(paths), flush=True)
                    return
                elif kind == "logs" and event.get("content") in {
                    "skill_loaded", "tool_started", "tool_completed", "revision_requested",
                    "evidence_audit", "delivery_validated", "publishing", "error",
                }:
                    print(event["content"], str(event.get("output"))[:600], flush=True)
        await asyncio.wait_for(receive(), args.timeout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--url", default="ws://127.0.0.1:8018/ws")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--approve-plan", action="store_true")
    asyncio.run(run(parser.parse_args()))
