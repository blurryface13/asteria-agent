"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { authFetch } from "@/helpers/auth";

interface CollectionInfo {
  collection: string;
  docs: number;
  chunks: number;
}

interface TraceItem {
  rank: number;
  chunk_id: string;
  doc_id: string;
  title: string;
  page: number | null;
  content: string;
  score: number;
  scores: Record<string, number>;
}

interface TraceData {
  engine?: string;
  query: string;
  collection: string | null;
  mode: string;
  rrf_k: number;
  latency_s: number;
  stages: Record<"dense" | "sparse" | "rrf" | "rerank", TraceItem[]>;
  mcp_tool_call: {
    server: string;
    tool: string;
    arguments: Record<string, unknown>;
    status: string;
  };
}

interface EvaluationData {
  engine?: string;
  corpus?: {
    documents: number;
    chunks: number;
    golden_queries: number;
    collections: { name: string; documents: number }[];
  };
  metrics?: {
    scenario: string;
    mode: string;
    hit10: number;
    mrr10: number;
    latency_s: number;
  }[];
  aggregate_metrics?: Record<string, number>;
  query_count?: number;
  total_elapsed_ms?: number;
  evaluator_name?: string;
  formal?: {
    golden_queries?: number;
    hit_rate10?: Record<string, number>;
    faithfulness?: {
      average: number | null;
      min: number | null;
      max: number | null;
      sample_count: number | null;
      errors: number | null;
    };
    elapsed_s?: number;
  } | null;
}

interface ModularStatus {
  engine: string;
  root: string;
  config: string;
  available: boolean;
  models: {
    llm: { provider: string; model: string };
    embedding: { provider: string; model: string; dimensions: number };
    rerank: { enabled: boolean; provider: string; model: string };
    vision: { enabled: boolean; provider: string | null; model: string | null };
  };
}

type RagEngine = "modular" | "local";

const stageLabels = {
  dense: "Dense",
  sparse: "BM25",
  rrf: "RRF",
  rerank: "Rerank",
};

const stageDescriptions = {
  dense: "semantic embedding",
  sparse: "keyword match",
  rrf: "rank fusion",
  rerank: "LLM precision pass",
};

