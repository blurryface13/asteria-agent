"""Evaluate the query-understanding layer under realistic (colloquial) queries.

The 90-query golden set is clean English generated from corpus chunks - it
overstates lexical overlap and understates what real users type. To measure
the understanding layer where it matters, we derive a *colloquial variant*
of each golden query (casual Chinese researcher phrasing, LLM-generated,
cached), then compare document-level Hit@10 on the hybrid retriever:

  A) colloquial query, no understanding layer
  B) colloquial query -> rewrite_query() -> retrieval
  (reference line: original clean golden query)

Usage: python scripts/query_understanding_eval.py [--limit 90] [--mode hybrid]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

GOLDEN_PATH = PROJECT_ROOT / "eval" / "golden.jsonl"
COLLOQUIAL_PATH = PROJECT_ROOT / "eval" / "golden_colloquial.jsonl"
OUT_PATH = PROJECT_ROOT / "outputs" / "query_understanding_eval.json"

_DERIVE_PROMPT = """把下面这个书面化的英文研究问题,改写成一位中国研究生在知识库搜索框里会随手输入的**口语化中文查询**。
要求:保留问题的核心意图;可以使用领域缩写(如 PSNR、BER);不要完整句子腔,像真实搜索输入;只输出改写后的查询本身。

英文问题: {query}"""


async def derive_colloquial(golden: list[dict]) -> list[dict]:
    """LLM-derive (and cache) colloquial Chinese variants of the golden queries."""
    if COLLOQUIAL_PATH.exists():
        cached = [json.loads(l) for l in COLLOQUIAL_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(cached) >= len(golden):
            return cached[: len(golden)]

    import os
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

    async def one(item: dict) -> dict:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": _DERIVE_PROMPT.format(query=item["query"])}],
            max_tokens=80, temperature=0.4,
        )
        return {**item, "colloquial": (resp.choices[0].message.content or "").strip()}

    sem = asyncio.Semaphore(8)
    async def guarded(item):
        async with sem:
            return await one(item)
    rows = await asyncio.gather(*[guarded(item) for item in golden])
    COLLOQUIAL_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return list(rows)


def hit_at_10(trace: dict, expected_doc_id: str, expected_title: str) -> float:
    """Document-level hit: expected paper among top-10 chunks' source docs."""
    stage = trace.get("stages", {})
    items = stage.get("rerank") or stage.get("rrf") or []
    needle_id = (expected_doc_id or "").lower()
    needle_title = (expected_title or "").lower()
    seen_docs = []
    for item in items[:10]:
        meta = item.get("metadata") or {}
        hay = " ".join(str(x) for x in [item.get("doc_id"), item.get("title"),
                                        meta.get("source_ref"), meta.get("source_path")] if x).lower()
        seen_docs.append(hay)
    for hay in seen_docs:
        if (needle_id and needle_id in hay) or (needle_title and needle_title in hay):
            return 1.0
    return 0.0


async def evaluate(rows: list[dict], mode: str) -> dict:
    from backend.knowledge.modular_rag import get_modular_bridge
    from backend.knowledge.query_understanding import rewrite_query

    bridge = get_modular_bridge()
    scores = {"colloquial_raw": [], "colloquial_rewritten": [], "original": []}
    examples = []
    for i, row in enumerate(rows):
        colloquial = row["colloquial"]
        rewritten = await rewrite_query(colloquial)
        for label, q in (("colloquial_raw", colloquial),
                         ("colloquial_rewritten", rewritten),
                         ("original", row["query"])):
            trace = await bridge.trace(query=q, top_k=10, collection=None, mode=mode)
            scores[label].append(hit_at_10(trace, row.get("expected_doc_id", ""),
                                           row.get("expected_title", "")))
        if i < 5:
            examples.append({"original": row["query"], "colloquial": colloquial, "rewritten": rewritten})
        if (i + 1) % 10 == 0:
            print(f"{i + 1}/{len(rows)} done", flush=True)
    return {
        "mode": mode,
        "n": len(rows),
        "hit@10": {k: round(sum(v) / len(v), 4) for k, v in scores.items() if v},
        "examples": examples,
    }


async def main(limit: int, mode: str) -> None:
    golden = [json.loads(l) for l in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if l.strip()][:limit]
    rows = await derive_colloquial(golden)
    started = time.perf_counter()
    report = await evaluate(rows, mode)
    report["elapsed_s"] = round(time.perf_counter() - started, 1)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["hit@10"], indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=90)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "hybrid_rerank"])
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.mode))
