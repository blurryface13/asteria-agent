"""Lightweight STORM-style outline evaluation on FreshWiki.

Follows the metric STORM's paper uses to evaluate its multi-perspective
pre-writing stage: **heading soft recall** — how well the generated report's
headings semantically cover the reference Wikipedia article's section outline.

soft_recall = (1/|R|) * sum_r max_g cos(E(r), E(g))
  R = reference headings (Wikipedia sections, boilerplate sections excluded)
  G = generated report headings, E = bge-m3 embeddings (local Ollama)

Lightweight setup: N topics sampled from FreshWiki's 100, two variants
(basic single-agent vs multi-agent + perspectives). Not comparable with the
STORM paper's absolute numbers (different backend/task framing) - used for
variant-to-variant comparison on a public dataset.

Usage: python scripts/freshwiki_outline_eval.py --topics 10 --variants basic multi_agent_perspectives
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

HF_TREE = "https://huggingface.co/api/datasets/EchoShao8899/FreshWiki/tree/main/json"
HF_FILE = "https://huggingface.co/datasets/EchoShao8899/FreshWiki/resolve/main/{path}"
CACHE_DIR = PROJECT_ROOT / "outputs" / "freshwiki" / "data"
OUT_DIR = PROJECT_ROOT / "outputs" / "freshwiki"
BOILERPLATE = {"references", "external links", "see also", "notes", "further reading",
               "bibliography", "sources", "footnotes", "gallery"}
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def fetch_topics(n: int, seed: int = 42) -> list[Path]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(HF_TREE, timeout=30) as resp:
        files = [f["path"] for f in json.load(resp) if f["path"].endswith(".json")]
    random.seed(seed)
    picked = random.sample(sorted(files), n)
    paths = []
    for rel in picked:
        dest = CACHE_DIR / Path(rel).name
        if not dest.exists():
            urllib.request.urlretrieve(HF_FILE.format(path=rel), dest)
        paths.append(dest)
    return paths


def reference_headings(doc: dict) -> list[str]:
    heads = []
    for section in doc.get("content", []):
        title = (section.get("section_title") or "").strip()
        if title and title.lower() not in BOILERPLATE:
            heads.append(title)
    return heads


def generated_headings(report: str) -> list[str]:
    return [m.group(1).strip() for m in HEADING_RE.finditer(report) if m.group(1).strip()]


def soft_recall(reference: list[str], generated: list[str], embedder) -> float:
    if not reference or not generated:
        return 0.0
    import numpy as np
    ref_vecs = np.asarray(embedder.embed_documents(reference), dtype=float)
    gen_vecs = np.asarray(embedder.embed_documents(generated), dtype=float)
    ref_vecs /= np.linalg.norm(ref_vecs, axis=1, keepdims=True) + 1e-12
    gen_vecs /= np.linalg.norm(gen_vecs, axis=1, keepdims=True) + 1e-12
    sims = ref_vecs @ gen_vecs.T          # |R| x |G|
    return float(sims.max(axis=1).mean())


async def run_variant(query: str, variant: str) -> str:
    if variant == "basic":
        from scripts.evaluate_agent_workflows import run_basic
        report, _ = await run_basic(query)
        return report
    from scripts.evaluate_agent_workflows import run_multi_agent
    report, _ = await run_multi_agent(
        query, perspectives_enabled=(variant == "multi_agent_perspectives"))
    return report


async def main(n_topics: int, variants: list[str], seed: int) -> None:
    import os
    from langchain_ollama import OllamaEmbeddings

    embedder = OllamaEmbeddings(model="bge-m3",
                                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    topics = fetch_topics(n_topics, seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in topics:
        doc = json.loads(path.read_text(encoding="utf-8"))
        title = doc["title"]
        refs = reference_headings(doc)
        query = f"Write a comprehensive research report about: {title}"
        for variant in variants:
            started = time.perf_counter()
            try:
                report = await run_variant(query, variant)
            except Exception as e:
                print(f"[FAIL] {title} / {variant}: {e}", flush=True)
                rows.append({"topic": title, "variant": variant, "error": str(e)[:300]})
                continue
            recall = soft_recall(refs, generated_headings(report), embedder)
            elapsed = round(time.perf_counter() - started, 1)
            (OUT_DIR / f"{path.stem}_{variant}.md").write_text(report, encoding="utf-8")
            rows.append({"topic": title, "variant": variant, "soft_recall": round(recall, 4),
                         "ref_headings": len(refs), "gen_headings": len(generated_headings(report)),
                         "latency_s": elapsed})
            print(f"[OK] {title} / {variant}: soft_recall={recall:.3f} ({elapsed}s)", flush=True)

    summary = {}
    for variant in variants:
        vals = [r["soft_recall"] for r in rows if r.get("variant") == variant and "soft_recall" in r]
        if vals:
            summary[variant] = {"mean_soft_recall": round(sum(vals) / len(vals), 4), "n": len(vals)}
    report_obj = {"dataset": "FreshWiki (EchoShao8899/FreshWiki)", "topics": n_topics,
                  "seed": seed, "summary": summary, "rows": rows}
    (OUT_DIR / "freshwiki_outline_eval.json").write_text(
        json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topics", type=int, default=10)
    parser.add_argument("--variants", nargs="+",
                        default=["basic", "multi_agent_perspectives"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    asyncio.run(main(args.topics, args.variants, args.seed))
