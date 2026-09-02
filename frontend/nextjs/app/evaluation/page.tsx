"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { authFetch } from "@/helpers/auth";

type Trace = { trace_id: string; name: string; spans: any[]; source_batch_id?: string };
type BadCase = { badcase_id: string; trace_id: string; failure_type: string; failure_reason: string; suggested_dimensions: string[] };
type Dimension = { dimension_id: string; path: string; label: string; description: string };

export default function EvaluationPage() {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [badcases, setBadcases] = useState<BadCase[]>([]);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [selected, setSelected] = useState<Trace | null>(null);
  const [message, setMessage] = useState("");

  const refresh = async () => {
    const [traceRes, badcaseRes, dimensionRes] = await Promise.all([
      authFetch("/api/evaluation/traces"), authFetch("/api/evaluation/badcases"), authFetch("/api/evaluation/dimensions"),
    ]);
    if (traceRes.ok) setTraces((await traceRes.json()).traces || []);
    if (badcaseRes.ok) setBadcases((await badcaseRes.json()).badcases || []);
    if (dimensionRes.ok) setDimensions((await dimensionRes.json()).dimensions || []);
  };

  useEffect(() => { refresh().catch(() => setMessage("评测服务暂不可用，请先启动 Asteria 后端")); }, []);

  const stats = useMemo(() => ({ traces: traces.length, spans: traces.reduce((sum, item) => sum + item.spans.length, 0), badcases: badcases.length }), [traces, badcases]);

  const analyze = async (traceId: string) => {
    const response = await authFetch(`/api/evaluation/badcases/from-trace/${traceId}`, { method: "POST" });
    setMessage(response.ok ? "已完成 BadCase 分析" : "BadCase 分析失败");
    await refresh();
  };

  return (
    <main className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <div className="mx-auto flex max-w-7xl gap-6 px-6 py-8">
        <aside className="hidden w-56 shrink-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:block">
          <div className="mb-7 text-lg font-semibold">GoodQuestion Lab</div>
          <nav className="space-y-1 text-sm">
            {["评测概览", "BadCase 日志", "种子题库", "生成任务", "专家质检"].map((item, index) => <div key={item} className={`rounded-lg px-3 py-2 ${index === 0 ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-500"}`}>{item}</div>)}
          </nav>
          <Link href="/" className="mt-8 block text-xs text-slate-400 hover:text-indigo-600">← 返回科研 Agent</Link>
        </aside>
        <section className="min-w-0 flex-1">
          <div className="mb-6 flex items-end justify-between">
            <div><p className="text-xs font-medium uppercase tracking-[0.2em] text-indigo-500">Agent Evaluation</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">科研 Agent 评测中心</h1><p className="mt-2 text-sm text-slate-500">Trace 归档、BadCase 回流、维度扩展与回归验证</p></div>
            <button onClick={() => refresh()} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 shadow-sm hover:border-indigo-300">刷新</button>
          </div>
          {message && <div className="mb-4 rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">{message}</div>}
          <div className="grid gap-4 sm:grid-cols-3">
            {[["Trace 批次", stats.traces], ["执行 Span", stats.spans], ["待处理 BadCase", stats.badcases]].map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-sm text-slate-500">{label}</div><div className="mt-2 text-2xl font-semibold">{value}</div></div>)}
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 px-5 py-4"><h2 className="font-semibold">BadCase 日志 / Trace 归档</h2><p className="mt-1 text-xs text-slate-400">支持按父子关系查看 Agent、LLM、Tool 执行轨迹</p></div><div className="divide-y divide-slate-100">{traces.length === 0 && <p className="p-5 text-sm text-slate-400">尚未导入 Trace JSONL</p>}{traces.map(trace => <div key={trace.trace_id} className="cursor-pointer px-5 py-4 hover:bg-slate-50" onClick={() => setSelected(trace)}><div className="flex items-center justify-between"><div><div className="font-medium">{trace.name}</div><div className="mt-1 font-mono text-xs text-slate-400">{trace.trace_id}</div></div><button onClick={(event) => { event.stopPropagation(); analyze(trace.trace_id); }} className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs text-white hover:bg-indigo-700">分析 BadCase</button></div><div className="mt-3 flex gap-3 text-xs text-slate-500"><span>{trace.spans.length} spans</span><span>{trace.spans.filter(s => s.kind === "llm").length} LLM</span><span>{trace.spans.filter(s => s.kind === "tool").length} Tools</span></div></div>)}</div></div>
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 px-5 py-4"><h2 className="font-semibold">失败样本与评测维度</h2><p className="mt-1 text-xs text-slate-400">规则归因结果可继续回流种子题库</p></div><div className="p-5">{badcases.length > 0 ? <div className="space-y-3">{badcases.slice(0, 5).map(item => <div key={item.badcase_id} className="rounded-lg border border-amber-100 bg-amber-50 p-3"><div className="flex justify-between text-xs"><span className="font-medium text-amber-800">{item.failure_type}</span><span className="text-amber-600">candidate</span></div><p className="mt-1 text-sm text-slate-700">{item.failure_reason}</p><div className="mt-2 flex flex-wrap gap-1">{item.suggested_dimensions.map(d => <span key={d} className="rounded bg-white px-2 py-0.5 text-[10px] text-slate-500">{d}</span>)}</div></div>)}</div> : <p className="text-sm text-slate-400">选择 Trace 并执行分析后，这里会展示失败证据。</p>}<div className="mt-6 border-t border-slate-100 pt-4"><div className="text-xs font-medium text-slate-500">当前维度目录</div><div className="mt-2 flex flex-wrap gap-1.5">{dimensions.slice(0, 8).map(item => <span key={item.dimension_id} title={item.description} className="rounded-full border border-slate-200 px-2 py-1 text-[10px] text-slate-500">{item.label}</span>)}</div></div></div></div>
          </div>
          {selected && <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><h2 className="font-semibold">Trace 详情：{selected.name}</h2><button onClick={() => setSelected(null)} className="text-sm text-slate-400">关闭</button></div><div className="mt-4 space-y-2">{selected.spans.map(span => <div key={span.span_id} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs"><span className="w-16 rounded bg-white px-2 py-1 text-center text-slate-500">{span.kind}</span><span className="font-medium">{span.name}</span><span className="ml-auto text-slate-400">{span.duration_ms ? `${Math.round(span.duration_ms)} ms` : "—"}</span><span className={span.status === "error" ? "text-red-600" : "text-emerald-600"}>{span.status}</span></div>)}</div></div>}
        </section>
      </div>
    </main>
  );
}
