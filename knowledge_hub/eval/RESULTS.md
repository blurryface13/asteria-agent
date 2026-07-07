# Retrieval Evaluation Results

**Corpus**: 142 papers on physical-channel robust watermarking (screen-shooting / print-camera), 10,781 chunks from the lab's Zotero library.
**Golden set**: 60 auto-generated (query, expected-paper) pairs — deepseek-chat writes the research question a sampled mid-document chunk answers; human-spot-checked.
**Metric**: doc-level Hit Rate@k / MRR@10 (a hit = expected paper among the distinct source docs of top-k chunks).

| mode | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | avg latency |
|---|---|---|---|---|---|---|
| dense (bge-m3 + pgvector) | 0.567 | 0.900 | 0.950 | 0.950 | 0.727 | 0.27 s |
| sparse (BM25) | 0.667 | 0.883 | 0.917 | 0.950 | 0.778 | 0.08 s |
| hybrid (RRF fusion) | 0.550 | 0.900 | **0.967** | **1.000** | 0.731 | 0.20 s |
| hybrid + LLM rerank | 0.633 | **0.950** | **0.967** | 0.967 | **0.784** | 1.46 s |

## Findings

1. **Hybrid fusion wins on recall**: Hit@10 goes 95% → **100%** over either single retriever — dense and sparse miss *different* papers, and RRF captures the union.
2. **LLM rerank wins on precision**: Hit@3 90% → **95%**, MRR 0.731 → **0.784** (+7% relative) over plain fusion, at ~1.2 s extra latency per query (one deepseek-chat listwise call).
3. **BM25 is unusually strong at Hit@1** (0.667). Known bias: auto-generated queries reuse the source passage's exact terminology, favoring lexical match. A human-written query set would likely shift Hit@1 toward dense/hybrid. Worth remembering when reading row 2.
4. Latency budget: sparse 0.08 s < hybrid 0.20 s < dense 0.27 s < +rerank 1.46 s — mode is a per-call parameter, so callers pick their own precision/latency trade-off.

Reproduce:

```bash
python -m knowledge_hub.eval.build_golden --n 60
python -m knowledge_hub.eval.evaluate
```
