"""Probe the configured research embedding provider without changing settings.

Run from the repository root with the dora Python. A successful /api/tags or
health response alone does not establish that the embedding model can run.
"""
import asyncio
import json
import math
import time
from dotenv import load_dotenv

from asteria_researcher.config.config import Config
from asteria_researcher.memory.embeddings import Memory


async def check():
    load_dotenv()
    cfg = Config()
    provider = Memory(cfg.embedding_provider, cfg.embedding_model, **cfg.embedding_kwargs).get_embeddings()
    started = time.monotonic()
    dimensions = []
    for count in (1, 16, 1):
        vectors = await asyncio.wait_for(provider.aembed_documents(
            [f"Research evidence health check {i}: source and page provenance." for i in range(count)]), 120)
        if len(vectors) != count or not vectors[0]:
            raise RuntimeError("Embedding vector count/dimension mismatch")
        width = len(vectors[0])
        if any(len(v) != width or not all(math.isfinite(x) for x in v) for v in vectors):
            raise RuntimeError("Malformed embedding vectors")
        dimensions.append(width)
    if len(set(dimensions)) != 1:
        raise RuntimeError("Embedding dimensions changed across requests")
    print(json.dumps({"status": "passed", "provider": cfg.embedding_provider,
                      "model": cfg.embedding_model, "batches": [1, 16, 1],
                      "dimension": dimensions[0], "seconds": round(time.monotonic() - started, 2)}))


if __name__ == "__main__":
    asyncio.run(check())
