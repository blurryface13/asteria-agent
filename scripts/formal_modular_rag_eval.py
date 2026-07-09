"""Formal Modular RAG evaluation for the resume-backed RAG claims.

This script builds a curated CS research-paper collection, runs document-level
golden-query retrieval evaluation across dense/sparse/RRF/rerank stages, and
runs a smaller Ragas answer-quality evaluation sample.

It intentionally disables large-batch Vision LLM captioning for ingestion; the
formal run targets retrieval quality. Qwen-VL multimodal behavior is tested
separately and recorded in memory.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULAR_ROOT = Path(
    "/Users/dora/Documents/Codex/2026-07-07/wome/work/MODULAR-RAG-MCP-SERVER"
)
OUT_DIR = PROJECT_ROOT / "outputs" / "formal_rag_eval"
PAPERS_DIR = OUT_DIR / "papers"
REPORT_JSON = OUT_DIR / "formal_rag_eval_report.json"
REPORT_MD = OUT_DIR / "formal_rag_eval_report.md"
EVAL_CONFIG = OUT_DIR / "modular_rag_eval_settings.yaml"
COLLECTION = "cs_research_eval_20260709"


@dataclass(frozen=True)
class Paper:
    slug: str
    title: str
    field: str
    arxiv_id: str
    queries: tuple[str, str]

    @property
    def url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"

    @property
    def filename(self) -> str:
        return f"{self.field}_{self.slug}_{self.arxiv_id.replace('/', '_')}.pdf"


PAPERS: tuple[Paper, ...] = (
    Paper(
        "rag_original",
        "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "rag",
        "2005.11401",
        (
            "Which paper introduced retrieval-augmented generation for knowledge-intensive NLP tasks?",
            "What method combines a parametric seq2seq model with non-parametric memory retrieved from Wikipedia?",
        ),
    ),
    Paper(
        "self_rag",
        "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
        "rag",
        "2310.11511",
        (
            "Which paper proposes reflection tokens for adaptive retrieval and critique in RAG?",
            "What work trains a language model to decide when to retrieve and critique its own generations?",
        ),
    ),
    Paper(
        "corrective_rag",
        "Corrective Retrieval Augmented Generation",
        "rag",
        "2401.15884",
        (
            "Which paper introduces a corrective retrieval evaluator for RAG?",
            "What RAG method triggers web search when retrieved documents are judged ambiguous or incorrect?",
        ),
    ),
    Paper(
        "agentic_rag_survey",
        "Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG",
        "rag",
        "2501.09136",
        (
            "Which survey defines a taxonomy of Agentic RAG systems by cardinality, control, autonomy, and knowledge representation?",
            "What paper surveys single-agent, multi-agent, and graph-based Agentic RAG architectures?",
        ),
    ),
    Paper(
        "ma_rag",
        "MA-RAG: Multi-Agent Retrieval-Augmented Generation",
        "rag",
        "2505.20096",
        (
            "Which paper proposes planner, step definer, extractor, and QA agents for multi-agent RAG?",
            "What Multi-Agent RAG framework addresses ambiguities and reasoning challenges in complex information-seeking tasks?",
        ),
    ),
    Paper(
        "react",
        "ReAct: Synergizing Reasoning and Acting in Language Models",
        "agent",
        "2210.03629",
        (
            "Which paper synergizes reasoning traces and task-specific actions in language models?",
            "What method interleaves chain-of-thought reasoning with external actions for language agents?",
        ),
    ),
    Paper(
        "toolformer",
        "Toolformer: Language Models Can Teach Themselves to Use Tools",
        "agent",
        "2302.04761",
        (
            "Which paper shows that language models can teach themselves to use external tools?",
            "What work adds API call annotations so a language model learns tool use in a self-supervised way?",
        ),
    ),
    Paper(
        "reflexion",
        "Reflexion: Language Agents with Verbal Reinforcement Learning",
        "agent",
        "2303.11366",
        (
            "Which paper proposes verbal reinforcement learning for language agents?",
            "What agent method stores self-reflective feedback in memory to improve future trials?",
        ),
    ),
    Paper(
        "voyager",
        "Voyager: An Open-Ended Embodied Agent with Large Language Models",
        "agent",
        "2305.16291",
        (
            "Which paper introduces an open-ended embodied agent in Minecraft with a skill library?",
            "What agent autonomously explores, acquires skills, and stores executable programs in a skill library?",
        ),
    ),
    Paper(
        "agent_architecture_survey",
        "The Landscape of Emerging AI Agent Architectures",
        "agent",
        "2404.11584",
        (
            "Which survey reviews AI agent architectures for reasoning, planning, and tool execution?",
            "What paper analyzes emerging agent architecture patterns for complex goal execution?",
        ),
    ),
    Paper(
        "resnet",
        "Deep Residual Learning for Image Recognition",
        "cv",
        "1512.03385",
        (
            "Which computer vision paper introduced residual learning and ResNet for image recognition?",
            "What architecture uses identity shortcut connections to train very deep neural networks?",
        ),
    ),
    Paper(
        "vision_transformer",
        "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
        "cv",
        "2010.11929",
        (
            "Which paper introduced the Vision Transformer by splitting images into patches?",
            "What model treats 16 by 16 image patches as tokens for image classification?",
        ),
    ),
    Paper(
        "detr",
        "End-to-End Object Detection with Transformers",
        "cv",
        "2005.12872",
        (
            "Which paper formulates object detection as a direct set prediction problem with transformers?",
            "What object detector removes hand-designed anchors and non-maximum suppression using a transformer decoder?",
        ),
    ),
    Paper(
        "sam",
        "Segment Anything",
        "cv",
        "2304.02643",
        (
            "Which paper introduces a promptable segmentation model and the SA-1B dataset?",
            "What foundation model enables zero-shot segmentation from points, boxes, masks, and text prompts?",
        ),
    ),
    Paper(
        "sam2",
        "SAM 2: Segment Anything in Images and Videos",
        "cv",
        "2408.00714",
        (
            "Which paper extends Segment Anything to promptable visual segmentation in videos?",
            "What model uses streaming memory for real-time video segmentation?",
        ),
    ),
)


def write_eval_config() -> None:
    source = PROJECT_ROOT / "backend" / "knowledge" / "modular_rag_settings.yaml"
    text = source.read_text(encoding="utf-8")
    text = text.replace("  enabled: true\n  provider: \"qwen\"\n  model: \"qwen-vl-plus\"", "  enabled: false\n  provider: \"qwen\"\n  model: \"qwen-vl-plus\"")
    EVAL_CONFIG.write_text(text, encoding="utf-8")


def download_papers() -> list[dict[str, Any]]:
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    downloads: list[dict[str, Any]] = []
    for paper in PAPERS:
        target = PAPERS_DIR / paper.filename
        status = "exists" if target.exists() and target.stat().st_size > 20_000 else "downloaded"
        if status == "downloaded":
            request = urllib.request.Request(paper.url, headers={"User-Agent": "asteria-rag-eval/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = response.read()
            except urllib.error.URLError as exc:
                downloads.append({**asdict(paper), "path": str(target), "status": "failed", "error": str(exc)})
                continue
            target.write_bytes(data)
        downloads.append(
            {
                **asdict(paper),
                "path": str(target),
                "status": status,
                "bytes": target.stat().st_size if target.exists() else 0,
            }
        )
    return [item for item in downloads if item.get("status") != "failed"]


def source_matches(item: dict[str, Any], expected_filename: str) -> bool:
    metadata = item.get("metadata") or {}
    haystack = " ".join(
        str(value)
        for value in [
            metadata.get("source_path"),
            metadata.get("source"),
            metadata.get("title"),
            item.get("title"),
            item.get("doc_id"),
        ]
        if value
    ).lower()
    return expected_filename.lower() in haystack


def rebuild_full_bm25(collection: str) -> dict[str, Any]:
    """Rebuild the BM25 index from the full Chroma collection.

    The upstream ingestion pipeline builds BM25 from the current file's chunks.
    For a formal multi-document evaluation, rebuild once from all persisted
    chunks so sparse retrieval and RRF share the same corpus as dense retrieval.
    """
    if str(MODULAR_ROOT) not in sys.path:
        sys.path.insert(0, str(MODULAR_ROOT))

    from src.core.settings import resolve_path
    from src.ingestion.embedding.sparse_encoder import SparseEncoder
    from src.ingestion.storage.bm25_indexer import BM25Indexer
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory

    from backend.knowledge.modular_rag import get_modular_bridge

    bridge = get_modular_bridge()
    vector_store = VectorStoreFactory.create(bridge.settings, collection_name=collection)
    raw = vector_store.collection.get(include=["documents", "metadatas"])
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
    }


def stage_metrics(results: list[dict[str, Any]], expected_filename: str) -> dict[str, float]:
    rank = None
    for index, item in enumerate(results[:10], start=1):
        if source_matches(item, expected_filename):
            rank = index
            break
    return {
        "hit@10": 1.0 if rank is not None else 0.0,
        "mrr@10": 1.0 / rank if rank else 0.0,
    }


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


async def run() -> dict[str, Any]:
    if "DASHSCOPE_API_KEY" not in os.environ:
        raise RuntimeError("DASHSCOPE_API_KEY is required for qwen3-rerank and Ragas")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_eval_config()
    successful_papers = download_papers()

    os.environ["MODULAR_RAG_MCP_CONFIG"] = str(EVAL_CONFIG)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from backend.knowledge.modular_rag import get_modular_bridge

    bridge = get_modular_bridge()
    started = time.perf_counter()
    ingest = await bridge.ingest(str(PAPERS_DIR), collection=COLLECTION, force=False)
    bm25_rebuild = rebuild_full_bm25(COLLECTION)

    test_cases: list[dict[str, Any]] = []
    by_file = {Path(item["path"]).name: item for item in successful_papers}
    for paper in successful_papers:
        filename = Path(paper["path"]).name
        for query in paper["queries"]:
            test_cases.append(
                {
                    "query": query,
                    "expected_filename": filename,
                    "expected_title": paper["title"],
                    "field": paper["field"],
                    "slug": paper["slug"],
                }
            )

    stage_rows: list[dict[str, Any]] = []
    stage_sums: dict[str, dict[str, float]] = {
        "dense": {"hit@10": 0.0, "mrr@10": 0.0, "latency_s": 0.0},
        "sparse": {"hit@10": 0.0, "mrr@10": 0.0, "latency_s": 0.0},
        "rrf": {"hit@10": 0.0, "mrr@10": 0.0, "latency_s": 0.0},
        "rerank": {"hit@10": 0.0, "mrr@10": 0.0, "latency_s": 0.0},
    }

    for case in test_cases:
        trace = await bridge.trace(case["query"], top_k=10, collection=COLLECTION)
        for stage in ["dense", "sparse", "rrf", "rerank"]:
            metrics = stage_metrics(trace["stages"].get(stage, []), case["expected_filename"])
            row = {**case, "stage": stage, **metrics, "latency_s": trace["latency_s"]}
            stage_rows.append(row)
            stage_sums[stage]["hit@10"] += metrics["hit@10"]
            stage_sums[stage]["mrr@10"] += metrics["mrr@10"]
            stage_sums[stage]["latency_s"] += trace["latency_s"]

    n = len(test_cases) or 1
    stage_summary = {
        stage: {
            "hit_rate@10": values["hit@10"] / n,
            "mrr@10": values["mrr@10"] / n,
            "avg_trace_latency_s": values["latency_s"] / n,
        }
        for stage, values in stage_sums.items()
    }

    # Run Ragas on a stratified subset: 2 CV, 2 RAG, 2 Agent queries.
    ragas_rows: list[dict[str, Any]] = []
    subset: list[dict[str, Any]] = []
    for field in ["cv", "rag", "agent"]:
        subset.extend([case for case in test_cases if case["field"] == field][:2])

    ragas_errors: list[dict[str, Any]] = []
    for case in subset:
        trace = await bridge.trace(case["query"], top_k=5, collection=COLLECTION)
        contexts = [item["content"] for item in trace["stages"].get("rerank", [])[:5] if item.get("content")]
        if not contexts:
            continue
        try:
            answer = await qwen_answer(case["query"], contexts)
            ragas = await bridge.ragas_score(
                query=case["query"],
                answer=answer,
                contexts=contexts,
                metrics=["faithfulness", "answer_relevancy", "context_precision"],
            )
            ragas_rows.append(
                {
                    **case,
                    "answer": answer,
                    "metrics": ragas["metrics"],
                    "latency_s": ragas["latency_s"],
                }
            )
        except Exception as exc:
            ragas_errors.append(
                {
                    **case,
                    "error": str(exc)[:1000],
                }
            )
            # The retrieval report is still useful for regression. Continue so
            # account/billing issues in the judge model do not erase the run.
            continue

    ragas_summary: dict[str, float] = {}
    if ragas_rows:
        keys = sorted({key for row in ragas_rows for key in row["metrics"].keys()})
        for key in keys:
            values = [row["metrics"][key] for row in ragas_rows if key in row["metrics"]]
            ragas_summary[key] = sum(values) / len(values)

    total_chunks = sum((item.get("chunk_count") or 0) for item in ingest.get("results", []))
    total_images = sum((item.get("image_count") or 0) for item in ingest.get("results", []))
    report = {
        "collection": COLLECTION,
        "config": str(EVAL_CONFIG),
        "paper_count": len(successful_papers),
        "query_count": len(test_cases),
        "fields": sorted(set(item["field"] for item in successful_papers)),
        "ingestion": {
            "processed": ingest.get("processed"),
            "successful": ingest.get("successful"),
            "failed": ingest.get("failed"),
            "chunk_count": max(total_chunks, bm25_rebuild["chunk_count"]),
            "image_count": total_images,
            "bm25_rebuild": bm25_rebuild,
        },
        "retrieval": {
            "summary": stage_summary,
            "rows": stage_rows,
        },
        "ragas": {
            "sample_count": len(ragas_rows),
            "summary": ragas_summary,
            "rows": ragas_rows,
            "errors": ragas_errors,
        },
        "papers": successful_papers,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Formal Modular RAG Evaluation",
        "",
        f"- Collection: `{report['collection']}`",
        f"- Papers: {report['paper_count']}",
        f"- Golden queries: {report['query_count']}",
        f"- Chunks: {report['ingestion']['chunk_count']}",
        f"- Ragas samples: {report['ragas']['sample_count']}",
        "",
        "## Retrieval Summary",
        "",
        "| Stage | Hit Rate@10 | MRR@10 | Avg Trace Latency (s) |",
        "|---|---:|---:|---:|",
    ]
    for stage, metrics in report["retrieval"]["summary"].items():
        lines.append(
            f"| {stage} | {metrics['hit_rate@10']:.3f} | "
            f"{metrics['mrr@10']:.3f} | {metrics['avg_trace_latency_s']:.3f} |"
        )
    lines.extend(["", "## Ragas Summary", ""])
    if report["ragas"]["summary"]:
        for key, value in report["ragas"]["summary"].items():
            lines.append(f"- {key}: {value:.3f}")
    else:
        lines.append("- No Ragas metrics computed.")
    if report["ragas"].get("errors"):
        lines.append(f"- Ragas errors: {len(report['ragas']['errors'])}")
        first = report["ragas"]["errors"][0]
        lines.append(f"- First error: {first.get('error', '')[:300]}")
    lines.extend(["", "## Papers", ""])
    for item in report["papers"]:
        lines.append(f"- [{item['field']}] {item['title']} (`{Path(item['path']).name}`)")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(
        {
            "collection": result["collection"],
            "paper_count": result["paper_count"],
            "query_count": result["query_count"],
            "ingestion": result["ingestion"],
            "retrieval_summary": result["retrieval"]["summary"],
            "ragas_summary": result["ragas"]["summary"],
            "report_json": str(REPORT_JSON),
            "report_md": str(REPORT_MD),
            "elapsed_s": result["elapsed_s"],
        },
        indent=2,
        ensure_ascii=False,
    ))
