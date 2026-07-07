"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authFetch } from "@/helpers/auth";

interface Source {
  index: number;
  title: string;
  page: number | null;
  content: string;
  scores: Record<string, number>;
}

interface CollectionInfo {
  collection: string;
  docs: number;
  chunks: number;
}

export default function KnowledgePage() {
  const [question, setQuestion] = useState("");
  const [collection, setCollection] = useState<string>("");
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<string>("");
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    authFetch("/api/knowledge/collections")
      .then((r) => (r.ok ? r.json() : { collections: [] }))
      .then((d) => setCollections(d.collections || []))
      .catch(() => {});
  }, []);

  const ask = async () => {
    if (!question.trim() || loading) return;
    setLoading(true);
    setError("");
    setAnswer("");
    setSources([]);
    try {
      const res = await authFetch("/api/knowledge/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          collection: collection || null,
          mode: "hybrid_rerank",
          top_k: 5,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || `请求失败 (${res.status})`);
      }
      const data = await res.json();
      setAnswer(data.answer || "");
      setSources(data.sources || []);
    } catch (e: any) {
      setError(e?.message || "查询失败,请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const totalDocs = collections.reduce((s, c) => s + Number(c.docs), 0);

  return (
    <main className="min-h-screen bg-white text-gray-900">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">📚 Knowledge Hub</h1>
            <p className="mt-1 text-sm text-gray-500">
              实验室文献知识库问答 · 混合检索(BM25 + 语义) + 重排
              {totalDocs > 0 && ` · ${totalDocs} 篇论文`}
            </p>
          </div>
          <Link
            href="/"
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            ← 返回调研
          </Link>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask();
              }
            }}
            placeholder="例如:摩尔纹是怎么产生的?对屏摄水印提取有什么影响?"
            rows={3}
            className="w-full resize-none rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-teal-500"
          />
          <div className="mt-3 flex items-center justify-between">
            <select
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm text-gray-600"
            >
              <option value="">全部集合</option>
              {collections.map((c) => (
                <option key={c.collection} value={c.collection}>
                  {c.collection} ({c.docs} 篇)
                </option>
              ))}
            </select>
            <button
              onClick={ask}
              disabled={loading || !question.trim()}
              className="rounded-lg bg-teal-600 px-5 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-40"
            >
              {loading ? "检索与生成中..." : "提问"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {answer && (
          <div className="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-2 text-sm font-semibold uppercase text-gray-500">回答</h2>
            <div className="whitespace-pre-wrap text-[15px] leading-7 text-gray-800">{answer}</div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="mt-4">
            <h2 className="mb-2 text-sm font-semibold uppercase text-gray-500">
              引用来源({sources.length})
            </h2>
            <div className="space-y-2">
              {sources.map((s) => (
                <details
                  key={s.index}
                  className="rounded-lg border border-gray-200 bg-gray-50/60 p-3"
                >
                  <summary className="cursor-pointer text-sm text-gray-700">
                    <span className="font-mono text-teal-700">[{s.index}]</span>{" "}
                    <span className="font-medium">{s.title}</span>
                    {s.page != null && <span className="text-gray-400"> · p.{s.page}</span>}
                  </summary>
                  <p className="mt-2 text-xs leading-5 text-gray-600">{s.content}</p>
                  <p className="mt-1 text-[11px] text-gray-400">
                    {Object.entries(s.scores)
                      .map(([k, v]) => `${k}=${v}`)
                      .join("  ")}
                  </p>
                </details>
              ))}
            </div>
          </div>
        )}

        {!answer && !loading && !error && (
          <p className="mt-10 text-center text-sm text-gray-400">
            回答完全基于知识库中的论文内容生成,并附带可展开的原文引用。
          </p>
        )}
      </div>
    </main>
  );
}
