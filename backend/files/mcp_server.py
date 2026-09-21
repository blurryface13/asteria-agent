"""stdio MCP tools; identity is set by the authenticated server, never tool args."""
import asyncio
import os
from mcp.server.fastmcp import FastMCP
from backend.files import service

mcp=FastMCP('asteria-private-files')

def identity():
    email=os.environ.get('ASTERIA_MCP_USER')
    if not email: raise RuntimeError('Authenticated owner required')
    return email

@mcp.tool()
async def list_workspace_files()->list:
    return await asyncio.to_thread(service.listing,identity())

@mcp.tool()
async def read_workspace_file(name:str)->dict:
    return await asyncio.to_thread(service.read,identity(),name)

@mcp.tool()
async def propose_workspace_change(name:str,content:str='',operation:str='write',expected_version:str|None=None)->dict:
    """Propose only; a human must approve in the web UI. Read existing files first."""
    return await service.propose(identity(),name,content,operation,expected_version)

if __name__=='__main__':
    mcp.run(transport='stdio')
