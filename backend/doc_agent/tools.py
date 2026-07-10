"""Document-editing tools + working session.

Tools registered here form the doc agent's action space. Two safety rules are
baked in structurally, not just by prompt:
  1. read-before-edit: propose_edit only operates on text the agent has read.
  2. propose != apply: the ReAct loop can only *propose* edits (returns a diff);
     writing to disk is a separate, user-confirmed action (apply_edit), and it
     only ever writes a *copy* (<stem>.edited<ext>), never the original.
"""
from __future__ import annotations

import difflib
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .tool_registry import ToolRegistry

registry = ToolRegistry()


@dataclass
class ProposedEdit:
    edit_id: str
    original: str
    revised: str
    diff: str
    citations: list[dict]
    instruction: str


@dataclass
class DocSession:
    session_id: str
    workspace: Path
    file_path: Path | None = None
    file_text: str | None = None
    edits: dict[str, ProposedEdit] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".tex", ".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        from docx import Document as Docx
        doc = Docx(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"unsupported document type: {suffix}")


def _write_copy(path: Path, revised_text: str) -> Path:
    """Write to a sibling copy, never the original."""
    out = path.with_name(f"{path.stem}.edited{path.suffix}")
    if path.suffix.lower() == ".docx":
        from docx import Document as Docx
        doc = Docx()
        for line in revised_text.split("\n"):
            doc.add_paragraph(line)
        doc.save(str(out))
    else:
        out.write_text(revised_text, encoding="utf-8")
    return out


@registry.register(
    name="read_document",
    description="Read the user's document (.tex/.txt/.md/.docx) into the working "
                "session so its text can be revised. Must be called before proposing edits.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the document, relative to the session workspace."}
        },
        "required": ["path"],
    },
)
async def read_document(path: str, context: DocSession) -> dict:
    target = (context.workspace / path).resolve()
    if not str(target).startswith(str(context.workspace.resolve())):
        raise ValueError("path escapes the session workspace")
    if not target.exists():
        raise FileNotFoundError(f"no such file: {path}")
    text = _read_text(target)
    context.file_path = target
    context.file_text = text
    return {
        "path": path,
        "chars": len(text),
        "preview": text[:1500],
    }


@registry.register(
    name="search_knowledge_base",
    description="Search the research-paper knowledge base (336 papers on physical-channel "
                "watermarking) for passages relevant to a claim or topic. Use this to ground "
                "any factual rewrite in real sources before proposing an edit.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look up in the knowledge base."},
            "top_k": {"type": "integer", "description": "How many passages to return (1-8).", "default": 5},
        },
        "required": ["query"],
    },
)
async def search_knowledge_base(query: str, context: DocSession, top_k: int = 5) -> dict:
    from backend.knowledge.modular_rag import get_modular_bridge
    top_k = max(1, min(int(top_k), 8))
    trace = await get_modular_bridge().trace(query=query, top_k=top_k, collection=None)
    chunks = trace.get("stages", {}).get("rerank") or []
    passages = [
        {"title": c.get("title") or "source", "page": c.get("page"), "content": (c.get("content") or "")[:500]}
        for c in chunks
    ]
    return {"query": query, "passages": passages}


@registry.register(
    name="propose_edit",
    description="Propose a factually-grounded rewrite of a span of the document. Returns a "
                "diff and the knowledge-base citations that support the change. This does NOT "
                "write to disk - it only produces a proposal for the user to review.",
    parameters={
        "type": "object",
        "properties": {
            "original_text": {"type": "string", "description": "The exact span from the document to rewrite."},
            "instruction": {"type": "string", "description": "How to rewrite it (e.g. 'correct the claim about moire cause and add a citation')."},
            "citations": {
                "type": "array",
                "description": "Knowledge-base passages that justify the rewrite, from search_knowledge_base results.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "page": {"type": ["integer", "null"]},
                    },
                },
            },
        },
        "required": ["original_text", "instruction"],
    },
)
async def propose_edit(original_text: str, instruction: str, context: DocSession,
                       citations: list[dict] | None = None) -> dict:
    if context.file_text is None:
        raise ValueError("read_document must be called before propose_edit")
    if original_text not in context.file_text:
        # read-before-edit integrity: only rewrite text that actually exists
        raise ValueError("original_text not found verbatim in the document")

    import os as _os
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=_os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    def _fmt_cite(c: dict) -> str:
        page = c.get("page")
        return f"- ({c.get('title')}" + (f", p.{page}" if page not in (None, "") else "") + ")"
    cite_block = "\n".join(_fmt_cite(c) for c in (citations or [])) or "(no citations provided)"
    prompt = (
        "Rewrite the ORIGINAL text per the INSTRUCTION. Preserve the document's format "
        "(if it is LaTeX, keep valid LaTeX; do not add prose outside the span). Only use "
        "facts supported by the CITED passages; do not invent. Return ONLY the rewritten span.\n\n"
        f"INSTRUCTION: {instruction}\n\nCITED passages:\n{cite_block}\n\nORIGINAL:\n{original_text}"
    )
    resp = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200, temperature=0.2,
    )
    revised = (resp.choices[0].message.content or "").strip()

    diff = "".join(difflib.unified_diff(
        original_text.splitlines(keepends=True),
        revised.splitlines(keepends=True),
        fromfile="original", tofile="revised",
    ))
    edit = ProposedEdit(
        edit_id=uuid.uuid4().hex[:12],
        original=original_text, revised=revised, diff=diff,
        citations=citations or [], instruction=instruction,
    )
    context.edits[edit.edit_id] = edit
    return {
        "edit_id": edit.edit_id,
        "diff": diff,
        "revised_preview": revised[:600],
        "citations": edit.citations,
    }


async def apply_edit(session: DocSession, edit_id: str) -> dict:
    """User-confirmed write. NOT a registry tool - never called by the ReAct
    loop. Applies the proposed edit to the in-memory text and writes a COPY."""
    edit = session.edits.get(edit_id)
    if edit is None:
        raise KeyError(f"unknown edit: {edit_id}")
    if session.file_text is None or session.file_path is None:
        raise ValueError("no document loaded")
    if edit.original not in session.file_text:
        raise ValueError("document changed; edit no longer applies")
    session.file_text = session.file_text.replace(edit.original, edit.revised, 1)
    out_path = _write_copy(session.file_path, session.file_text)
    return {"applied": edit_id, "output_path": str(out_path)}