export default function RagWorkspacePage() {
  const searchParams = useSearchParams();
  const [engine, setEngine] = useState<RagEngine>("modular");
  const [query, setQuery] = useState(
    searchParams.get("query") || "screen shooting resilient watermarking"
  );
  const [collection, setCollection] = useState(searchParams.get("collection") || "");
  const [ingestPath, setIngestPath] = useState("");
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [mode, setMode] = useState("hybrid_rerank");
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationData | null>(null);
  const [modularStatus, setModularStatus] = useState<ModularStatus | null>(null);
  const [loadingTrace, setLoadingTrace] = useState(false);
  const [loadingIngest, setLoadingIngest] = useState(false);
  const [loadingEval, setLoadingEval] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const collectionUrl = engine === "modular"
      ? "/api/knowledge/modular/collections"
      : "/api/knowledge/collections";
    authFetch(collectionUrl)
      .then((r) => (r.ok ? r.json() : { collections: [] }))
      .then((d) => setCollections(d.collections || []))
      .catch(() => {});

    setTrace(null);
    setEvaluation(null);
    setError("");

    if (engine === "local") {
      authFetch("/api/knowledge/evaluation")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setEvaluation(d))
        .catch(() => {});
      return;
    }

    authFetch("/api/knowledge/modular/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setModularStatus(d))
      .catch(() => {});
  }, [engine]);

  const bestMetrics = useMemo(() => {
    const rows = evaluation?.metrics || [];
    return rows.filter((row) => row.scenario === "watermark");
  }, [evaluation]);

  const runTrace = async () => {
    if (!query.trim() || loadingTrace) return;
    setLoadingTrace(true);
    setError("");
    try {
      const res = await authFetch(
        engine === "modular" ? "/api/knowledge/modular/trace" : "/api/knowledge/trace",
        {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          collection: collection || null,
          mode,
          top_k: 5,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || `Trace failed (${res.status})`);
      }
      setTrace(await res.json());
    } catch (e: any) {
      setError(e?.message || "Trace failed");
    } finally {
      setLoadingTrace(false);
    }
  };

  const runModularIngest = async () => {
    if (!ingestPath.trim() || loadingIngest) return;
    setLoadingIngest(true);
    setError("");
    try {
      const res = await authFetch("/api/knowledge/modular/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: ingestPath.trim(),
          collection: collection || "knowledge_hub",
          force: false,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || `Ingestion failed (${res.status})`);
      }
      const data = await res.json();
      setError(`Ingestion finished: ${data.successful}/${data.processed} files indexed.`);
    } catch (e: any) {
      setError(e?.message || "Ingestion failed");
    } finally {
      setLoadingIngest(false);
    }
  };

  const runModularEvaluation = async () => {
    if (loadingEval) return;
    setLoadingEval(true);
    setError("");
    try {
      const res = await authFetch("/api/knowledge/modular/evaluation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ collection: collection || "knowledge_hub", top_k: 10 }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || `Evaluation failed (${res.status})`);
      }
      setEvaluation(await res.json());
    } catch (e: any) {
      setError(e?.message || "Evaluation failed");
    } finally {
      setLoadingEval(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#fbfdfd] text-slate-900">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 lg:px-8">
        <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-teal-600">
              RAG Workspace
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">
              Research retrieval lab
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              Inspect ingestion scope, retrieval stages, MCP tool calls, and offline evaluation in one place.
            </p>
          </div>
          <nav className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setEngine("modular")}
              className={`rounded-full border px-3 py-2 text-sm font-semibold shadow-sm ${
                engine === "modular"
                  ? "border-teal-200 bg-teal-50 text-teal-700"
                  : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              Modular RAG MCP
            </button>
            <button
              onClick={() => setEngine("local")}
              className={`rounded-full border px-3 py-2 text-sm font-semibold shadow-sm ${
                engine === "local"
                  ? "border-teal-200 bg-teal-50 text-teal-700"
                  : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              Local Knowledge Hub
            </button>
            <Link
              href="/knowledge"
              className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:border-teal-200 hover:text-teal-700"
            >
              Knowledge Base
            </Link>
            <Link
              href="/"
              className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:border-teal-200 hover:text-teal-700"
            >
              Research Home
            </Link>
          </nav>
        </header>

        <section className="grid gap-4 lg:grid-cols-[0.9fr_1.45fr_0.85fr]">
          <aside className="rounded-lg border border-slate-200 bg-white/90 p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-950">Ingestion Pipeline</h2>
                <p className="mt-1 text-xs text-slate-500">
                  {engine === "modular" ? "external MCP project" : "current local corpus"}
                </p>
              </div>
              <span className="rounded-full bg-teal-50 px-2 py-1 text-xs font-semibold text-teal-700">
                indexed
              </span>
            </div>

            <div className="mt-5 space-y-3">
              {["PDF parse", "Chunk", "Embed", "Vector index", "BM25 index"].map((step, index) => (
                <div key={step} className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md border border-teal-100 bg-teal-50 text-xs font-bold text-teal-700">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-slate-800">{step}</p>
                    <p className="text-xs text-slate-400">
                      {index === 1 ? "1000 size / 150 overlap" : "ready"}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 grid grid-cols-2 gap-2">
              <MetricChip label="Docs" value={evaluation?.corpus?.documents || (engine === "local" ? 321 : "-")} />
              <MetricChip label="Chunks" value={evaluation?.corpus?.chunks || (engine === "local" ? 23269 : "-")} />
              <MetricChip label="Golden" value={evaluation?.corpus?.golden_queries || evaluation?.query_count || "-"} />
              <MetricChip label="RRF k" value={trace?.rrf_k || 60} />
            </div>

            {engine === "modular" && (
              <div className="mt-5 space-y-3">
                <div className="rounded-lg border border-slate-100 bg-[#fbfdfd] p-3 text-xs leading-5 text-slate-500">
                  <p className="font-semibold text-slate-800">Model stack</p>
                  <p>LLM: {modularStatus?.models.llm.provider || "deepseek"} / {modularStatus?.models.llm.model || "deepseek-chat"}</p>
                  <p>Embedding: {modularStatus?.models.embedding.provider || "ollama"} / {modularStatus?.models.embedding.model || "bge-m3"}</p>
                  <p>Vision: {modularStatus?.models.vision.enabled ? "enabled" : "disabled"}</p>
                </div>
                <input
                  value={ingestPath}
                  onChange={(e) => setIngestPath(e.target.value)}
                  className="min-h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs outline-none focus:border-teal-400"
                  placeholder="/path/to/papers"
                />
                <button
                  onClick={runModularIngest}
                  disabled={loadingIngest || !ingestPath.trim()}
                  className="w-full rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-100 disabled:opacity-40"
                >
                  {loadingIngest ? "Indexing..." : "Run Modular Ingest"}
                </button>
              </div>
            )}
          </aside>

          <section className="rounded-lg border border-slate-200 bg-white/95 p-4 shadow-sm">
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-3 md:flex-row">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      runTrace();
                    }
                  }}
                  className="min-h-11 flex-1 rounded-lg border border-slate-200 bg-[#fbfdfd] px-3 text-sm outline-none focus:border-teal-400"
                  placeholder="Ask a research query..."
                />
                <button
                  onClick={runTrace}
                  disabled={loadingTrace || !query.trim()}
                  className="min-h-11 rounded-lg bg-teal-600 px-5 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-40"
                >
                  {loadingTrace ? "Tracing..." : "Run Trace"}
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                <select
                  value={collection}
                  onChange={(e) => setCollection(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600"
                >
                  <option value="">All collections</option>
                  {collections.map((c) => (
                    <option key={c.collection} value={c.collection}>
                      {c.collection} ({c.docs})
                    </option>
                  ))}
                </select>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600"
                >
                  <option value="hybrid_rerank">Hybrid + rerank</option>
                  <option value="hybrid">Hybrid</option>
                </select>
                {trace && (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500">
                    {trace.latency_s}s
                  </span>
                )}
              </div>
            </div>

            {error && (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="mt-5 grid gap-3 xl:grid-cols-4">
              {(Object.keys(stageLabels) as Array<keyof typeof stageLabels>).map((stage) => (
                <StageColumn key={stage} stage={stage} items={trace?.stages?.[stage] || []} />
              ))}
            </div>
          </section>

          <aside className="rounded-lg border border-slate-200 bg-white/90 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-950">Evaluation</h2>
            <p className="mt-1 text-xs text-slate-500">offline golden-set snapshot</p>

            <div className="mt-4 space-y-3">
              {evaluation?.formal && (
                <div className="rounded-lg border border-teal-200 bg-teal-50/50 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-teal-900">
                      Formal Eval · combined corpus
                    </span>
                    <span className="text-xs text-teal-600">
                      {evaluation.formal.golden_queries ?? "-"} golden queries
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <div className="rounded-md bg-white p-2 text-center shadow-sm">
                      <div className="text-2xl font-bold text-teal-700">
                        {evaluation.formal.hit_rate10?.rerank != null
                          ? `${(evaluation.formal.hit_rate10.rerank * 100).toFixed(1)}%`
                          : "-"}
                      </div>
                      <div className="text-[11px] uppercase tracking-wide text-slate-500">
                        Hit Rate@10 (rerank)
                      </div>
                    </div>
                    <div className="rounded-md bg-white p-2 text-center shadow-sm">
                      <div className="text-2xl font-bold text-teal-700">
                        {evaluation.formal.faithfulness?.average != null
                          ? evaluation.formal.faithfulness.average.toFixed(3)
                          : "-"}
                      </div>
                      <div className="text-[11px] uppercase tracking-wide text-slate-500">
                        Faithfulness (n={evaluation.formal.faithfulness?.sample_count ?? "-"})
                      </div>
                    </div>
                  </div>
                  {evaluation.formal.hit_rate10 && (
                    <div className="mt-3 space-y-1">
                      {Object.entries(evaluation.formal.hit_rate10).map(([mode, v]) => (
                        <div key={mode} className="flex items-center gap-2">
                          <span className="w-14 text-[11px] text-slate-500">{mode}</span>
                          <div className="h-1.5 flex-1 rounded-full bg-slate-100">
                            <div className="h-1.5 rounded-full bg-teal-400" style={{ width: `${Math.round(v * 100)}%` }} />
                          </div>
                          <span className="w-12 text-right text-[11px] text-slate-500">{(v * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {engine === "modular" && evaluation?.aggregate_metrics && (
                <div className="rounded-lg border border-slate-100 bg-[#fbfdfd] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-800">
                      {evaluation.evaluator_name || "CustomEvaluator"}
                    </span>
                    <span className="text-xs text-slate-400">
                      {evaluation.total_elapsed_ms ? `${Math.round(evaluation.total_elapsed_ms)}ms` : ""}
                    </span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {Object.entries(evaluation.aggregate_metrics).map(([name, value]) => (
                      <div key={name}>
                        <div className="flex justify-between text-xs text-slate-500">
                          <span>{name}</span>
                          <span>{value.toFixed(3)}</span>
                        </div>
                        <div className="mt-1 h-2 rounded-full bg-slate-100">
                          <div className="h-2 rounded-full bg-teal-500" style={{ width: `${Math.round(value * 100)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {engine === "modular" && (
                <button
                  onClick={runModularEvaluation}
                  disabled={loadingEval}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:border-teal-200 hover:text-teal-700 disabled:opacity-40"
                >
                  {loadingEval ? "Evaluating..." : "Run Modular Eval"}
                </button>
              )}

              {engine === "local" && bestMetrics.map((row) => (
                <div key={row.mode} className="rounded-lg border border-slate-100 bg-[#fbfdfd] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-800">{row.mode}</span>
                    <span className="text-xs text-slate-400">{row.latency_s}s</span>
                  </div>
                  <div className="mt-3 h-2 rounded-full bg-slate-100">
                    <div
                      className="h-2 rounded-full bg-teal-500"
                      style={{ width: `${Math.round(row.hit10 * 100)}%` }}
                    />
                  </div>
                  <div className="mt-2 flex justify-between text-xs text-slate-500">
                    <span>Hit@10 {row.hit10.toFixed(3)}</span>
                    <span>MRR {row.mrr10.toFixed(3)}</span>
                  </div>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white/95 p-4 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-950">MCP Tool Calls</h2>
              <p className="mt-1 text-xs text-slate-500">
                {engine === "modular"
                  ? "These calls are backed by jerry-ai-dev/MODULAR-RAG-MCP-SERVER."
                  : "The same retrieval path can be exposed to report agents through MCP."}
              </p>
            </div>
            <Link
              href="/?openPreferences=mcp"
              className="rounded-full border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-100"
            >
              Configure MCP
            </Link>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {["query_knowledge_hub", "list_collections", "get_document_summary"].map((tool) => (
              <div key={tool} className="rounded-lg border border-slate-100 bg-[#fbfdfd] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-slate-800">{tool}</span>
                  <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                    ready
                  </span>
                </div>
                <pre className="mt-3 overflow-hidden rounded-md bg-slate-950/90 p-3 text-[11px] leading-5 text-slate-100">
{JSON.stringify(
  tool === "query_knowledge_hub"
    ? trace?.mcp_tool_call.arguments || { query, top_k: 5, collection: collection || null }
    : tool === "list_collections"
      ? {}
      : { doc_id: "selected paper" },
  null,
  2
)}
                </pre>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function MetricChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-[#fbfdfd] p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-bold text-slate-900">{value}</p>
    </div>
  );
}

function StageColumn({ stage, items }: { stage: keyof typeof stageLabels; items: TraceItem[] }) {
  return (
    <div className="min-h-[360px] rounded-lg border border-slate-100 bg-[#fbfdfd] p-3">
      <div className="mb-3">
        <h3 className="text-sm font-bold text-slate-900">{stageLabels[stage]}</h3>
        <p className="text-xs text-slate-400">{stageDescriptions[stage]}</p>
      </div>
      {items.length === 0 ? (
        <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-slate-200 text-center text-xs text-slate-400">
          Run trace to inspect candidates
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <details key={`${stage}-${item.chunk_id}`} className="rounded-lg border border-slate-200 bg-white p-2">
              <summary className="cursor-pointer list-none">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-teal-50 text-xs font-bold text-teal-700">
                    {item.rank}
                  </span>
                  <div className="min-w-0">
                    <p className="line-clamp-2 text-xs font-semibold leading-5 text-slate-800">
                      {item.title}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      score {item.score}
                      {item.page != null ? ` · p.${item.page}` : ""}
                    </p>
                  </div>
                </div>
              </summary>
              <p className="mt-2 text-xs leading-5 text-slate-500">{item.content}</p>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
