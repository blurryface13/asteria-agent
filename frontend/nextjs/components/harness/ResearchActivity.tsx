"use client";
import { useState } from "react";
import s from "./activity.module.css";

const labels: Record<string, string> = {search: "检索论文", read: "读取原文", references: "追踪参考文献",
  retrieve: "检索证据片段", delegate: "委派研究", request_user: "等待确认", finish: "汇总发现",
  agent: "研究任务", skill: "研究规范", plan: "研究计划", write: "综合写作", publish: "编译与交付", dependency_check: "依赖检查",
  read_passage: "阅读原文页段", sufficiency: "研究充分性审查", assessment_check: "审查证据校验", report_check: "报告校验", run: "研究运行"};
const stateLabels: Record<string, string> = {started: "进行中", completed: "已完成", failed: "失败",
  incomplete: "带缺口回传", partial: "部分读取失败", waiting: "待确认"};
function parse(value: any) {
  if (typeof value !== "string") return value;
  try { return JSON.parse(value); } catch { return null; }
}
function safeUrl(value: string) {
  try { const u = new URL(value); return u.protocol === "https:" ? u.href : undefined; } catch { return undefined; }
}

export default function ResearchActivity({logs, done, active}: {logs: any[]; done: boolean; active: boolean}) {
  const [selected, setSelected] = useState("");
  const events = logs.filter(l => l.header === "agent_action").map(l => parse(l.text)).filter(Boolean);
  const graph = [...logs].reverse().find(l => l.header === "citation_graph");
  const data = graph ? parse(graph.text) : null;
  const groups = new Map<string, any[]>();
  events.forEach(e => {
    const group = groups.get(e.agent) || [];
    const existing = e.call_id ? group.findIndex(x => x.call_id === e.call_id) : -1;
    if (existing >= 0) group[existing] = {...group[existing], ...e}; else group.push(e);
    groups.set(e.agent, group);
  });
  const latest = events.at(-1);
  const actions = Array.from(groups.values()).flat();
  const attempts = actions.filter(e => (e.status === "failed" || e.status === "partial") && e.severity !== "fatal");
  // A child handoff is not a run failure. Keep one gap record per agent,
  // rather than counting both finish and agent lifecycle events.
  const gaps = Array.from(groups.entries()).filter(([, records]) =>
    [...records].reverse().find(e => e.tool === "agent")?.status === "incomplete");
  const fatal = [...events].reverse().find(e => e.severity === "fatal");
  const transportFailure = [...logs].reverse().find(l => l.header === "error");
  const taskError = fatal?.error || transportFailure?.text;
  const childCount = Array.from(groups.keys()).filter(name => name.startsWith("researcher-")).length;
  const nodes: any[] = data?.nodes || [], edges: any[] = data?.edges || [];
  const focus = nodes.find(n => n.id === selected) || nodes.find(n => edges.some(e => e.source === n.id)) || nodes[0];
  const related = focus ? edges.filter(e => e.source === focus.id || e.target === focus.id) : [];
  const neighbors = nodes.filter(n => related.some(e => e.source === n.id || e.target === n.id) && n.id !== focus?.id);
  return <section className={s.activity} aria-label="研究活动">
    <div className={s.current} role="status">
      <span className={taskError ? s.failedDot : done ? s.done : s.dot} />
      <span>{taskError ? "研究任务失败" : done ? "研究与交付已完成" : !active ? "研究已停止，可展开查看执行记录" : latest?.purpose || "正在组织研究"}</span>
    </div>
    <details>
      <summary>{groups.size > 0 ? `${childCount} 个研究子任务 · ${events.filter(e => e.status === "completed" && e.call_id).length} 次操作完成` : "查看执行过程"}</summary>
      {Array.from(groups.entries()).map(([agent, actions]) => <details className={s.agent} key={agent}>
        <summary>{agent === "lead" ? "主 Agent" : agent === "assessor" ? "充分性审查 Agent" : agent.split(":").slice(1).join(":") || agent}<small>{actions.length} 项活动</small></summary>
        {actions.map((event, i) => <details className={s.action} key={event.call_id || `${event.tool}-${i}`}>
          <summary><span>{labels[event.tool] || event.tool}</span><span className={s.purpose}>{event.purpose}</span>
            <small data-error={event.status === "failed"}>{stateLabels[event.status] || event.status}{event.seconds != null ? ` · ${event.seconds}s` : ""}</small></summary>
          {event.skills?.map((skill: any) => <details key={skill.id}><summary>
            {skill.title || skill.id} · v{skill.version} · {skill.origin === "user" ? "用户指定" : skill.origin === "system" ? "系统契约" : "Agent 自选"}
          </summary><pre>{JSON.stringify(skill, null, 2)}</pre></details>)}
          {event.format_profile && <p>报告版式：{event.format_profile === "brief" ? "研究简报" : event.format_profile === "academic" ? "学术报告" : event.format_profile}</p>}
          <pre>{JSON.stringify({arguments: event.arguments, skill: event.skill, plan: event.plan, result: event.result, error: event.error}, null, 2)}</pre>
        </details>)}
      </details>)}
      <details className={s.debug}><summary>原始事件（调试）</summary><pre>{JSON.stringify(logs, null, 2)}</pre></details>
    </details>
    {taskError && <p className={s.fatal} role="alert">{String(taskError)}</p>}
    {attempts.length > 0 && <details className={s.warning}><summary>{attempts.length} 次失败或部分失败的尝试</summary>
      <p className={s.note}>保留每次调用结果，不等同于整项任务失败；后续是否修正可在执行记录中查看。</p>
      {attempts.map((e, i) => <details key={i}><summary>{labels[e.tool] || e.tool}：{e.purpose}</summary>
        <pre>{JSON.stringify(e.error || e.result || e, null, 2)}</pre></details>)}</details>}
    {gaps.length > 0 && <details className={s.warning}><summary>{gaps.length} 项研究曾带缺口回传</summary>
      {gaps.map(([agent, records]) => <p key={agent}>{agent}：{[...records].reverse().find(e => e.tool === "agent")?.result?.summary || "阶段性研究未覆盖全部分配目标"}</p>)}</details>}
    {data && <details className={s.graph}>
      <summary>论文与引用关系 · {nodes.length} 篇发现 · {nodes.filter(n => n.status === "read").length} 篇已读 · {edges.length} 条引用</summary>
      <p className={s.note}>箭头由引用论文指向被引论文。仅显示实际参考文献与标题核验得到的关系，不代表完整学术引用网络。</p>
      <select aria-label="选择引用图中心论文" value={focus?.id || ""} onChange={e => setSelected(e.target.value)}>
        {nodes.map(n => <option key={n.id} value={n.id}>{n.title} · {n.status === "read" ? "已读" : "未读"}</option>)}
      </select>
      {focus && neighbors.length > 0 ? <svg viewBox="0 0 640 340" role="img" aria-label="所选论文的一跳引用关系">
        <defs><marker id="citation-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="currentColor" /></marker></defs>
        {neighbors.map((n, i) => {
          const angle = i * Math.PI * 2 / neighbors.length, x = 320 + 240 * Math.cos(angle), y = 170 + 125 * Math.sin(angle);
          const outgoing = related.some(e => e.source === focus.id && e.target === n.id);
          return <g key={n.id}><line x1={outgoing ? 320 : x} y1={outgoing ? 170 : y} x2={outgoing ? x : 320} y2={outgoing ? y : 170} stroke="currentColor" opacity=".35" markerEnd="url(#citation-arrow)" />
            <circle cx={x} cy={y} r="8" fill={n.status === "read" ? "#8cbbac" : "#888b92"} />
            <text x={x} y={y + 22} textAnchor="middle" fill="currentColor" fontSize="10">{n.title.slice(0, 24)}<title>{n.title}</title></text></g>;
        })}
        <circle cx="320" cy="170" r="11" fill="#b9c9df" /><text x="320" y="149" textAnchor="middle" fill="currentColor" fontSize="11">所选论文</text>
      </svg> : <p className={s.note}>这篇论文尚无已核实引用关系。</p>}
      <div className={s.edges}>{related.map((e, i) => <details key={i}><summary>
        {nodes.find(n => n.id === e.source)?.title || e.source} → {nodes.find(n => n.id === e.target)?.title || e.target}
      </summary><p>{e.evidence}</p><a href={safeUrl(e.target)} target="_blank" rel="noreferrer">查看被引论文</a></details>)}</div>
      <details><summary>全部论文与读取状态</summary>{nodes.map(n => <p key={n.id}><a href={safeUrl(n.url)} target="_blank" rel="noreferrer">{n.title}</a> · {n.status === "read" ? "已读" : n.status === "failed" ? "读取失败" : "仅发现"}</p>)}</details>
      {data.unresolved_references?.length > 0 && <details><summary>{data.unresolved_references.length} 条未解析参考文献</summary><pre>{JSON.stringify(data.unresolved_references, null, 2)}</pre></details>}
    </details>}
  </section>;
}
