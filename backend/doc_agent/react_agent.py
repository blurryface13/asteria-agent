"""A real ReAct / tool-calling loop for the document-editing agent.

This is NOT a fixed workflow: the LLM is given the ToolRegistry's schemas and
decides, each turn, which tool to call (Thought -> Action -> Observation), until
it produces an edit proposal or stops. Every step is recorded so the frontend
can show that the model is driving the control flow.
"""
from __future__ import annotations

import json
import logging
import os

from openai import AsyncOpenAI

from .tools import DocSession, registry

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a document-revision agent. The user wants to revise a document so its "
    "claims are accurate and grounded in a research-paper knowledge base.\n\n"
    "Work in a ReAct loop using the provided tools:\n"
    "1. read_document to load the file.\n"
    "2. search_knowledge_base to find evidence for the claim you are revising.\n"
    "3. propose_edit to produce a grounded rewrite (pass the citations you found).\n\n"
    "Rules: never propose an edit without first searching the knowledge base for "
    "supporting evidence. Only rewrite spans that exist verbatim in the document. "
    "When you have proposed the needed edit(s), reply with a short summary and stop."
)


async def run_react(session: DocSession, instruction: str, file_path: str,
                    max_steps: int = 8) -> dict:
    client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content":
            f"Document path: {file_path}\nRevision request: {instruction}\n"
            f"Start by reading the document."},
    ]
    tools = registry.schemas()

    for step in range(max_steps):
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=800,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            # LLM decided it is done (no further action)
            session.trace.append({"type": "final", "thought": msg.content or ""})
            return {"status": "done", "summary": msg.content or "", "trace": session.trace,
                    "edits": _collect_edits(session)}

        # Record the assistant turn (with its tool calls) then execute each call
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
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            session.trace.append({"type": "action", "step": step + 1, "tool": name,
                                  "thought": msg.content or "", "args": args})
            try:
                result = await registry.dispatch(name, args, context=session)
                observation = result
            except Exception as e:  # tool failure is fed back so the loop can recover
                observation = {"error": str(e)}
                logger.warning(f"tool {name} failed: {e}")
            session.trace.append({"type": "observation", "tool": name,
                                  "result": _truncate(observation)})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(observation, ensure_ascii=False)[:4000],
            })

    session.trace.append({"type": "final", "thought": "step limit reached"})
    return {"status": "max_steps", "summary": "reached step limit", "trace": session.trace,
            "edits": _collect_edits(session)}


def _collect_edits(session: DocSession) -> list[dict]:
    return [
        {"edit_id": e.edit_id, "instruction": e.instruction, "diff": e.diff,
         "revised_preview": e.revised[:600], "citations": e.citations}
        for e in session.edits.values()
    ]


def _truncate(obj, limit: int = 1500):
    """Cap the trace observation size without risking malformed JSON."""
    s = json.dumps(obj, ensure_ascii=False)
    return obj if len(s) <= limit else {"summary": s[:limit] + "…"}
