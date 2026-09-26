"""Check the packaged API dependencies before starting the local lab."""

from __future__ import annotations

import importlib
import traceback
from pathlib import Path


def main() -> int:
    failed = False
    entrypoint = Path(__file__).with_name("start-research-service.py")
    if entrypoint.stat().st_size == 0:
        print(f"FAIL: empty entrypoint: {entrypoint}")
        failed = True

    checks = {
        "uvicorn runner": lambda: getattr(importlib.import_module("uvicorn"), "run", None)
        or getattr(importlib.import_module("uvicorn.main"), "run"),
        "websockets.Headers": lambda: getattr(
            importlib.import_module("websockets.datastructures"), "Headers"
        ),
        "sniffio.AsyncLibraryNotFoundError": lambda: getattr(
            importlib.import_module("sniffio"), "AsyncLibraryNotFoundError"
        ),
        "typing_extensions.deprecated": lambda: getattr(
            importlib.import_module("typing_extensions"), "deprecated"
        ),
        "typing_extensions.Sentinel": lambda: getattr(
            importlib.import_module("typing_extensions"), "Sentinel"
        ),
        "typing_inspection.Qualifier": lambda: getattr(
            importlib.import_module("typing_inspection.introspection"), "Qualifier"
        ),
        "anyio streams": lambda: getattr(importlib.import_module("anyio.abc"), "ObjectReceiveStream"),
        "fastapi.FastAPI": lambda: getattr(importlib.import_module("fastapi"), "FastAPI"),
        "redis.asyncio.Redis": lambda: getattr(importlib.import_module("redis.asyncio"), "Redis"),
        "requests.Session": lambda: getattr(importlib.import_module("requests"), "Session"),
        "tenacity.retry": lambda: getattr(importlib.import_module("tenacity"), "retry"),
        "tiktoken.get_encoding": lambda: getattr(importlib.import_module("tiktoken"), "get_encoding"),
        "langchain_openai.ChatOpenAI": lambda: getattr(importlib.import_module("langchain_openai"), "ChatOpenAI"),
        "langchain_ollama.OllamaEmbeddings": lambda: getattr(importlib.import_module("langchain_ollama"), "OllamaEmbeddings"),
        "chromadb.Client": lambda: getattr(importlib.import_module("chromadb"), "Client"),
        "asteria app": lambda: getattr(importlib.import_module("main"), "app"),
    }
    for name, check in checks.items():
        try:
            check()
            print(f"OK: {name}")
        except Exception:
            print(f"FAIL: {name}")
            traceback.print_exc()
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
