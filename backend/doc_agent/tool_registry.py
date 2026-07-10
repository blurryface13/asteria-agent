"""A minimal, explicit tool registry for the document-editing agent.

Unlike the rest of the codebase (which relies on dynamic MCP discovery or
inline hardcoded tool schemas), the doc agent uses a real registry: each tool
declares a name, an LLM-facing JSON schema, and an async handler, registered
via a decorator. The registry then hands the LLM a `tools` array and dispatches
tool calls by name. This is the "tool system" layer the project otherwise lacks.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


ToolHandler = Callable[..., Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema for the arguments
    handler: ToolHandler

    def to_openai_schema(self) -> dict:
        """OpenAI/DeepSeek-compatible function-calling tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict):
        """Decorator: register an async function as a named tool."""
        def _decorator(fn: ToolHandler) -> ToolHandler:
            if name in self._tools:
                raise ValueError(f"tool already registered: {name}")
            if not inspect.iscoroutinefunction(fn):
                raise TypeError(f"tool handler must be async: {name}")
            self._tools[name] = Tool(name=name, description=description,
                                     parameters=parameters, handler=fn)
            return fn
        return _decorator

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict]:
        """The `tools` array passed to the LLM."""
        return [t.to_openai_schema() for t in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict, context: Any = None) -> Any:
        """Execute a tool call. `context` is passed through to handlers that
        declare a `context` kwarg (e.g. the agent's working session)."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        sig = inspect.signature(tool.handler)
        kwargs = dict(arguments)
        if "context" in sig.parameters:
            kwargs["context"] = context
        return await tool.handler(**kwargs)
