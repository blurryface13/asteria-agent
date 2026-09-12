"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/helpers/auth";
import { ChatBoxSettings } from "@/types/data";
import s from "./skills.module.css";

type Skill = {id: string; title: string; kind: string; selectable: boolean; version: string;
  description: string; source: string; phases: string[]; content?: string; sha256?: string};
type Props = {settings: ChatBoxSettings; onChange: (settings: ChatBoxSettings) => void;
  locked: boolean; supported: boolean};
const phases: Record<string, string> = {research: "研究", writing: "写作", formatting: "输出契约"};

export default function SkillBrowser({settings, onChange, locked, supported}: Props) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [profiles, setProfiles] = useState<Record<string, {description: string}>>({});
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Skill | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const ids = settings.skill_ids || [];
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    authFetch("/api/workspace/skills", {signal: controller.signal, cache: "no-store"})
      .then(async response => {
        if (!response.ok) throw new Error("技能目录加载失败，请检查后端连接。");
        const data = await response.json();
        setSkills(data.skills); setProfiles(data.format_profiles);
        setSelected(current => current || data.skills.find((item: Skill) => item.selectable)?.id || "");
      }).catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setDetail(null); setError("");
    authFetch("/api/workspace/skills/" + encodeURIComponent(selected), {signal: controller.signal, cache: "no-store"})
      .then(async response => {
        if (!response.ok) throw new Error("技能正文加载失败。");
        setDetail(await response.json());
      }).catch(e => {if (!controller.signal.aborted) setError(e.message);});
    return () => controller.abort();
  }, [selected, revision]);
  const toggle = (skill: Skill) => {
    if (locked || !supported || !skill.selectable) return;
    const next = ids.includes(skill.id) ? ids.filter(id => id !== skill.id) :
      [...ids.filter(id => skill.kind !== "content" || skills.find(s => s.id === id)?.kind !== "content"), skill.id];
    onChange({...settings, skill_ids: next});
  };
  return <section className={s.browser} aria-label="技能目录">
    <header className={s.toolbar}>
      <input aria-label="搜索技能" placeholder="搜索技能" value={query} onChange={e => setQuery(e.target.value)} />
      <button disabled={locked || !supported} onClick={() => onChange({...settings, skill_ids: [], format_profile: null})}>
        {ids.length || settings.format_profile ? "恢复自动选择" : "自动选择"}
      </button>
    </header>
    <p className={s.hint}>{!supported ? "窄屏使用原有问答链路；可查看技能，桌面科研任务支持指定。" :
      locked ? "任务进行中，配置已锁定；展开执行记录查看实际加载结果。" :
      "仅本次科研任务：指定项必加载，其余由 Agent 按需选择。主要写作指导单选，辅助指导可叠加。"}</p>
    {error && <div role="alert" className={s.error}>{error} <button onClick={() => setRevision(v => v + 1)}>重试</button></div>}
    {loading ? <p role="status">加载技能目录…</p> : <div className={s.columns}>
      <div className={s.list} aria-label="可用技能">
        {skills.filter(item => (item.title + item.description + item.id).toLowerCase().includes(query.toLowerCase())).map(item =>
          <button key={item.id} aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}>
            <span>{item.title}</span><small>{ids.includes(item.id) ? "已指定" : item.selectable ? item.kind === "content" ? "写作" : "辅助" : "系统"}</small>
          </button>)}
        {!skills.some(item => (item.title + item.description + item.id).toLowerCase().includes(query.toLowerCase())) && <p>没有匹配的技能</p>}
      </div>
      <article className={s.detail} aria-label="技能详情" aria-busy={!detail}>
        {detail ? <>
          <header><h3>{detail.title}</h3><span>v{detail.version}</span></header>
          <p>{detail.description}</p>
          <div className={s.meta}>{detail.phases.map(p => phases[p]).join(" · ")} · {detail.kind === "content" ? "内容指导" : detail.selectable ? "辅助指导" : "运行约束"}</div>
          {detail.selectable && <label className={s.pin}>
            <input type="checkbox" checked={ids.includes(detail.id)} disabled={locked || !supported} onChange={() => toggle(detail)} />
            本次任务指定
          </label>}
          <details><summary>查看指导正文</summary><pre>{detail.content}</pre></details>
          <footer>{detail.source}<details><summary>版本指纹</summary><code>{detail.id} · SHA-256: {detail.sha256}</code></details></footer>
        </> : <p role="status">读取技能正文…</p>}
      </article>
    </div>}
    <div className={s.format}>
      <label htmlFor="skill-format">报告版式</label>
      <select id="skill-format" disabled={locked || !supported} value={settings.format_profile || ""}
        onChange={e => onChange({...settings, format_profile: e.target.value || null})}>
        <option value="">Agent 自动选择</option>
        {Object.keys(profiles).map(id => <option key={id} value={id}>{id === "academic" ? "学术报告 · 衬线 / 编号章节" : id === "brief" ? "研究简报 · 无衬线 / 紧凑" : id}</option>)}
      </select>
      <small>内容指导与版式独立组合；不改变工具权限。</small>
    </div>
  </section>;
}
