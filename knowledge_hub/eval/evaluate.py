"""Retrieval evaluation: doc-level Hit Rate@k and MRR across modes.

A query counts as a hit at k if the expected document appears among the
distinct source documents of the top-k retrieved chunks.

Usage: python -m knowledge_hub.eval.evaluate [--golden knowledge_hub/eval/golden.jsonl]
                                             [--modes dense sparse hybrid hybrid_rerank]
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

K_VALUES = (1, 3, 5, 10)


async def evaluate_mode(searcher, golden: list[dict], mode: str, collection: str | None = None) -> dict:
    hits = {k: 0 for k in K_VALUES}
    mrr_total = 0.0
    latencies = []
    for item in golden:
        t0 = time.perf_counter()
        chunks = await searcher.search(item["query"], top_k=max(K_VALUES), mode=mode,
                                       collection=collection)
        latencies.append(time.perf_counter() - t0)
        # collapse chunk ranking to doc ranking (first appearance)
        doc_ranking: list[str] = []
        for c in chunks:
            if c.doc_id not in doc_ranking:
                doc_ranking.append(c.doc_id)
        expected = item["expected_doc_id"]
        rank = doc_ranking.index(expected) + 1 if expected in doc_ranking else None
        if rank is not None:
            mrr_total += 1.0 / rank
            for k in K_VALUES:
                if rank <= k:
                    hits[k] += 1
    n = len(golden)
    return {
        "mode": mode,
        **{f"hit@{k}": hits[k] / n for k in K_VALUES},
        "mrr@10": mrr_total / n,
        "avg_latency_s": sum(latencies) / n,
    }


async def main(golden_path: str, modes: list[str], collection: str | None = None):
    from ..retrieval.hybrid import HybridSearch
    from ..db import close_pool

    golden = [json.loads(line) for line in Path(golden_path).read_text().splitlines() if line.strip()]
    scope = collection or "FULL CORPUS"
    print(f"golden set: {len(golden)} queries | search scope: {scope}\n")
    searcher = HybridSearch()

    rows = []
    for mode in modes:
        rows.append(await evaluate_mode(searcher, golden, mode, collection))

    header = ["mode"] + [f"hit@{k}" for k in K_VALUES] + ["mrr@10", "avg_latency_s"]
    print(" | ".join(f"{h:>13}" for h in header))
    print("-" * (16 * len(header)))
    for r in rows:
        print(" | ".join(
            f"{r[h]:>13.3f}" if isinstance(r[h], float) else f"{r[h]:>13}" for h in header))
    await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default="knowledge_hub/eval/golden.jsonl")
    parser.add_argument("--modes", nargs="+",
                        default=["dense", "sparse", "hybrid", "hybrid_rerank"])
    parser.add_argument("--collection", default=None,
                        help="restrict search scope; omit for full-corpus (distractor) setting")
    args = parser.parse_args()
    asyncio.run(main(args.golden, args.modes, args.collection))
