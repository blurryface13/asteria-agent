"""Authenticated Coding Agent acceptance against the isolated QA API.

This script provisions a disposable QA account only after proving DATABASE_URL
targets the dedicated QA database. It never writes to the primary Asteria DB.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATABASE = "asteria_qa_coding_20260927"


async def run(args):
    import httpx
    from dotenv import load_dotenv

    for path in args.env_file:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        load_dotenv(path, override=True)
    source = urlsplit(os.environ.get("DATABASE_URL", ""))
    if source.scheme not in {"postgresql", "postgres"} or not source.hostname:
        raise ValueError("Valid PostgreSQL DATABASE_URL required")
    if source.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("QA acceptance requires local PostgreSQL")
    os.environ["DATABASE_URL"] = urlunsplit((source.scheme, source.netloc, "/" + DATABASE,
                                               source.query, source.fragment))
    if urlsplit(os.environ["DATABASE_URL"]).path != "/" + DATABASE:
        raise ValueError("Refusing to provision outside QA database")
    os.environ["ASTERIA_REDIS_URL"] = "redis://127.0.0.1:6379/9"
    os.environ["ASTERIA_REDIS_NAMESPACE"] = "asteria:qa:coding:20260927"

    from backend.auth.lab import provision
    from backend.auth.db import close_pool

    identity = uuid4().hex[:10]
    email = f"coding-acceptance-{identity}@example.com"
    password = secrets.token_urlsafe(24)
    await provision(email, password, "Coding QA")
    await close_pool()
    folder = ROOT / "outputs" / ("coding-http-acceptance-" + identity)
    folder.mkdir(parents=True)
    prompt = ("请编写并实际运行 Python 代码：只在隔离实验区创建 demo.py，运行后输出 42 "
              "并生成 result.txt。检查真实退出码和产物，不要修改原工作区。")
    request_id = "coding-accept-" + identity
    deadline = time.monotonic() + args.timeout
    async with httpx.AsyncClient(base_url=args.url, timeout=30, trust_env=False) as client:
        async def request(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

        login = await request("POST", "/api/auth/login", json={"email": email, "password": password})
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        try:
            conversation = await request("POST", "/api/workspace/conversations",
                                         json={"title": "隔离 Coding 入口验收", "mode": "chat"})
            await request("POST", "/api/coordinator/route", json={
                "conversation_id": conversation["id"], "request_id": request_id,
                "message": prompt, "knowledge_mode": "off"})
            while time.monotonic() < deadline:
                turn = (await request("GET", "/api/coordinator/turn", params={
                    "conversation_id": conversation["id"], "request_id": request_id}))["turn"]
                if turn and turn["status"] in {"completed", "failed", "interrupted"}:
                    break
                await asyncio.sleep(2)
            else:
                raise TimeoutError("Coding QA turn exceeded deadline")
            (folder / "turn.json").write_text(json.dumps(turn, ensure_ascii=False, indent=2))
            result = turn.get("result") or {}
            response = result.get("response") or {}
            metadata = response.get("metadata") or {}
            checks = {
                "turn_completed": turn["status"] == "completed",
                "routed_to_coding": result.get("capability") == "workspace_coding",
                "execution_performed": metadata.get("execution_performed") is True,
                "scratch_change_performed": metadata.get("scratch_change_performed") is True,
                "generated_artifacts": bool(metadata.get("generated_artifacts")),
                "no_original_workspace_approval": metadata.get("pending_approval") is not True,
            }
            summary = {"passed": all(checks.values()), "checks": checks,
                       "status": turn["status"], "capability": result.get("capability"),
                       "output": str(folder / "turn.json")}
            (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            return summary["passed"]
        finally:
            await request("POST", "/api/auth/logout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="append", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8027")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if not asyncio.run(run(args)):
        raise SystemExit(1)
