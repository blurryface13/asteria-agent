"""ReAct loop for the watermark experiment agent.

Same loop shape as backend/doc_agent/react_agent.py (kept separate for now so
the two agents evolve independently; unifying into a shared runner is a known
follow-up). The LLM orchestrates a real CV experiment: it decides which lab
tool to call each turn until the robustness experiment is complete, then
writes a structured experiment report.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from openai import AsyncOpenAI

from .tools import LabSession, registry

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a research assistant running digital-watermarking experiments on "
    "real models (not simulations - every tool call executes real embedding/"
    "distortion/decoding).\n\n"
    "You will be given an EXPERIMENT PROTOCOL (a declarative SOP). Follow its "
    "objective, steps, control groups and success criteria, deciding yourself "
    "which tool to call at each turn and adapting when a tool fails.\n\n"
    "When the experiment is complete, stop calling tools and write a concise "
    "experiment report in Markdown that satisfies the protocol's success "
    "criteria. Report only numbers you actually observed from tool results - "
    "never invent values."
)

PROTOCOL_DIR = Path(__file__).resolve().parent / "protocols"


def load_protocol(name: str) -> str:
    """Load a declarative experiment protocol (YAML kept as text - the agent
    reads it, we don't parse it into code; that's the point)."""
    path = PROTOCOL_DIR / f"{name}.yaml"
    if not path.exists():
        available = [p.stem for p in PROTOCOL_DIR.glob("*.yaml")]
        raise FileNotFoundError(f"protocol '{name}' not found; available: {available}")
    return path.read_text(encoding="utf-8")


async def run_experiment(session: LabSession, instruction: str,
                         protocol: str | None = None,
                         max_steps: int = 10) -> dict:
    client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                         base_url="https://api.deepseek.com")
    user_content = instruction
    if protocol:
        user_content = (f"EXPERIMENT PROTOCOL:\n{load_protocol(protocol)}\n\n"
                        f"Additional instruction from the user: {instruction}")
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]
    tools = registry.schemas()
    started = time.perf_counter()
    tool_call_count = 0

    for step in range(max_steps):
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=1600,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            session.trace.append({"type": "final", "report": msg.content or ""})
            return {
                "status": "done",
                "report": msg.content or "",
                "trace": session.trace,
                "metrics": _run_metrics(session, started, step, tool_call_count),
            }

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            tool_call_count += 1
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            session.trace.append({"type": "action", "step": step + 1,
                                  "tool": tc.function.name, "args": args,
                                  "thought": msg.content or ""})
            t0 = time.perf_counter()
            try:
                observation = await registry.dispatch(tc.function.name, args, context=session)
            except Exception as e:
                observation = {"error": str(e)}
                logger.warning(f"lab tool {tc.function.name} failed: {e}")
            session.trace.append({"type": "observation", "tool": tc.function.name,
                                  "elapsed_s": round(time.perf_counter() - t0, 2),
                                  "result": observation})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(observation, ensure_ascii=False)[:4000],
            })

    session.trace.append({"type": "final", "report": "step limit reached"})
    return {"status": "max_steps", "report": "", "trace": session.trace,
            "metrics": _run_metrics(session, started, max_steps, tool_call_count)}


def _run_metrics(session: LabSession, started: float, steps: int, tool_calls: int) -> dict:
    return {
        "end_to_end_s": round(time.perf_counter() - started, 2),
        "react_steps": steps + 1,
        "tool_calls": tool_calls,
        "session_id": session.session_id,
    }
