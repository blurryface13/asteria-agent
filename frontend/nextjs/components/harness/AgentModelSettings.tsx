"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/helpers/auth";
import { getHost } from "@/helpers/getHost";
import s from "./harness.module.css";

type Role = { role: string; model: string | null; has_key: boolean; key_tail: string | null };
const names: Record<string, string> = {
  intent_router: "意图路由", general_chat: "通用对话", research_lead: "Research Lead",
  research_subagent: "Search Subagent", coding_subagent: "代码子 Agent",
  data_analyst: "数据分析", writer: "报告写作", citation_agent: "引文核对",
  orchestrator_compose: "跨角色汇总", financial_research: "金融助手", company_research: "企业背调",
};

export default function AgentModelSettings() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [model, setModel] = useState("deepseek-chat");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("正在读取服务端配置…");
  const current = roles.find(row => row.role === selected);

  useEffect(() => {
    let live = true;
    authFetch(`${getHost()}/api/admin/agent-models`, {cache: "no-store"}).then(async response => {
      if (!response.ok) throw new Error(response.status === 403 ? "仅管理员可以配置模型" : "无法读取模型配置");
      return response.json();
    }).then(data => {
      if (!live) return;
      setRoles(data.roles || []);
      setSelected(data.roles?.[0]?.role || "");
      setModel(data.roles?.[0]?.model || "deepseek-chat");
      setStatus("");
    }).catch(error => { if (live) setStatus(error.message); });
    return () => { live = false; };
  }, []);

  function select(role: string) {
    setSelected(role);
    setModel(roles.find(row => row.role === role)?.model || "deepseek-chat");
    setKey("");
    setStatus("");
  }

  async function save(clearKey = false) {
    if (!selected || busy) return;
    setBusy(true);
    setStatus("正在保存…");
    try {
      const response = await authFetch(`${getHost()}/api/admin/agent-models/${selected}`, {
        method: "PUT", headers: {"Content-Type": "application/json"}, cache: "no-store",
        body: JSON.stringify({model, api_key: clearKey ? null : key.trim() || null, clear_key: clearKey}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "保存失败");
      setRoles(data.roles || []);
      setKey("");
      setStatus("已保存；新任务将使用此配置，运行中的任务不会切换。");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  return <div className={s.modelSettings}>
    <p>按角色配置 DeepSeek。未单独配置的角色继续使用服务端默认模型和密钥。密钥仅在保存时传输，之后不可查看。</p>
    {roles.length > 0 && <>
      <label>Agent 角色
        <select value={selected} onChange={event => select(event.target.value)} disabled={busy}>
          {roles.map(row => <option value={row.role} key={row.role}>{names[row.role] || row.role}</option>)}
        </select>
      </label>
      <label>模型
        <select value={model} onChange={event => setModel(event.target.value)} disabled={busy}>
          <option value="deepseek-chat">deepseek-chat</option>
          <option value="deepseek-reasoner">deepseek-reasoner</option>
        </select>
      </label>
      <label>此角色的 API Key（留空则保持原值）
        <input type="password" autoComplete="new-password" value={key} disabled={busy}
          onChange={event => setKey(event.target.value)} placeholder="输入新密钥以覆盖" />
      </label>
      <p>{current?.has_key ? `此角色已有独立密钥 · 尾号 ${current.key_tail}` : "此角色使用服务端默认密钥"}</p>
      <div className={s.modelActions}>
        <button className={s.primary} disabled={busy} onClick={() => save()}>保存配置</button>
        {current?.has_key && <button className={s.outline} disabled={busy} onClick={() => save(true)}>清除此角色密钥</button>}
      </div>
    </>}
    <p role="status" aria-live="polite">{status}</p>
  </div>;
}
