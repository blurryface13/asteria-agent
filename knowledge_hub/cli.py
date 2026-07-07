"""CLI: python -m knowledge_hub.cli ingest <glob...> [--collection watermark]
       python -m knowledge_hub.cli stats
"""
import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


async def _ingest(args):
    from .config import KHConfig
    from .ingestion.pipeline import ingest_paths
    from .db import close_pool

    cfg = KHConfig()
    paths: list[Path] = []
    if args.from_file:
        paths.extend(Path(line.strip()) for line in Path(args.from_file).read_text().splitlines() if line.strip())
    for pattern in args.paths:
        p = Path(pattern).expanduser()
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.pdf")))
        elif p.is_file():
            paths.append(p)
    print(f"{len(paths)} pdf files to process")
    stats = await ingest_paths(paths, args.collection, cfg)
    print(stats)
    await close_pool()


async def _stats(args):
    from .config import KHConfig
    from .db import get_pool, close_pool

    cfg = KHConfig()
    pool = await get_pool(cfg.database_url)
    docs = await pool.fetchval("SELECT count(*) FROM kh_documents")
    chunks = await pool.fetchval("SELECT count(*) FROM kh_chunks")
    by_col = await pool.fetch(
        "SELECT collection, count(*) AS docs FROM kh_documents GROUP BY collection")
    print(f"documents: {docs}, chunks: {chunks}")
    for row in by_col:
        print(f"  {row['collection']}: {row['docs']} docs")
    await close_pool()


async def _query(args):
    from .retrieval.hybrid import HybridSearch
    from .db import close_pool

    searcher = HybridSearch()
    results = await searcher.search(args.text, top_k=args.top_k,
                                    collection=args.collection, mode=args.mode)
    for i, c in enumerate(results, 1):
        prov = ", ".join(f"{k}={v:.4f}" for k, v in c.provenance.items())
        print(f"{i}. [{c.title[:70]}] p{c.page_start} ({prov})")
        print(f"   {c.content[:180].replace(chr(10), ' ')}...")
    await close_pool()


def main():
    parser = argparse.ArgumentParser(prog="knowledge_hub")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("paths", nargs="*")
    p_ingest.add_argument("--from-file", help="text file with one pdf path per line")
    p_ingest.add_argument("--collection", default="watermark")
    p_ingest.set_defaults(func=_ingest)

    p_stats = sub.add_parser("stats")
    p_stats.set_defaults(func=_stats)

    p_query = sub.add_parser("query")
    p_query.add_argument("text")
    p_query.add_argument("--mode", default="hybrid",
                         choices=["dense", "sparse", "hybrid", "hybrid_rerank"])
    p_query.add_argument("--top-k", type=int, default=5)
    p_query.add_argument("--collection", default=None)
    p_query.set_defaults(func=_query)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
