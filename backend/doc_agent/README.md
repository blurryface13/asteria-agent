# Document-Editing Agent (ReAct + ToolRegistry)

A knowledge-grounded document-revision agent: upload a paper (`.tex/.md/.txt/.docx`),
give a revision instruction, and the agent revises it so its claims are accurate and
cited against the research-paper knowledge base (the Modular RAG corpus, 336 papers).

This module exists to introduce standard agent concepts the rest of the project
lacked — a real **tool registry** and a real **ReAct loop** — so the system is
demonstrably more than a fixed LLM workflow.

## What makes it "agentic" (not a fixed workflow)

`react_agent.py` runs a genuine tool-calling loop: the LLM is handed the registry's
tool schemas and *decides each turn* which tool to call (Thought → Action →
Observation), recovering from tool errors on its own. In testing the agent:
`read_document → search_knowledge_base ×3 (refining its own queries) → propose_edit
(failed twice: text not verbatim) → re-read the document → propose_edit (succeeded)`.
That self-recovery is the loop adapting control flow at runtime — not a hardcoded
pipeline.

## The pieces

| File | Role |
|---|---|
| `tool_registry.py` | `ToolRegistry`: decorator-based registration of (name, JSON schema, async handler); emits the LLM `tools` array and dispatches calls by name. |
| `tools.py` | The action space: `read_document`, `search_knowledge_base` (reuses the Modular RAG bridge), `propose_edit` (grounded rewrite → diff + citations, **no disk write**). Plus `apply_edit` (not a registry tool). |
| `react_agent.py` | The ReAct loop over the registry, with a step cap and full trace capture. |
| `routes.py` | `/api/doc-agent/upload · /revise · /apply`, JWT-guarded. |

## Safety model (borrowed from coding agents, enforced structurally)

- **read-before-edit**: `propose_edit` rejects any `original_text` not present verbatim
  in the loaded document.
- **propose ≠ apply**: the ReAct loop can only *propose* (returns a diff). Writing is a
  separate, user-confirmed action (`/apply`).
- **never touch the original**: `apply_edit` writes a sibling copy `<stem>.edited<ext>`.

## Reuse (no reinvention)

Retrieval is `backend.knowledge.modular_rag.get_modular_bridge().trace()`; auth is the
project-wide `Depends(get_current_user_email)`; generation uses the existing
OpenAI-compatible LLM config.
