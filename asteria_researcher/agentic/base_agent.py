"""Shared, provider-neutral role loop, following EchoMind's BaseAgent boundary.

Domain adapters retain their tool schemas and observations; they do not own a
second decision loop. Model/provider errors propagate, invalid decisions become
observations, and cancellation is never converted into an ordinary tool error.
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentProfile:
    role: str
    mission: str
    input_contract: str
    output_contract: str
    tool_scope: tuple[str, ...]
    max_turns: int = 8


@dataclass(frozen=True)
class AgentFinish:
    value: Any


class AgentStop(Exception):
    """Shared runtime budget exhausted before starting another side effect."""


class BaseAgent:
    def __init__(self, profile, *, max_turns=None, terminal_tools=("finish",)):
        self.profile = profile
        self.max_turns = profile.max_turns if max_turns is None else max_turns
        if self.max_turns < 1:
            raise ValueError("Agent requires at least one decision turn")
        self.terminal_tools = frozenset(terminal_tools)

    async def run(self, *, decide, parse, execute, observe_error,
                  tool_name=lambda action: action.tool, available=None):
        """Run one isolated invocation; callbacks close over its own observations.

        decide receives the effective allowlist so advertised tools and executable
        tools agree. It may return None to stop when a shared budget is exhausted.
        execute returns AgentFinish only for a validated final result.
        """
        for turn in range(self.max_turns):
            allowed = set(self.profile.tool_scope)
            if available is not None:
                allowed.intersection_update(available(turn))
            if turn == self.max_turns - 1:
                allowed.intersection_update(self.terminal_tools)
            raw = await decide(turn, allowed)
            if raw is None:
                break
            try:
                action = parse(raw)
            except (ValueError, TypeError) as error:
                await observe_error("Invalid action JSON/schema; repair the structure, do not execute tools.", error)
                continue
            if tool_name(action) not in allowed:
                await observe_error("Tool unavailable or outside role permissions / remaining budget", None)
                continue
            try:
                result = await execute(action, turn)
            except AgentStop:
                break
            if isinstance(result, AgentFinish):
                return result.value
        return None
