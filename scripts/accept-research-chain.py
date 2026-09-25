"""Live authenticated research acceptance; uses the configured model/search quota.

Creates a dedicated test account and task, uses the same HTTP routes as the UI,
and preserves the report/events. Never prints or saves the temporary password.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
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


async def verify_deliverables(client, run, *, require_matrix=False):
    """Use the authenticated download path, not merely files present on disk."""
    from urllib.parse import quote
    from pathlib import PurePosixPath
    artifacts = {item["kind"]: item for item in run.get("artifacts", [])}
    verified, downloaded = [], {}
    kinds = ['md', 'latex_pdf', 'citation_review', 'lead_decisions']
    kinds.extend(k for k in artifacts if k.startswith('chart_') or k in {'data_analysis', 'tool_calls', 'report_bundle'})
    for kind in kinds:
        item = artifacts.get(kind)
        if not item:
            raise ValueError("Missing completed-run artifact: " + kind)
        path = PurePosixPath(item["path"])
        if path.is_absolute() or not path.parts or path.parts[0] != "outputs" or ".." in path.parts:
            raise ValueError("Invalid artifact download path")
        response = await client.get("/" + quote(str(path), safe="/"))
        response.raise_for_status()
        content = response.content
        if len(content) != item["size_bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Artifact download differs from recorded content: " + kind)
        if kind == "latex_pdf" and not content.startswith(b"%PDF-"):
            raise ValueError("PDF artifact is not a PDF")
        if kind == "citation_review" and json.loads(content)["status"] != "completed":
            raise ValueError("Citation review is not complete")
        if kind.startswith('chart_') and (not content.startswith(b'\x89PNG') or 'image/png' not in response.headers.get('content-type', '')):
            raise ValueError('Chart download is not a renderable PNG')
        if kind == 'report_bundle':
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(content)) as bundle:
                if bundle.testzip() is not None or not {'report.md', 'report.tex', 'report.pdf'} <= set(bundle.namelist()):
                    raise ValueError('Report bundle is incomplete')
        downloaded[kind] = content
        verified.append({"kind": kind, "status": response.status_code, "bytes": len(content), "sha256": item["sha256"]})
    if require_matrix:
        manifest_bytes = downloaded.get('data_analysis')
        if not manifest_bytes:
            raise ValueError('Acceptance requires a downloadable data_analysis manifest')
        charts = json.loads(manifest_bytes).get('charts', [])
        report = downloaded['md'].decode('utf-8')
        matrices = [chart for chart in charts if chart.get('kind') == 'matrix']
        if not matrices or any(f"chart_{chart.get('id')}" not in artifacts or
                               f"figures/{chart.get('id')}.png" not in report
                               for chart in matrices):
            raise ValueError('Acceptance requires a delivered, report-embedded method/evidence comparison matrix')
    return verified


async def run(args):
    import httpx
    from dotenv import load_dotenv
    from backend.auth.lab import provision
    from backend.auth.db import close_pool
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.lab", override=True)
    resume = getattr(args, "resume", None)
    if resume:
        folder = Path(resume).resolve()
        if folder.parent != (ROOT / 'outputs').resolve() or not re.fullmatch(r'acceptance_[0-9a-f]{10}', folder.name):
            raise ValueError('Resume accepts only this repository’s dedicated acceptance folders')
        identity = folder.name.removeprefix('acceptance_')
        submission = json.loads((folder / 'request.json').read_text())
        from backend.auth.db import get_pool
        pool = await get_pool()
        owner = await pool.fetchval('SELECT user_email FROM workspace_conversations WHERE id=$1', submission['conversation_id'])
        if owner != f'acceptance-{identity}@example.com':
            await close_pool()
            raise ValueError('Cannot reset credentials for a non-acceptance account')
    else:
        identity = uuid4().hex[:10]
    email, password = f"acceptance-{identity}@example.com", secrets.token_urlsafe(24)
    await provision(email, password, "科研链路验收")
    await close_pool()
    folder = ROOT / "outputs" / ("acceptance_" + identity)
    folder.mkdir(parents=True, exist_ok=bool(resume))
    run_id, last_state, after, terminal = None, None, 0, False
    stage, primary_error = "routing", None
    if resume and (folder / 'events.jsonl').exists():
        after = max((json.loads(line)['sequence'] for line in (folder / 'events.jsonl').read_text().splitlines() if line.strip()), default=0)
    started = time.monotonic()
    async with httpx.AsyncClient(base_url=args.url, timeout=30, trust_env=False) as client:
        async def request(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        login = await request("POST", "/api/auth/login", json={"email": email, "password": password})
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        if resume:
            conversation = {'id': submission['conversation_id']}
            (folder / ('resume-' + uuid4().hex[:8] + '.json')).write_text(json.dumps({
                'resumed_at_epoch': time.time(), 'note': 'Observer resumed; no new task or model request submitted.'}))
        else:
            conversation = await request("POST", "/api/workspace/conversations", json={"title": "Anthropic 架构端到端验收", "mode": "research"})
            task = Path(args.task_file).read_text() if args.task_file else DEFAULT_TASK
            submission = {"conversation_id": conversation["id"], "request_id": "accept-" + identity,
                "message": task, "knowledge_mode": "auto", "research_request": {
                    "task": task, "report_type": "research_report", "report_source": "web",
                    "tone": "Objective", "online_rag": not args.direct_read, "headers": {}, "mcp_enabled": True}}
            (folder / "request.json").write_text(json.dumps(submission, ensure_ascii=False, indent=2))
        print(json.dumps({"account": email, "conversation": conversation["id"], "output": str(folder)}), flush=True)
        try:
            if not resume:
                await request("POST", "/api/coordinator/route", json=submission)
            while time.monotonic() - started < args.timeout:
                if not run_id:
                    turn = (await request("GET", "/api/coordinator/turn", params={"conversation_id": conversation["id"]}))["turn"]
                    if turn and turn["status"] in {"completed", "failed", "interrupted"}:
                        (folder / "routing.json").write_text(json.dumps(turn, ensure_ascii=False, indent=2))
                    if turn and turn["status"] == "completed":
                        run_id = turn["result"].get("run_id")
                        if not run_id:
                            raise RuntimeError("Research request did not start a research Run: " + json.dumps(turn["result"], ensure_ascii=False)[:1500])
                    elif turn and turn["status"] in {"failed", "interrupted"}:
                        raise RuntimeError(str(turn.get("error")))
                if run_id:
                    stage = "research"
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
                        stage = "delivery_verification"
                        downloads = await verify_deliverables(client, current,
                                                              require_matrix=getattr(args, 'require_matrix', False))
                        (folder / "downloads.json").write_text(json.dumps(downloads, ensure_ascii=False, indent=2))
                        print("PASS " + str(folder / "result.json"), flush=True)
                        return
                await asyncio.sleep(2)
            raise TimeoutError("Acceptance deadline exceeded")
        except Exception as error:
            primary_error = error
            # Do not serialize HTTP request objects, headers, auth tokens or raw
            # provider responses. The API's sanitized routing/run error is saved
            # separately, including failures before a research Run exists.
            (folder / "failure.json").write_text(json.dumps({
                "stage": stage, "error_type": type(error).__name__, "run_id": run_id,
                "http_status": error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "evidence": [p.name for p in (folder / "routing.json", folder / "result.json") if p.exists()],
            }, ensure_ascii=False, indent=2))
            raise
        finally:
            cleanup_errors = []
            paths = ([f"/api/workspace/runs/{run_id}/cancel"] if run_id and not terminal else [])
            for path in paths + ["/api/auth/logout"]:
                try:
                    await request("POST", path)
                except Exception as error:
                    cleanup_errors.append({"operation": "cancel" if path.endswith("/cancel") else "logout",
                                           "error_type": type(error).__name__})
            if cleanup_errors:
                (folder / "cleanup-errors.json").write_text(json.dumps(cleanup_errors, indent=2))
                if primary_error is None:
                    raise RuntimeError("Acceptance cleanup failed; see cleanup-errors.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8018")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--approve-plan", action="store_true")
    parser.add_argument("--direct-read", action="store_true")
    parser.add_argument("--task-file")
    parser.add_argument("--require-matrix", action="store_true",
                        help="Require a validated comparison matrix embedded in the final report")
    parser.add_argument("--resume", help="Resume observation of a dedicated acceptance folder; does not submit another task")
    asyncio.run(run(parser.parse_args()))
