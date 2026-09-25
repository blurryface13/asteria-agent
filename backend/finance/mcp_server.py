"""Read-only MCP connector for official public financial-source discovery."""
from mcp.server.fastmcp import FastMCP

from backend.server.financial_sources import search_financial_sources

mcp = FastMCP('asteria-public-finance')


@mcp.tool()
async def discover_financial_sources(query: str) -> list[dict]:
    """Find official filing, regulator and issuer URLs. Results are not read evidence."""
    if not 2 <= len(query.strip()) <= 3500:
        raise ValueError('Query must contain 2–3500 characters')
    return await search_financial_sources(query)


if __name__ == '__main__':
    mcp.run(transport='stdio')
