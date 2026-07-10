"""Subprocess bridge to the watermark-mcp experiment CLI.

The watermarking model (PIMoG today; swappable for the user's own models)
lives in its own repo with its own torch venv. We never import torch here -
each action shells out to that venv and parses one JSON object from stdout.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

WATERMARK_ROOT = Path(os.getenv(
    "WATERMARK_MCP_ROOT", "/Users/dora/Documents/项目/code/watermark-mcp")).resolve()
PYTHON = WATERMARK_ROOT / ".venv" / "bin" / "python"


class WatermarkLabError(RuntimeError):
    pass


async def run_action(*cli_args: str, timeout: float = 300.0) -> dict:
    if not PYTHON.exists():
        raise WatermarkLabError(f"watermark venv python not found: {PYTHON}")
    proc = await asyncio.create_subprocess_exec(
        str(PYTHON), "-m", "mcp.experiment_cli", *cli_args,
        cwd=str(WATERMARK_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise WatermarkLabError(f"watermark action timed out: {cli_args[0]}")
    if proc.returncode != 0:
        tail = stderr.decode(errors="replace").strip().splitlines()[-3:]
        raise WatermarkLabError(f"watermark action failed: {' '.join(tail)}")
    # the CLI prints exactly one JSON object as its last line
    last_line = stdout.decode(errors="replace").strip().splitlines()[-1]
    return json.loads(last_line)
