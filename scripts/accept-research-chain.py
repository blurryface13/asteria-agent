"""Live authenticated research acceptance; uses the configured model/search quota.

Creates a dedicated test account and task, uses the same HTTP routes as the UI,
and preserves the report/events. Never prints or saves the temporary password.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_TASK = """为10人实验室调研科研多Agent系统，形成约1600字中文综述。比较 ReAct 的推理与行动循环、AutoGen 的多Agent协作，以及 Anthropic Research 的 Lead/Search/Citation 分工；分析并行分工如何避免重复调查、长任务如何保留上下文，并给出适合实验室的实现建议与局限。优先阅读以下原始资料，必要时再补充检索，不要求穷尽文献：
https://arxiv.org/abs/2210.03629
https://arxiv.org/abs/2308.08155
https://www.anthropic.com/engineering/multi-agent-research-system
请对不同问题合理分工，区分论文结论、厂商经验和你的建议，正文给出来源；无需运行实验或修改代码。"""


async def run(args):
    import httpx
    from dotenv import load_dotenv
    from backend.auth.lab import provision
    from backend.auth.db import close_pool
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.lab", override=True)
    identity = uuid4().hex[:10]
    email, password = f"acceptance-{identity}@example.com", secrets.token_urlsafe(24)
    await provision(email, password, "科研链路验收")
    await close_pool()
    folder = ROOT / "outputs" / ("acceptance_" + identity)
    folder.mkdir(parents=True)
    run_id, last_state, after, terminal = None, None, 0, False
    started = time.monotonic()
    async with httpx.AsyncClient(base_url=args.url, timeout=30, trust_env=False) as client:
        async def request(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        login = await request("POST", "/api/auth/login", json={"email": email, "password": password})
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        conversation = await request("POST", "/api/workspace/conversations", json={"title": "Anthropic 架构端到端验收", "mode": "research"})
        task = Path(args.task_file).read_text() if args.task_file else DEFAULT_TASK
        submission = {"conversation_id": conversation["id"], "request_id": "accept-" + identity,
            "message": task, "knowledge_mode": "auto", "research_request": {
                "task": task, "report_type": "research_report", "report_source": "web",
                "tone": "Objective", "online_rag": not args.direct_read, "headers": {}, "mcp_enabled": True}}
        (folder / "request.json").write_text(json.dumps(submission, ensure_ascii=False, indent=2))
        print(json.dumps({"account": email, "conversation": conversation["id"], "output": str(folder)}), flush=True)
        try:
            await request("POST", "/api/coordinator/route", json=submission)
            while time.monotonic() - started < args.timeout:
                if not run_id:
                    turn = (await request("GET", "/api/coordinator/turn", params={"conversation_id": conversation["id"]}))["turn"]
                    if turn and turn["status"] == "completed":
                        (folder / "routing.json").write_text(json.dumps(turn, ensure_ascii=False, indent=2))
                        run_id = turn["result"].get("run_id")
                        if not run_id:
                            raise RuntimeError("Research request did not start a research Run: " + json.dumps(turn["result"], ensure_ascii=False)[:1500])
                    elif turn and turn["status"] in {"failed", "interrupted"}:
                        raise RuntimeError(str(turn.get("error")))
                if run_id:
                    current = await request("GET", f"/api/workspace/runs/{run_id}")
                    if current["status"] != last_state:
                        print(json.dumps({"run_id": run_id, "status": current["status"], "seconds": round(time.monotonic()-started)}), flush=True)
                        last_state = current["status"]
                    events = (await request("GET", f"/api/workspace/runs/{run_id}/events", params={"after": after}))["events"]
                    with (folder / "events.jsonl").open("a") as stream:
                        for event in events:
                            after = event["sequence"]
                            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                            payload = event["payload"]
                            action = payload.get("output", {})
                            if payload.get("content") == "agent_action" and isinstance(action, dict):
                                print(json.dumps({k: action.get(k) for k in ("agent", "tool", "status", "purpose")}, ensure_ascii=False), flush=True)
                    approval = current.get("approval")
                    if approval:
                        if not args.approve_plan or not approval["question"].startswith("请确认研究范围"):
                            raise RuntimeError("Task requires manual approval in the UI")
                        (folder / "approved-plan.txt").write_text(approval["question"])
                        await request("POST", f"/api/workspace/runs/{run_id}/approvals/{approval['id']}", json={"content": "确认"})
                    if current["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                        terminal = True
                        (folder / "result.json").write_text(json.dumps(current, ensure_ascii=False, indent=2))
                        if current["status"] != "completed":
                            raise RuntimeError(str(current.get("error") or current["status"]))
                        print("PASS " + str(folder / "result.json"), flush=True)
                        return
                await asyncio.sleep(2)
            raise TimeoutError("Acceptance deadline exceeded")
        finally:
            if run_id and not terminal:
                await request("POST", f"/api/workspace/runs/{run_id}/cancel")
            await request("POST", "/api/auth/logout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8018")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--approve-plan", action="store_true")
    parser.add_argument("--direct-read", action="store_true")
    parser.add_argument("--task-file")
    asyncio.run(run(parser.parse_args()))
