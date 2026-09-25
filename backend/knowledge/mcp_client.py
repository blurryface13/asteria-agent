"""Local stdio transport; no arbitrary executable or model-selected credentials."""
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def search(owner: str, knowledge_ids: tuple[str, ...], query: str):
    # This trusted local server needs DB/embedding configuration, not login JWTs
    # or unrelated provider secrets. Never expose these values in tool results.
    permitted = {
        "PATH", "SYSTEMROOT", "HOME", "DATABASE_URL", "ASTERIA_ADMIN_EMAILS",
        "ASTERIA_PUBLISH_PAPER_CORPUS", "MODULAR_RAG_MCP_ROOT", "MODULAR_RAG_MCP_CONFIG",
        "MODULAR_RAG_COLLECTION", "OLLAMA_BASE_URL", "DASHSCOPE_API_KEY",
        "NO_PROXY", "no_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
    }
    env = {key: value for key, value in os.environ.items() if key in permitted}
    env.update(ASTERIA_MCP_USER=owner, ASTERIA_MCP_KNOWLEDGE_IDS=json.dumps(knowledge_ids))
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "backend.knowledge.mcp_server"], env=env,
        cwd=Path(__file__).resolve().parents[2])
    async with stdio_client(parameters) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        result = await session.call_tool("search_lab_knowledge", {"query": query})
        if result.isError:
            raise ValueError("知识库 MCP 检索失败；请检查库权限、索引及服务端日志")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict) and isinstance(structured.get("result"), list):
            return structured["result"]
        rows = []
        for item in result.content:
            if item.type == "text":
                value = json.loads(item.text)
                rows.extend(value if isinstance(value, list) else [value])
        return rows
