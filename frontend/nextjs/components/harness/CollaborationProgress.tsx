"use client";
import s from "./activity.module.css";

const statusNames: Record<string, string> = {started: "进行中", completed: "已回传", incomplete: "带缺口回传",
  failed: "失败", cancelled: "已取消", waiting: "等待调研答复"};
const seconds = (ms: unknown) => typeof ms === "number" && ms >= 0 ? `${(ms / 1000).toFixed(1)} 秒` : "—";

/** Partial results are evidence for the lead, never a substitute for acceptance. */
export default function CollaborationProgress({events, active}: {events: any[]; active: boolean}) {
  const batches = new Map<string, any>();
  const handoffs = new Map<string, any>();
  const arrivals = new Map<string, any>();
  events.forEach(e => {
    if (e.tool === "parallel_batch" && e.batch_id) batches.set(e.batch_id, {...batches.get(e.batch_id), ...e});
    if (e.tool === "research_handoff" && e.request_id) handoffs.set(e.request_id, {...handoffs.get(e.request_id), ...e});
    if (e.tool === "parallel_result" && e.batch_id) arrivals.set(`${e.batch_id}:${e.index}`, e);
  });
  if (!batches.size && !handoffs.size) return null;
  const state = (e: any) => !active && ["started", "waiting"].includes(e.status)
    ? "已停止，未收到完成记录" : statusNames[e.status] || e.status;
  return <section className={s.collaboration} aria-label="协作进展">
    <h3>分工与阶段结果</h3>
    <p className={s.note}>各路完成后立即回传；阶段结果尚未经最终验收，不等同于任务完成。</p>
    {Array.from(batches.entries()).map(([id, batch], i) => {
      const results = Array.from(arrivals.values()).filter(e => e.batch_id === id);
      const assignments = Array.isArray(batch.assignments) ? batch.assignments : [];
      return <div className={s.batch} key={id}>
        <div className={s.batchHeading}><span>第 {i + 1} 批 · {results.length}/{assignments.length} 项回传</span>
          <span>{state(batch)}</span></div>
        <details className={s.assignments}>
          <summary>查看分工与交付要求</summary>
          {assignments.map((a: any, index: number) => <div className={s.assignment} key={index}>
            <p><strong>{a.name}</strong> · {a.role === "coding" ? "代码／实验准备" : "调研"}</p>
            <p>{a.objective}</p><p className={s.note}>侧重：{a.focus || "未记录"} · 交付：{a.expected_output || "未记录"}</p>
            {a.exclude && <p className={s.note}>不包含：{a.exclude}</p>}
          </div>)}
        </details>
        {results.length > 0 ? <ol className={s.arrivals} aria-label={`第 ${i + 1} 批回传顺序`}>
          {results.map(e => <li key={e.index}>
            <div className={s.batchHeading}><strong>{e.assignment?.name || `子任务 ${e.index + 1}`}</strong>
              <span data-error={e.status === "failed"}>{state(e)} · 启动后 {seconds(e.since_dispatch_ms)}</span></div>
            {e.result?.summary && <details><summary>{String(e.result.summary).slice(0, 100)}{String(e.result.summary).length > 100 ? "…" : ""}</summary>
              <p className={s.finding}>{String(e.result.summary)}</p></details>}
          </li>)}
        </ol> : <p className={s.note}>{active && batch.status === "started" ? "子任务正在独立执行，尚无阶段结果。" : "本批没有已回传结果。"}</p>}
        {results.length > 0 && <p className={s.note}>首项回传 {seconds(batch.first_result_ms ?? results[0].since_dispatch_ms)}
          {batch.elapsed_ms != null && <> · 本批耗时 {seconds(batch.elapsed_ms)}</>}
          {batch.status === "completed" && " · 已交回 Lead，后续仍需验收"}</p>}
      </div>;
    })}
    {handoffs.size > 0 && <div className={s.handoffs}><h4>代码任务的定向求助</h4>
      {Array.from(handoffs.entries()).map(([id, e]) => <details key={id}>
        <summary>{e.request?.question || e.purpose} <span className={s.note}>· {state(e)}{e.wait_ms != null && ` · 等待 ${seconds(e.wait_ms)}`}</span></summary>
        {e.request?.observed_problem && <p>代码观察：{e.request.observed_problem}</p>}
        {e.result?.summary && <p className={s.finding}>{e.result.summary}</p>}
        <p className={s.note}>答复返回原代码 Loop；不会重新启动整个科研任务。</p>
      </details>)}
    </div>}
  </section>;
}
