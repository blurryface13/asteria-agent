"""Bind coding tools to server-authenticated identity, not model-supplied identity."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from asteria_researcher.agentic.repository_tools import repository_tools


class ReadFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=180)


class ChangeFile(ReadFile):
    content: str = Field(default="", max_length=262144)
    operation: Literal["write", "delete"] = "write"
    expected_version: str | None = None


class ListFiles(BaseModel):
    model_config = ConfigDict(extra="forbid")


def build_coding_tools(email=None):
    tools = repository_tools()
    if not email:
        return tools
    from backend.files.client import call
    for name, schema in (("list_workspace_files", ListFiles), ("read_workspace_file", ReadFile),
                         ("propose_workspace_change", ChangeFile)):
        async def execute(arguments, name=name, schema=schema):
            validated = schema.model_validate(arguments)
            return await call(email, name, validated.model_dump())
        tools[name] = (schema.model_json_schema(), execute)
    return tools


async def run_workspace_coding(message, history, model, email, progress=None):
    """Same role loop for standalone coding and a research lead's coding child."""
    from asteria_researcher.agentic.autonomous import AutonomousReview
    from asteria_researcher.agentic.collaboration import Assignment
    events = []
    async def emit(kind, payload):
        events.append(payload)
        if progress:
            await progress(payload)
    async def no_approval(_question):
        raise ValueError("文件更改必须通过现有文件提案页面批准")
    runtime = AutonomousReview(model, None, emit, no_approval, online_rag=False,
                               max_actions=30, coding_tools=build_coding_tools(email))
    runtime.query, runtime.plan = message, {}
    runtime.collaboration_context = {"history": history[-8:]}
    task = Assignment(name="代码与实验准备", objective=message, role="coding",
                      focus="按用户授权范围调查并处理代码问题", expected_output="可核查的代码结论或待批准提案；说明未执行项")
    result = (await runtime.dispatch_assignments([task]))[0]
    return result["summary"], {"agent": "workspace_coding", "status": result["status"],
                               "tool_calls": events, "research_requests": result.get("research_requests", []),
                               "sources": result.get("sources", []),
                               "execution_performed": result.get("execution_performed", False),
                               "scratch_change_performed": result.get("scratch_change_performed", False),
                               "generated_artifacts": result.get("generated_artifacts", []),
                               "pending_approval": result.get("pending_approval", False)}
