"""Build a golden retrieval-eval set from the ingested corpus.

For N randomly sampled documents, take a content-rich chunk and ask
deepseek-chat to write the question a researcher would pose whose answer
lives in that chunk. The source document is then the expected retrieval
target. Auto-generated, meant to be human-reviewed before trusting numbers.

Usage: python -m knowledge_hub.eval.build_golden --n 30 --out knowledge_hub/eval/golden.jsonl
"""
import argparse
import asyncio
import json
import random
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

_PROMPT = """You are helping build a retrieval evaluation set for a corpus of research papers on digital watermarking (screen-shooting / print-camera robustness).

Below is a passage from the paper "{title}".

Passage:
{content}

Write ONE natural research question (in English) that a researcher might ask, whose answer is contained in this passage. The question must be specific enough that this paper is the right one to retrieve, but must NOT mention the paper title or authors directly.

Reply with ONLY the question text."""


async def main(n: int, out: str, seed: int):
    from ..config import KHConfig
    from ..db import get_pool, close_pool
    from openai import AsyncOpenAI

    cfg = KHConfig()
    pool = await get_pool(cfg.database_url)
    docs = await pool.fetch(
        """SELECT d.id, d.title FROM kh_documents d
           WHERE EXISTS (SELECT 1 FROM kh_chunks c WHERE c.doc_id = d.id)""")
    random.seed(seed)
    sample = random.sample(list(docs), min(n, len(docs)))

    client = AsyncOpenAI(api_key=cfg.deepseek_api_key, base_url="https://api.deepseek.com")

    async def gen_one(doc):
        # pick a mid-document chunk (abstract/intro chunks are too easy,
        # reference-list chunks are garbage)
        chunk = await pool.fetchrow(
            """SELECT content FROM kh_chunks WHERE doc_id = $1
               AND length(content) > 400
               ORDER BY abs(chunk_index - 6) LIMIT 1""", doc["id"])
        if chunk is None:
            return None
        resp = await client.chat.completions.create(
            model=cfg.rerank_model,
            messages=[{"role": "user", "content": _PROMPT.format(
                title=doc["title"], content=chunk["content"][:1500])}],
            max_tokens=100, temperature=0.3,
        )
        question = resp.choices[0].message.content.strip().strip('"')
        return {"query": question, "expected_doc_id": doc["id"], "expected_title": doc["title"]}

    results = await asyncio.gather(*[gen_one(d) for d in sample])
    items = [r for r in results if r]
    Path(out).write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n")
    print(f"wrote {len(items)} golden items to {out}")
    await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--out", default="knowledge_hub/eval/golden.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    asyncio.run(main(args.n, args.out, args.seed))
