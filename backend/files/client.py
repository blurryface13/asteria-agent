import json
import os
import sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

TOOLS={'list_workspace_files','read_workspace_file','propose_workspace_change'}

async def call(email,name,arguments):
    if name not in TOOLS: raise ValueError('MCP tool unavailable')
    # Credentials are not forwarded to unrelated models or external MCP servers.
    env={k:v for k,v in os.environ.items() if k in {'PATH','DATABASE_URL','ASTERIA_WORKSPACES_ROOT','PYTHONPATH','SYSTEMROOT'}}
    env['ASTERIA_MCP_USER']=email
    params=StdioServerParameters(command=sys.executable,args=['-m','backend.files.mcp_server'],env=env,cwd=Path(__file__).resolve().parents[2])
    async with stdio_client(params) as (reader,writer),ClientSession(reader,writer) as session:
        await session.initialize()
        result=await session.call_tool(name,arguments)
        if result.isError: raise ValueError('MCP operation rejected; check filename, version and pending quota')
        return [json.loads(c.text) if c.text.startswith(('{','[')) else c.text for c in result.content if c.type=='text']
