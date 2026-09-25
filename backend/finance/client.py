"""Fixed local finance MCP server; the model cannot choose executable/host."""
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def search(query: str):
    permitted = {'PATH', 'SYSTEMROOT', 'PYTHONPATH', 'NO_PROXY', 'no_proxy',
                 'HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'}
    env = {k: v for k, v in os.environ.items() if k in permitted}
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'backend.finance.mcp_server'], env=env,
        cwd=Path(__file__).resolve().parents[2])
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        result = await session.call_tool('discover_financial_sources', {'query': query})
        if result.isError:
            raise ValueError('金融资料 MCP 检索失败')
        structured = getattr(result, 'structuredContent', None)
        if isinstance(structured, dict) and isinstance(structured.get('result'), list):
            return structured['result']
        rows = []
        for item in result.content:
            if item.type == 'text':
                value = json.loads(item.text)
                rows.extend(value if isinstance(value, list) else [value])
        return rows
