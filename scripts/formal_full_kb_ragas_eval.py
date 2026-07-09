"""Formal full-knowledge-base RAG evaluation.

This evaluation combines:
- the existing Knowledge Hub PostgreSQL corpus: 321 papers / 23k chunks
- the curated Modular RAG CS paper corpus from formal_modular_rag_eval.py

It reports only the two metrics currently used for the resume claim:
- Hit Rate@10 over a Golden Test Set
- Ragas Faithfulness over a stratified subset of the same retrieval task
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULAR_ROOT = Path(
    "/Users/dora/Documents/Codex/2026-07-07/wome/work/MODULAR-RAG-MCP-SERVER"
)
OUT_DIR = PROJECT_ROOT / "outputs" / "full_kb_rag_eval"
REPORT_JSON = OUT_DIR / "full_kb_ragas_eval_report.json"
REPORT_MD = OUT_DIR / "full_kb_ragas_eval_report.md"
COMBINED_COLLECTION = "full_kb_rag_eval_20260709"
FORMAL_COLLECTION = "cs_research_eval_20260709"


def ensure_paths() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    os.environ["MODULAR_RAG_MCP_CONFIG"] = str(
        PROJECT_ROOT / "outputs" / "formal_rag_eval" / "modular_rag_eval_settings.yaml"
    )
    for path in [str(PROJECT_ROOT), str(MODULAR_ROOT)]:
        if path not in sys.path:
            sys.path.insert(0, path)


def parse_vector(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(x) for x in value]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [float(part) for part in text.split(",") if part.strip()]


def batch(items: list[Any], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


async def load_knowledge_hub_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch(
        """
        SELECT
            c.id AS chunk_id,
            c.doc_id,
            c.chunk_index,
            c.content,
            c.page_start,
            c.embedding,
            d.title,
            d.source_path,
            d.collection
        FROM kh_chunks c
        JOIN kh_documents d ON d.id = c.doc_id
        ORDER BY d.collection, d.id, c.chunk_index
        """
    )
    docs = await conn.fetch(
        """
        SELECT collection, count(*) AS docs
        FROM kh_documents
        GROUP BY collection
        ORDER BY collection
        """
    )
    await conn.close()

    records: list[dict[str, Any]] = []
    for row in rows:
        metadata = {
            "text": row["content"],
            "origin": "knowledge_hub",
            "doc_id": row["doc_id"],
            "source_ref": row["doc_id"],
            "title": row["title"] or "",
            "source_path": row["source_path"] or "",
            "collection": row["collection"] or "",
            "page_start": int(row["page_start"] or 0),
            "chunk_index": int(row["chunk_index"] or 0),
        }
        records.append(
            {
                "id": f"kh::{row['chunk_id']}",
                "vector": parse_vector(row["embedding"]),
                "metadata": metadata,
            }
        )
    return records, [dict(row) for row in docs]


def load_formal_records() -> list[dict[str, Any]]:
    from backend.knowledge.modular_rag import get_modular_bridge
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory

    bridge = get_modular_bridge()
    store = VectorStoreFactory.create(bridge.settings, collection_name=FORMAL_COLLECTION)
    raw = store.collection.get(include=["embeddings", "documents", "metadatas"])
    ids = raw.get("ids") or []
    embeddings = raw.get("embeddings")
    if embeddings is None:
        embeddings = []
    docs = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []

    records: list[dict[str, Any]] = []
    for chunk_id, vector, text, metadata in zip(ids, embeddings, docs, metadatas):
        meta = dict(metadata or {})
        meta["text"] = text or meta.get("text", "")
        meta["origin"] = "formal_cs_papers"
        meta["source_ref"] = meta.get("source_ref") or meta.get("doc_hash") or str(chunk_id)
        records.append(
            {
                "id": f"formal::{chunk_id}",
                "vector": [float(x) for x in vector],
                "metadata": meta,
            }
        )
    return records


def reset_collection(collection: str) -> None:
    from backend.knowledge.modular_rag import get_modular_bridge
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory

    bridge = get_modular_bridge()
    store = VectorStoreFactory.create(bridge.settings, collection_name=collection)
    try:
        store.client.delete_collection(collection)
    except Exception:
        pass
    VectorStoreFactory.create(bridge.settings, collection_name=collection)


def upsert_records(collection: str, records: list[dict[str, Any]]) -> None:
    from backend.knowledge.modular_rag import get_modular_bridge
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory

    bridge = get_modular_bridge()
    store = VectorStoreFactory.create(bridge.settings, collection_name=collection)
    for chunk in batch(records, 500):
        store.upsert(chunk)


def load_bm25_metadata(collection: str) -> dict[str, Any]:
    from src.core.settings import resolve_path
    from src.ingestion.storage.bm25_indexer import BM25Indexer

    index_dir = resolve_path(f"data/db/bm25/{collection}")
    indexer = BM25Indexer(index_dir=str(index_dir))
    loaded = indexer.load(collection)
    if not loaded:
        raise RuntimeError(f"BM25 index not found for collection: {collection}")
    return {
        "chunk_count": indexer._metadata.get("num_docs"),
        "index_dir": str(index_dir),
        "loaded_existing": True,
    }


def rebuild_full_bm25(collection: str) -> dict[str, Any]:
    from src.core.settings import resolve_path
    from src.ingestion.embedding.sparse_encoder import SparseEncoder
    from src.ingestion.storage.bm25_indexer import BM25Indexer
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory

    from backend.knowledge.modular_rag import get_modular_bridge

    bridge = get_modular_bridge()
    vector_store = VectorStoreFactory.create(bridge.settings, collection_name=collection)
    raw = vector_store.collection.get(include=["documents"])
    ids = raw.get("ids") or []
    docs = raw.get("documents") or []
    encoder = SparseEncoder()

    term_stats: list[dict[str, Any]] = []
    for chunk_id, text in zip(ids, docs):
        if not text or not str(text).strip():
            continue
        terms = encoder._tokenize(str(text))
        freqs: dict[str, int] = {}
        for term in terms:
            freqs[term] = freqs.get(term, 0) + 1
        term_stats.append(
            {
                "chunk_id": str(chunk_id),
                "term_frequencies": freqs,
                "doc_length": len(terms),
                "unique_terms": len(freqs),
            }
        )

    indexer = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
    indexer.rebuild(term_stats, collection=collection)
    return {
        "chunk_count": len(term_stats),
        "index_dir": str(resolve_path(f"data/db/bm25/{collection}")),
        "loaded_existing": False,
    }


def build_golden_set() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location(
        "formal_modular_rag_eval",
        PROJECT_ROOT / "scripts" / "formal_modular_rag_eval.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load formal_modular_rag_eval.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    papers = module.PAPERS

    golden: list[dict[str, Any]] = []
    kh_path = PROJECT_ROOT / "knowledge_hub" / "eval" / "golden.jsonl"
    for line in kh_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        golden.append(
            {
                "query": item["query"],
                "expected_doc_id": item["expected_doc_id"],
                "expected_title": item.get("expected_title", ""),
                "expected_filename": "",
                "origin": "knowledge_hub",
                "field": "watermark",
            }
        )

    for paper in papers:
        filename = paper.filename
        for query in paper.queries:
            golden.append(
                {
                    "query": query,
                    "expected_doc_id": "",
                    "expected_title": paper.title,
                    "expected_filename": filename,
                    "origin": "formal_cs_papers",
                    "field": paper.field,
                }
            )
    return golden


def result_matches(item: dict[str, Any], case: dict[str, Any]) -> bool:
    metadata = item.get("metadata") or {}
    haystack = " ".join(
        str(value)
        for value in [
            item.get("chunk_id"),
            item.get("doc_id"),
            item.get("title"),
            metadata.get("doc_id"),
            metadata.get("source_ref"),
            metadata.get("source_path"),
            metadata.get("source"),
            metadata.get("title"),
        ]
        if value
    ).lower()
    expected_doc_id = str(case.get("expected_doc_id") or "").lower()
    expected_filename = str(case.get("expected_filename") or "").lower()
    if expected_doc_id and expected_doc_id in haystack:
        return True
    return bool(expected_filename and expected_filename in haystack)


def hit_rate_at_10(results: list[dict[str, Any]], case: dict[str, Any]) -> float:
    return 1.0 if any(result_matches(item, case) for item in results[:10]) else 0.0


async def qwen_answer(query: str, contexts: list[str]) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    prompt = (
        "Answer the question using only the retrieved paper contexts. "
        "Keep the answer factual and concise.\n\n"
        f"Question: {query}\n\n"
        "Contexts:\n"
        + "\n\n".join(f"[{i + 1}] {text[:1200]}" for i, text in enumerate(contexts[:5]))
    )
    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=450,
    )
    return response.choices[0].message.content or ""


def choose_faithfulness_cases(golden: list[dict[str, Any]], sample_count: int | None) -> list[dict[str, Any]]:
    if sample_count is None or sample_count >= len(golden):
        return golden
    buckets: dict[str, list[dict[str, Any]]] = {}
    for case in golden:
        buckets.setdefault(case["field"], []).append(case)

    selected: list[dict[str, Any]] = []
    fields = list(buckets)
    index = 0
    while len(selected) < sample_count and any(index < len(buckets[field]) for field in fields):
        for field in fields:
            if index < len(buckets[field]) and len(selected) < sample_count:
                selected.append(buckets[field][index])
        index += 1
    return selected


async def run(faithfulness_samples: int | None, rebuild: bool, skip_bm25_rebuild: bool) -> dict[str, Any]:
    ensure_paths()
    if "DASHSCOPE_API_KEY" not in os.environ:
        raise RuntimeError("DASHSCOPE_API_KEY is required for qwen3-rerank and Ragas faithfulness")

    from backend.knowledge.modular_rag import get_modular_bridge

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    if rebuild:
        reset_collection(COMBINED_COLLECTION)
        kh_records, kh_collection_summary = await load_knowledge_hub_records()
        formal_records = load_formal_records()
        upsert_records(COMBINED_COLLECTION, kh_records + formal_records)
    else:
        kh_records, kh_collection_summary = await load_knowledge_hub_records()
        formal_records = load_formal_records()

    bm25_rebuild = (
        load_bm25_metadata(COMBINED_COLLECTION)
        if skip_bm25_rebuild
        else rebuild_full_bm25(COMBINED_COLLECTION)
    )
    golden = build_golden_set()
    bridge = get_modular_bridge()

    rows: list[dict[str, Any]] = []
    stage_hits = {"dense": 0.0, "sparse": 0.0, "rrf": 0.0, "rerank": 0.0}
    latencies: list[float] = []
    for case in golden:
        trace = await bridge.trace(case["query"], top_k=10, collection=COMBINED_COLLECTION)
        latencies.append(float(trace["latency_s"]))
        stage_result: dict[str, float] = {}
        for stage in ["dense", "sparse", "rrf", "rerank"]:
            value = hit_rate_at_10(trace["stages"].get(stage, []), case)
            stage_hits[stage] += value
            stage_result[f"{stage}_hit@10"] = value
        rows.append({**case, **stage_result, "latency_s": trace["latency_s"]})

    n = len(golden) or 1
    hit_summary = {
        stage: {
            "hit_rate@10": stage_hits[stage] / n,
        }
        for stage in stage_hits
    }

    faithfulness_rows: list[dict[str, Any]] = []
    faithfulness_errors: list[dict[str, Any]] = []
    for case in choose_faithfulness_cases(golden, faithfulness_samples):
        trace = await bridge.trace(case["query"], top_k=5, collection=COMBINED_COLLECTION)
        contexts = [item["content"] for item in trace["stages"].get("rerank", [])[:5] if item.get("content")]
        if not contexts:
            continue
        try:
            answer = await qwen_answer(case["query"], contexts)
            ragas = await bridge.ragas_score(
                query=case["query"],
                answer=answer,
                contexts=contexts,
                metrics=["faithfulness"],
            )
            faithfulness_rows.append(
                {
                    **case,
                    "answer": answer,
                    "faithfulness": ragas["metrics"].get("faithfulness"),
                    "latency_s": ragas["latency_s"],
                }
            )
        except Exception as exc:
            faithfulness_errors.append({**case, "error": str(exc)[:1000]})

    faithfulness_values = [
        float(row["faithfulness"])
        for row in faithfulness_rows
        if row.get("faithfulness") is not None
    ]
    faithfulness_summary = {
        "sample_count": len(faithfulness_rows),
        "average": sum(faithfulness_values) / len(faithfulness_values) if faithfulness_values else None,
        "min": min(faithfulness_values) if faithfulness_values else None,
        "max": max(faithfulness_values) if faithfulness_values else None,
        "errors": len(faithfulness_errors),
    }

    report = {
        "collection": COMBINED_COLLECTION,
        "corpus": {
            "knowledge_hub_docs": sum(int(item["docs"]) for item in kh_collection_summary),
            "knowledge_hub_chunks": len(kh_records),
            "formal_docs": 15,
            "formal_chunks": len(formal_records),
            "total_docs": sum(int(item["docs"]) for item in kh_collection_summary) + 15,
            "total_chunks": len(kh_records) + len(formal_records),
            "knowledge_hub_collections": kh_collection_summary,
            "bm25_rebuild": bm25_rebuild,
        },
        "chunking": {
            "knowledge_hub": {"chunk_size": 1000, "chunk_overlap": 150, "splitter": "RecursiveCharacterTextSplitter"},
            "modular_rag": {"chunk_size": 1000, "chunk_overlap": 200, "splitter": "recursive"},
        },
        "retrieval_config": {
            "dense_top_k": 20,
            "sparse_top_k": 20,
            "fusion_top_k": 10,
            "rrf_k": 60,
            "final_top_k_for_hit_rate": 10,
            "faithfulness_context_top_k": 5,
        },
        "golden_query_count": len(golden),
        "hit_rate": {
            "summary": hit_summary,
            "rows": rows,
            "avg_trace_latency_s": sum(latencies) / len(latencies) if latencies else None,
        },
        "faithfulness": {
            "summary": faithfulness_summary,
            "rows": faithfulness_rows,
            "errors": faithfulness_errors,
        },
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    corpus = report["corpus"]
    faithfulness = report["faithfulness"]["summary"]
    lines = [
        "# Full Knowledge Base RAG Evaluation",
        "",
        f"- Collection: `{report['collection']}`",
        f"- Documents: {corpus['total_docs']} ({corpus['knowledge_hub_docs']} Knowledge Hub + {corpus['formal_docs']} formal CS papers)",
        f"- Chunks: {corpus['total_chunks']}",
        f"- Golden queries: {report['golden_query_count']}",
        f"- Faithfulness samples: {faithfulness['sample_count']}",
        "",
        "## Chunking / Retrieval",
        "",
        "- Knowledge Hub chunks: size 1000, overlap 150, RecursiveCharacterTextSplitter",
        "- Modular RAG chunks: size 1000, overlap 200, recursive splitter",
        "- Retrieval: dense top20 + sparse top20 -> RRF k=60/top10 -> qwen3-rerank",
        "- Hit Rate uses final top10; Faithfulness uses top5 reranked contexts",
        "",
        "## Hit Rate@10",
        "",
        "| Stage | Hit Rate@10 |",
        "|---|---:|",
    ]
    for stage, metrics in report["hit_rate"]["summary"].items():
        lines.append(f"| {stage} | {metrics['hit_rate@10']:.3f} |")
    lines.extend(["", "## Ragas Faithfulness", ""])
    avg = faithfulness.get("average")
    if avg is None:
        lines.append("- Faithfulness: no score computed")
    else:
        lines.append(f"- Average faithfulness: {avg:.3f}")
        lines.append(f"- Min / Max: {faithfulness['min']:.3f} / {faithfulness['max']:.3f}")
    if faithfulness.get("errors"):
        lines.append(f"- Errors: {faithfulness['errors']}")
    lines.extend(["", f"Elapsed: {report['elapsed_s']:.1f}s", ""])
    return "\n".join(lines)


def parse_sample_count(value: str) -> int | None:
    if value.lower() == "all":
        return None
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("--faithfulness-samples must be positive or 'all'")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faithfulness-samples", type=parse_sample_count, default=18)
    parser.add_argument("--no-rebuild", action="store_true")
    parser.add_argument("--skip-bm25-rebuild", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(
        run(
            args.faithfulness_samples,
            rebuild=not args.no_rebuild,
            skip_bm25_rebuild=args.skip_bm25_rebuild,
        )
    )
    print(
        json.dumps(
            {
                "collection": report["collection"],
                "corpus": report["corpus"],
                "golden_query_count": report["golden_query_count"],
                "hit_rate": report["hit_rate"]["summary"],
                "faithfulness": report["faithfulness"]["summary"],
                "report_json": str(REPORT_JSON),
                "report_md": str(REPORT_MD),
                "elapsed_s": report["elapsed_s"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
