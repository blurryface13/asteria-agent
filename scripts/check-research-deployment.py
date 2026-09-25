"""Readiness checks for the Research Lead deployment; no paid model calls."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.lab", override=True)
    os.environ["PATH"] += os.pathsep + "/Library/TeX/texbin"
    results = []
    async def check(name, call):
        try:
            detail = await asyncio.wait_for(call(), 30)
            results.append({"check": name, "status": "ready", "detail": detail})
        except Exception as error:
            results.append({"check": name, "status": "failed", "error_type": type(error).__name__})
    async def database():
        from backend.auth.db import get_pool, close_pool
        try:
            return "PostgreSQL responds" if await (await get_pool()).fetchval("SELECT 1") == 1 else None
        finally:
            await close_pool()
    async def redis():
        from backend.auth.lab import redis_connection
        async with redis_connection() as client:
            await client.ping()
        return "Redis responds"
    async def api():
        import httpx
        async with httpx.AsyncClient(trust_env=False, timeout=8) as client:
            response = await client.get("http://127.0.0.1:" + os.getenv("ASTERIA_API_PORT", "8018") + "/api/auth/config")
            response.raise_for_status()
            return response.json()
    async def embedding():
        from asteria_researcher.config.config import Config
        from asteria_researcher.memory.embeddings import Memory
        cfg = Config(os.getenv("CONFIG_PATH") or None)
        vectors = await Memory(cfg.embedding_provider, cfg.embedding_model, **cfg.embedding_kwargs).get_embeddings().aembed_documents(["research readiness"])
        return {"provider": cfg.embedding_provider, "model": cfg.embedding_model, "dimensions": len(vectors[0])}
    async def tex():
        if not shutil.which("xelatex"):
            raise FileNotFoundError("XeLaTeX required")
        process = await asyncio.create_subprocess_exec(
            "kpsewhich", "--format=cmap", "Adobe-GB1-UCS2",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await process.communicate()
        if process.returncode or not Path(out.decode().strip()).is_file():
            raise FileNotFoundError("TeX Adobe-GB1 Unicode mapping required for portable Chinese PDF")
        return "XeLaTeX and embeddable Chinese Unicode mapping available"
    async def mcp(module, env):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(command=sys.executable, args=["-m", module],
            cwd=ROOT, env={"PATH": os.environ["PATH"], **env})
        async with stdio_client(parameters) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            return [tool.name for tool in (await session.list_tools()).tools]
    await asyncio.gather(
        check("database", database), check("redis", redis), check("api", api),
        check("embedding", embedding), check("pdf_compiler", tex),
        check("knowledge_mcp", lambda: mcp("backend.knowledge.mcp_server", {
            "ASTERIA_MCP_USER": "readiness@example.com", "ASTERIA_MCP_KNOWLEDGE_IDS": '["lab-research-papers"]'})),
        check("files_mcp", lambda: mcp("backend.files.mcp_server", {"ASTERIA_MCP_USER": "readiness@example.com"})),
    )
    print(json.dumps({"ready": all(r["status"] == "ready" for r in results), "checks": results}, ensure_ascii=False, indent=2))
    return all(r["status"] == "ready" for r in results)


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
