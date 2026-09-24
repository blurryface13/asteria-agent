"""Identity binding, actual MCP discovery, and research memory access boundaries."""
import asyncio
import json
import os
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException

from backend.server.research_tools import build_knowledge_search
from backend.runs.routes import validate_request


def test_knowledge_adapter_binds_identity_not_model_arguments(monkeypatch):
    from backend.knowledge import mcp_client
    seen = []
    async def search(owner, ids, query):
        seen.append((owner, ids, query))
        return [{"id": "chunk", "content": "original evidence"}]
    monkeypatch.setattr(mcp_client, "search", search)
    tool = build_knowledge_search("test@example.com", ["lab", "lab", "private"])
    assert asyncio.run(tool("methods"))[0]["id"] == "chunk"
    assert seen == [("test@example.com", ("lab", "private"), "methods")]
    assert build_knowledge_search(None, ["lab"]) is None
    with pytest.raises(ValueError):
        asyncio.run(tool(" "))


def test_server_enforces_selected_libraries(monkeypatch):
    from backend.knowledge import mcp_server
    monkeypatch.setenv("ASTERIA_MCP_USER", "reader@example.com")
    monkeypatch.setenv("ASTERIA_MCP_KNOWLEDGE_IDS", '["private-library"]')
    async def rejected(owner, ids, query, top_k):
        assert owner == "reader@example.com" and ids == ["private-library"]
        raise HTTPException(404, "Library not accessible")
    monkeypatch.setattr(mcp_server, "retrieve", rejected)
    with pytest.raises(HTTPException):
        asyncio.run(mcp_server.search_lab_knowledge("query"))


@pytest.mark.parametrize("fields", [
    {"knowledge_mode": "selected"}, {"knowledge_ids": ["same", "same"]},
    {"knowledge_ids": "lab"}, {"knowledge_mode": "off", "knowledge_ids": ["lab"]},
])
def test_invalid_run_knowledge_scope_rejected(fields):
    with pytest.raises(HTTPException):
        validate_request({"task": "Research", "report_type": "research_report", **fields})


def test_real_stdio_mcp_discovers_only_bound_read_tool():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "backend.knowledge.mcp_server"],
            cwd=Path(__file__).resolve().parents[1],
            env={"PATH": os.environ.get("PATH", ""), "ASTERIA_MCP_USER": "test@example.com",
                 "ASTERIA_MCP_KNOWLEDGE_IDS": '["lab"]'})
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert [t.name for t in tools.tools] == ["search_lab_knowledge"]
            assert set(tools.tools[0].inputSchema["properties"]) == {"query"}
            # Invalid input fails before attempting any database/model call.
            assert (await session.call_tool("search_lab_knowledge", {"query": ""})).isError
    asyncio.run(asyncio.wait_for(run(), 20))
