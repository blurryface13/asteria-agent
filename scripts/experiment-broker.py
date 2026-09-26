"""Internal, opt-in Docker execution broker. Never expose a host port."""
from __future__ import annotations

import asyncio
import hmac
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request

from experiment_tools import DockerExperimentWorkspace


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
sessions = {}
parallel_runs = asyncio.Semaphore(2)
root = Path(os.environ.get("ASTERIA_EXPERIMENT_ROOT", "/experiments")).resolve()
volume = os.environ.get("ASTERIA_EXPERIMENT_VOLUME", "")
token = os.environ.get("ASTERIA_EXPERIMENT_BROKER_TOKEN", "")


def authorize(authorization: str | None):
    if not token or not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Unauthorized")


def workspace(session_id: str):
    if session_id not in sessions:
        # A broker restart must not orphan an in-flight Worker session. The
        # bearer token remains required at the endpoint before this lookup.
        directory = root / session_id
        if not re.fullmatch(r"[0-9a-f]{32}", session_id) or not directory.is_dir():
            raise HTTPException(404, "Unknown or expired experiment session")
        if len(sessions) >= 32:
            raise HTTPException(503, "Experiment sessions full")
        sessions[session_id] = {"workspace": DockerExperimentWorkspace(directory, volume=volume),
                                "last_used": time.monotonic()}
    entry = sessions[session_id]
    entry["last_used"] = time.monotonic()
    return entry["workspace"]


async def payload(request: Request):
    raw = await request.body()
    if len(raw) > 300_000:
        raise HTTPException(413, "Experiment request too large")
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "Expected JSON object")
    return data


@app.get("/health")
def health():
    return {"status": "ok", "sessions": len(sessions)}


@app.post("/sessions")
def create_session(authorization: str | None = Header(default=None)):
    authorize(authorization)
    now = time.monotonic()
    for key, entry in list(sessions.items()):
        if now - entry["last_used"] > 4 * 3600:
            sessions.pop(key, None)  # Keep artifacts on the named volume.
    if len(sessions) >= 32 or not volume:
        raise HTTPException(503, "Experiment sessions full or volume not configured")
    session_id = uuid4().hex
    directory = root / session_id
    directory.mkdir(parents=True, exist_ok=False)
    os.chown(directory, 65534, 65534)
    sessions[session_id] = {"workspace": DockerExperimentWorkspace(directory, volume=volume),
                            "last_used": now}
    return {"session_id": session_id}


@app.post("/sessions/{session_id}/{operation}")
async def tool(session_id: str, operation: str, request: Request,
               authorization: str | None = Header(default=None)):
    authorize(authorization)
    if operation not in {"write", "read", "files", "run"}:
        raise HTTPException(404, "Unknown experiment operation")
    target = workspace(session_id)
    data = await payload(request)
    try:
        if operation == "write":
            return target.write(data)
        if operation == "read":
            return target.read(data)
        if operation == "files":
            if data:
                raise ValueError("files takes no parameters")
            return {"status": "completed", "files": target.files()}
        async with parallel_runs:
            return await target.run(data)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except asyncio.TimeoutError:
        raise HTTPException(408, "Experiment timed out") from None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
