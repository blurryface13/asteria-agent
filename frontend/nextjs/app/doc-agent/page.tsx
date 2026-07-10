"use client";

import { useState } from "react";
import Link from "next/link";
import { authFetch, getToken } from "@/helpers/auth";

interface TraceStep {
  type: string;
  step?: number;
  tool?: string;
  thought?: string;
  args?: Record<string, any>;
  result?: any;
}
interface Edit {
  edit_id: string;
  instruction: string;
  diff: string;
  revised_preview: string;
  citations: { title: string; page: number | null }[];
}

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg bg-gray-50 p-3 text-xs leading-5">
      {diff.split("\n").map((line, i) => {
        const cls = line.startsWith("+") && !line.startsWith("+++")
          ? "text-teal-700 bg-teal-50"
          : line.startsWith("-") && !line.startsWith("---")
          ? "text-red-600 bg-red-50"
          : "text-gray-500";
        return <div key={i} className={cls}>{line || " "}</div>;
      })}
    </pre>
  );
}

export default function DocAgentPage() {
  const [sessionId, setSessionId] = useState("");
  const [fileName, setFileName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [applied, setApplied] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const upload = async (f: File) => {
    setError("");
    const fd = new FormData();
    fd.append("file", f);
    const token = getToken();
    const res = await fetch("/api/doc-agent/upload", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    const d = await res.json();
    if (!res.ok) { setError(d?.detail || "上传失败"); return; }
    setSessionId(d.session_id);
    setFileName(d.file);
    setTrace([]); setEdits([]); setApplied({});
  };

  const revise = async () => {
    if (!sessionId || !instruction.trim() || loading) return;
    setLoading(true); setError(""); setTrace([]); setEdits([]);
    try {
      const res = await authFetch("/api/doc-agent/revise", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, file: fileName, instruction: instruction.trim() }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail || "改写失败");
      setTrace(d.trace || []);
      setEdits(d.edits || []);
    } catch (e: any) {
      setError(e?.message || "改写失败");
    } finally {
      setLoading(false);
    }
  };

  const apply = async (editId: string) => {
    const res = await authFetch("/api/doc-agent/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, edit_id: editId }),
    });
    const d = await res.json();
    if (res.ok) setApplied((p) => ({ ...p, [editId]: d.output_path }));
    else setError(d?.detail || "应用失败");
  };

  return (
    <main className="min-h-screen bg-white text-gray-900">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">✍️ 文档改写 Agent</h1>
            <p className="mt-1 text-sm text-gray-500">
              基于知识库溯源改写论文 · ReAct 自主工具调用 · 改动可预览可溯源
            </p>
          </div>
          <Link href="/" className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
            ← 返回
          </Link>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <label className="block text-sm font-medium text-gray-700">1. 上传文档 (.tex / .md / .txt / .docx)</label>
          <input
            type="file"
            accept=".tex,.md,.txt,.docx"
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            className="mt-2 block w-full text-sm text-gray-600 file:mr-3 file:rounded-lg file:border-0 file:bg-teal-50 file:px-3 file:py-1.5 file:text-teal-700"
          />
          {fileName && <p className="mt-2 text-xs text-teal-700">已上传: {fileName}</p>}

          <label className="mt-4 block text-sm font-medium text-gray-700">2. 改写指令</label>
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="例如:修正关于摩尔纹成因的错误说法,并基于知识库补充正确解释和引用"
            rows={2}
            disabled={!sessionId}
            className="mt-2 w-full resize-none rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-teal-500 disabled:bg-gray-50"
          />
          <button
            onClick={revise}
            disabled={!sessionId || !instruction.trim() || loading}
            className="mt-3 rounded-lg bg-teal-600 px-5 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-40"
          >
            {loading ? "Agent 工作中…" : "开始改写"}
          </button>
        </div>

        {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        {trace.length > 0 && (
          <div className="mt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase text-gray-500">Agent 决策轨迹 (ReAct)</h2>
            <div className="space-y-1">
              {trace.filter((t) => t.type === "action" || t.type === "final").map((t, i) => (
                <div key={i} className="flex items-start gap-2 rounded-lg border border-gray-100 bg-gray-50/60 p-2 text-xs">
                  {t.type === "action" ? (
                    <>
                      <span className="rounded bg-teal-100 px-1.5 py-0.5 font-mono text-teal-700">step {t.step}</span>
                      <span className="font-mono text-gray-700">🔧 {t.tool}</span>
                      <span className="text-gray-400">{t.args?.query || t.args?.path || t.args?.instruction?.slice(0, 40) || ""}</span>
                    </>
                  ) : (
                    <span className="text-gray-500">✅ {t.thought?.slice(0, 120)}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {edits.length > 0 && (
          <div className="mt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase text-gray-500">改写提案 ({edits.length})</h2>
            <div className="space-y-4">
              {edits.map((e) => (
                <div key={e.edit_id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                  <p className="mb-2 text-sm text-gray-600">{e.instruction}</p>
                  <DiffView diff={e.diff} />
                  {e.citations.length > 0 && (
                    <p className="mt-2 text-xs text-gray-500">
                      引用: {e.citations.map((c) => `${c.title}${c.page != null ? ` p.${c.page}` : ""}`).join(" · ")}
                    </p>
                  )}
                  {applied[e.edit_id] ? (
                    <p className="mt-3 text-xs text-teal-700">✅ 已应用到副本: {applied[e.edit_id]}</p>
                  ) : (
                    <button
                      onClick={() => apply(e.edit_id)}
                      className="mt-3 rounded-lg border border-teal-200 bg-teal-50 px-4 py-1.5 text-sm font-medium text-teal-700 hover:bg-teal-100"
                    >
                      确认应用 (写入副本,不改原文)
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
