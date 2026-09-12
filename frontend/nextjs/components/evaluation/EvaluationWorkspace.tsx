"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { authFetch } from "@/helpers/auth";
import { useWorkspace } from "@/hooks/useWorkspace";
import Icon from "@/components/harness/Icon";
import shell from "@/components/harness/harness.module.css";
import s from "./evaluation.module.css";

type RecordData = Record<string, unknown>;
type Span = RecordData & {
  span_id: string;
  parent_span_id?: string;
  name: string;
  kind: string;
  status: string;
  duration_ms?: number;
};
type Tab = "runs" | "batches" | "library" | "badcases" | "standards";
type Source =
  | "history"
  | "traces"
  | "tasks"
  | "reports"
  | "seeds"
  | "cases"
  | "generated-cases"
  | "badcases"
  | "dimensions";
const tabs: { id: Tab; label: string }[] = [
  { id: "runs", label: "运行记录" },
  { id: "batches", label: "评测批次" },
  { id: "library", label: "题库" },
  { id: "badcases", label: "BadCase" },
  { id: "standards", label: "评测标准" },
];
const sources: Record<Tab, { id: Source; label: string }[]> = {
  runs: [
    { id: "history", label: "研究历史" },
    { id: "traces", label: "Trace 归档" },
  ],
  batches: [
    { id: "tasks", label: "任务" },
    { id: "reports", label: "报告" },
  ],
  library: [
    { id: "seeds", label: "种子用例" },
    { id: "cases", label: "测试用例" },
    { id: "generated-cases", label: "生成用例" },
  ],
  badcases: [{ id: "badcases", label: "失败样本" }],
  standards: [{ id: "dimensions", label: "维度目录" }],
};
const text = (value: unknown, missing = "—") =>
  value == null || value === ""
    ? missing
    : typeof value === "string"
      ? value
      : JSON.stringify(value);
const recordId = (item: RecordData) =>
  text(
    item.badcase_id ??
      item.seed_id ??
      item.generated_id ??
      item.case_id ??
      item.task_id ??
      item.dimension_id ??
      item.id ??
      item.trace_id,
  );
const title = (item: RecordData) =>
  text(
    item.name ?? item.title ?? item.label ?? item.prompt ?? item.failure_reason,
    "未命名记录",
  );
const labels: Record<string, string> = {
  active: "可继续",
  archived: "已归档",
  completed: "已完成",
  failed: "失败",
  running: "运行中",
  pending: "待处理",
  candidate: "待质检",
  reviewed: "已审核",
  accepted: "已采纳",
  rejected: "已拒绝",
  passed: "已通过",
  needs_review: "待复核",
  ok: "正常",
  error: "异常",
  unset: "未标记",
};
const date = (item: RecordData) => {
  const value =
    item.updated_at ?? item.generated_at ?? item.imported_at ?? item.created_at;
  return value && !Number.isNaN(Date.parse(String(value)))
    ? new Date(String(value)).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
};
const status = (item: RecordData) =>
  text(item.status ?? item.quality_status ?? item.review_status, "未评分");
const duration = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${(value / 1000).toFixed(2)} s`
    : "N/A";

async function api(path: string, options?: RequestInit) {
  const response = await authFetch(`/api/evaluation/${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(text(data.detail, `请求失败（${response.status}）`));
  return data;
}

// Imported traces may contain orphaned or cyclic parents. Display every span once.
function TraceTree({ spans }: { spans: Span[] }) {
  const visited = new Set<string>();
  function node(span: Span, depth: number): React.ReactNode {
    if (visited.has(span.span_id)) return null;
    visited.add(span.span_id);
    const children = spans.filter(
      (child) =>
        child.parent_span_id === span.span_id && !visited.has(child.span_id),
    );
    return (
      <details key={span.span_id} className={s.span} open={depth === 0}>
        <summary>
          <span className={s.kind}>{span.kind}</span>
          <span>{span.name}</span>
          <small>{duration(span.duration_ms)}</small>
          <span className={s.badge} data-status={span.status}>
            {labels[span.status] || span.status}
          </span>
        </summary>
        <div className={s.spanBody}>
          {span.error != null && (
            <p className={s.failure}>{text(span.error)}</p>
          )}
          <details>
            <summary>输入 / 输出</summary>
            <pre>
              {JSON.stringify(
                {
                  input: span.input_messages,
                  arguments: span.tool_arguments,
                  output: span.output_messages,
                  result: span.tool_result,
                },
                null,
                2,
              )}
            </pre>
          </details>
          {children.map((child) => node(child, depth + 1))}
        </div>
      </details>
    );
  }
  const roots = spans.filter(
    (span) =>
      !span.parent_span_id ||
      !spans.some((parent) => parent.span_id === span.parent_span_id),
  );
  return (
    <div>
      {roots.map((span) => node(span, 0))}
      {spans
        .filter((span) => !visited.has(span.span_id))
        .map((span) => node(span, 0))}
    </div>
  );
}

export default function EvaluationWorkspace() {
  const workspace = useWorkspace();
  const [sidebar, setSidebar] = useState(true);
  const [username, setUsername] = useState("bunny");
  const [tab, setTab] = useState<Tab>("runs");
  const [source, setSource] = useState<Source>("history");
  const [rows, setRows] = useState<RecordData[]>([]);
  const [selected, setSelected] = useState<RecordData | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [content, setContent] = useState("");
  const [note, setNote] = useState("");
  const requestId = useRef(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setUsername(localStorage.getItem("asteria.displayName") || "bunny");
    if (window.matchMedia("(max-width: 899px)").matches) setSidebar(false);
  }, []);
  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    if (source === "history") {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await api(`${source}?limit=1000`);
      if (id !== requestId.current) return;
      const records = data[source.replaceAll("-", "_")];
      if (!Array.isArray(records)) throw new Error("评测接口返回格式不正确");
      setRows(records);
      setSelected((current) =>
        current
          ? records.find((item) => recordId(item) === recordId(current)) || null
          : null,
      );
    } catch (cause) {
      if (id === requestId.current)
        setError(cause instanceof Error ? cause.message : "评测服务不可用");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [source]);
  useEffect(() => {
    const generation = requestId;
    void refresh();
    return () => {
      generation.current++;
    };
  }, [refresh]);
  useEffect(() => {
    if (selected || importing) closeRef.current?.focus();
  }, [selected, importing]);
  const allRows: RecordData[] =
    source === "history"
      ? workspace.conversations
          .filter((item) => item.mode !== "chat")
          .map((item) => ({ ...item }))
      : rows;
  const visible = useMemo(
    () =>
      allRows.filter(
        (item) =>
          `${title(item)} ${recordId(item)} ${text(item.failure_type, "")}`
            .toLowerCase()
            .includes(query.toLowerCase()) &&
          (filter === "all" || status(item) === filter),
      ),
    [allRows, query, filter],
  );
  const pending = source === "history" ? workspace.loading : loading;
  const problem = error || (source === "history" ? workspace.error : null);
  function switchSource(next: Source) {
    if (busy || next === source) return;
    setSource(next);
    setRows([]);
    setSelected(null);
    setQuery("");
    setFilter("all");
    setError("");
    setNotice("");
    setImporting(false);
  }
  function switchTab(next: Tab) {
    if (busy) return;
    setTab(next);
    switchSource(sources[next][0].id);
  }
  function close() {
    setSelected(null);
    setImporting(false);
    listRef.current?.focus();
  }
  async function action(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api(path, {
        method,
        headers: { "Content-Type": "application/json" },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      setNotice(
        result.created === false
          ? "规则未发现失败，不代表质量评测通过。"
          : result.seed
            ? "已回流种子题库。"
            : result.count != null
              ? `已导入 ${result.count} 条轨迹。`
              : "已保存。",
      );
      if (result.count != null) {
        setImporting(false);
        setContent("");
      }
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main
      className={`${shell.shell} ${s.shell}`}
      data-sidebar={sidebar ? "open" : "closed"}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) close();
      }}
    >
      {sidebar && (
        <button
          className={shell.scrim}
          aria-label="关闭侧边栏"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside className={shell.rail} aria-label="工作台导航">
        <Link href="/" className={shell.brand}>
          <img src="/img/asteria-logo.png" alt="Asteria" />
          <span>个人</span>
        </Link>
        <nav>
          <Link href="/" className={shell.navItem}>
            <Icon name="new" />
            新任务
          </Link>
          <Link href="/knowledge" className={shell.navItem}>
            <Icon name="folder" />
            知识库
          </Link>
          <Link href="/rag-workspace" className={shell.navItem}>
            <Icon name="search" />
            检索问答
          </Link>
          <Link
            href="/evaluation"
            className={`${shell.navItem} ${shell.selected}`}
            aria-current="page"
          >
            <Icon name="grid" />
            评测中心
          </Link>
        </nav>
        <div className={shell.railScroll}>
          <div className={shell.group}>
            <summary>项目</summary>
            {workspace.projects.map((project) => (
              <details className={shell.projectTree} key={project.id}>
                <summary className={shell.project}>
                  <Icon name="folder" size={18} />
                  <span>{project.name}</span>
                </summary>
                <div className={shell.projectChildren}>
                  {workspace.conversations
                    .filter((item) => item.project_id === project.id)
                    .map((item) => (
                      <Link
                        className={shell.projectTask}
                        key={item.id}
                        href={`/?conversation=${encodeURIComponent(item.id)}`}
                      >
                        <Icon name="file" size={15} />
                        <span>{item.title}</span>
                      </Link>
                    ))}
                </div>
              </details>
            ))}
          </div>
          <div className={shell.group}>
            <summary>评测</summary>
            {tabs.map((item) => (
              <button
                className={`${shell.navItem} ${tab === item.id ? shell.selected : ""}`}
                key={item.id}
                aria-current={tab === item.id ? "page" : undefined}
                onClick={() => switchTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className={shell.user}>
          <span className={shell.avatar}>
            {username.slice(0, 1).toUpperCase()}
          </span>
          <span>{username}</span>
        </div>
      </aside>
      <section className={shell.workspace} aria-label="评测工作台">
        <header className={shell.topbar}>
          <button
            className={shell.iconButton}
            aria-label={sidebar ? "收起侧边栏" : "展开侧边栏"}
            aria-expanded={sidebar}
            onClick={() => setSidebar(!sidebar)}
          >
            <Icon name="panel" />
          </button>
          <span className={shell.taskPill}>
            <Icon name="grid" size={15} />
            评测中心
          </span>
          <span className={shell.spacer} />
          <Link href="/" className={s.back}>
            返回调研 <Icon name="arrow" size={15} />
          </Link>
        </header>
        <div className={s.layout}>
          <section className={s.content} ref={listRef} tabIndex={-1}>
            <div className={s.heading}>
              <h1>{tabs.find((item) => item.id === tab)?.label}</h1>
              <span className={s.muted}>
                {pending ? "加载中" : `${visible.length} 条`}
              </span>
              <span className={shell.spacer} />
              {source === "traces" && (
                <button
                  className={s.button}
                  onClick={() => {
                    setSelected(null);
                    setImporting(true);
                  }}
                >
                  <Icon name="plus" size={16} />
                  导入 JSONL
                </button>
              )}
              <button
                className={shell.iconButton}
                aria-label="刷新记录"
                disabled={pending || busy}
                onClick={() => {
                  setNotice("");
                  void (source === "history" ? workspace.refresh() : refresh());
                }}
              >
                <Icon name="refresh" size={18} />
              </button>
            </div>
            <div className={s.toolbar}>
              <div className={s.segments} aria-label="数据来源">
                {sources[tab].map((item) => (
                  <button
                    key={item.id}
                    aria-pressed={source === item.id}
                    onClick={() => switchSource(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <label className={s.search}>
                <Icon name="search" size={16} />
                <input
                  aria-label="搜索记录"
                  placeholder="搜索名称或 ID"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              {source !== "dimensions" && (
                <select
                  aria-label="筛选状态"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                >
                  <option value="all">全部状态</option>
                  {Array.from(new Set(allRows.map(status))).map((value) => (
                    <option key={value} value={value}>
                      {labels[value] || value}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {problem && (
              <div role="alert" className={s.failure}>
                {problem}{" "}
                <button
                  onClick={() =>
                    void (source === "history"
                      ? workspace.refresh()
                      : refresh())
                  }
                >
                  重试
                </button>
              </div>
            )}
            {notice && (
              <p role="status" className={s.notice}>
                {notice}
              </p>
            )}
            {source === "history" && (
              <p className={s.caption}>
                此处展示已保存的研究会话，会话状态不代表运行结果。历史补评待接入。
              </p>
            )}
            {source === "reports" && (
              <p className={s.caption}>
                既有执行器的规则评测报告；不等同于语义质量评分。
              </p>
            )}
            {source === "dimensions" && (
              <p className={s.caption}>
                当前目录用于失败归因与用例扩展。语义裁判与版本化评分另行接入。
              </p>
            )}
            <div className={s.list} aria-busy={pending}>
              <div className={s.columns}>
                <span>名称 / 内容</span>
                <span>{source === "dimensions" ? "路径" : "状态"}</span>
                <span>更新时间</span>
              </div>
              {!pending && !problem && visible.length === 0 && (
                <div className={s.empty}>
                  <Icon
                    name={query || filter !== "all" ? "search" : "file"}
                    size={28}
                  />
                  <h2>
                    {query || filter !== "all" ? "没有匹配记录" : "暂无记录"}
                  </h2>
                  <p>
                    {source === "traces"
                      ? "导入运行轨迹，查看 Agent 与工具调用。"
                      : source === "history"
                        ? "完成调研后，在这里查看运行记录。"
                        : "已有数据会显示在这里。"}
                  </p>
                </div>
              )}
              {pending && (
                <p role="status" className={s.empty}>
                  正在读取记录…
                </p>
              )}
              {!pending &&
                visible.map((item, index) => (
                  <button
                    key={`${recordId(item)}-${index}`}
                    disabled={busy}
                    className={s.row}
                    aria-pressed={
                      selected ? recordId(selected) === recordId(item) : false
                    }
                    onClick={() => {
                      setSelected(item);
                      setNote(text(item.review_note, ""));
                      setImporting(false);
                    }}
                  >
                    <span className={s.rowTitle}>
                      <span>{title(item)}</span>
                      <small>
                        {source === "traces"
                          ? `${Array.isArray(item.spans) ? item.spans.length : 0} 个节点 · `
                          : ""}
                        {recordId(item)}
                      </small>
                    </span>
                    <span className={s.badge} data-status={status(item)}>
                      {source === "dimensions"
                        ? text(item.path)
                        : labels[status(item)] || status(item)}
                    </span>
                    <time>{date(item)}</time>
                  </button>
                ))}
            </div>
            <footer className={s.footer}>
              {source === "history"
                ? "PostgreSQL · 项目与对话"
                : "评测资产 · 最多显示最近 1,000 条"}
              <span>缺失指标显示 N/A，不计为零分</span>
            </footer>
          </section>
          {(selected || importing) && (
            <aside
              className={s.detail}
              aria-label={importing ? "导入轨迹" : "记录详情"}
            >
              <header>
                <span>{importing ? "导入轨迹" : "记录详情"}</span>
                <button
                  ref={closeRef}
                  className={shell.iconButton}
                  aria-label="关闭详情"
                  onClick={close}
                  disabled={busy}
                >
                  <Icon name="close" size={18} />
                </button>
              </header>
              <div className={s.detailBody}>
                {error && (
                  <p role="alert" className={s.failure}>
                    {error}
                  </p>
                )}
                {importing ? (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void action("traces/import", {
                        content,
                        source_system: "manual",
                      });
                    }}
                  >
                    <h2>Trace JSONL</h2>
                    <p className={s.caption}>
                      每行一条轨迹或 Span。提交后保存到当前评测库。
                    </p>
                    <textarea
                      aria-label="JSONL 内容"
                      className={s.import}
                      placeholder={
                        '{"trace_id":"run-id","name":"研究任务","spans":[]}'
                      }
                      value={content}
                      onChange={(event) => setContent(event.target.value)}
                      required
                    />
                    <button
                      className={s.primary}
                      disabled={busy || !content.trim()}
                      type="submit"
                    >
                      {busy ? "正在导入…" : "导入轨迹"}
                    </button>
                  </form>
                ) : (
                  selected && (
                    <>
                      <h2>{title(selected)}</h2>
                      <code className={s.id}>{recordId(selected)}</code>
                      {source === "history" && (
                        <>
                          <dl>
                            <dt>会话状态</dt>
                            <dd>
                              {labels[status(selected)] || status(selected)}
                            </dd>
                            <dt>评测状态</dt>
                            <dd>尚未接入</dd>
                            <dt>运行模式</dt>
                            <dd>{text(selected.mode)}</dd>
                          </dl>
                          <Link
                            className={s.button}
                            href={`/?conversation=${encodeURIComponent(String(selected.id))}`}
                          >
                            <Icon name="file" size={16} />
                            打开研究记录
                          </Link>
                          <div className={s.planned}>
                            <button disabled className={s.button}>
                              评测此任务
                            </button>
                            <p>
                              下一步接入报告与证据快照，再对历史任务独立评分；不会重新发起调研。
                            </p>
                          </div>
                        </>
                      )}
                      {source === "traces" && (
                        <>
                          <button
                            className={s.button}
                            disabled={busy}
                            onClick={() =>
                              void action(
                                `badcases/from-trace/${encodeURIComponent(String(selected.trace_id))}`,
                              )
                            }
                          >
                            规则分析 BadCase
                          </button>
                          <p className={s.caption}>
                            检查已记录的工具、模型错误和失败证据。
                          </p>
                          <TraceTree
                            spans={
                              Array.isArray(selected.spans)
                                ? (selected.spans as Span[])
                                : []
                            }
                          />
                        </>
                      )}
                      {source === "badcases" && (
                        <>
                          <dl>
                            <dt>失败类型</dt>
                            <dd>{text(selected.failure_type)}</dd>
                            <dt>归因</dt>
                            <dd>{text(selected.failure_reason)}</dd>
                            <dt>关联轨迹</dt>
                            <dd>{text(selected.trace_id)}</dd>
                          </dl>
                          <h3>失败证据</h3>
                          <pre>
                            {JSON.stringify(selected.evidence ?? [], null, 2)}
                          </pre>
                          <label className={s.label}>
                            质检备注
                            <textarea
                              value={note}
                              onChange={(event) => setNote(event.target.value)}
                            />
                          </label>
                          <div className={s.actions}>
                            <button
                              className={s.button}
                              disabled={busy}
                              onClick={() =>
                                void action(
                                  `badcases/${encodeURIComponent(recordId(selected))}/review`,
                                  { status: "accepted", note },
                                  "PATCH",
                                )
                              }
                            >
                              采纳
                            </button>
                            <button
                              className={s.button}
                              disabled={busy}
                              onClick={() =>
                                void action(
                                  `badcases/${encodeURIComponent(recordId(selected))}/review`,
                                  { status: "rejected", note },
                                  "PATCH",
                                )
                              }
                            >
                              拒绝
                            </button>
                            <button
                              className={s.primary}
                              disabled={busy || selected.status !== "accepted"}
                              title="采纳后可回流种子题库"
                              onClick={() =>
                                void action(
                                  `seeds/from-badcase/${encodeURIComponent(recordId(selected))}`,
                                )
                              }
                            >
                              回流种子题库
                            </button>
                          </div>
                        </>
                      )}
                      {source === "reports" && (
                        <>
                          <p className={s.caption}>
                            旧版规则评分 · 按原始口径展示
                          </p>
                          <dl>
                            {[
                              ["样本数", selected.result_count],
                              ["规则成功率", selected.task_success_rate],
                              ["标题覆盖率", selected.average_outline_coverage],
                              [
                                "引用 URL 匹配率",
                                selected.average_citation_support_rate,
                              ],
                              [
                                "平均耗时",
                                duration(selected.average_latency_ms),
                              ],
                              ["P95 耗时", duration(selected.p95_latency_ms)],
                            ].map(([key, value]) => (
                              <div key={String(key)}>
                                <dt>{String(key)}</dt>
                                <dd>{text(value, "N/A")}</dd>
                              </div>
                            ))}
                          </dl>
                          <div className={s.planned}>
                            <button disabled className={s.button}>
                              重新评分
                            </button>
                            <button disabled className={s.button}>
                              重跑对比
                            </button>
                            <p>评分版本管理与自主运行时适配待接入。</p>
                          </div>
                        </>
                      )}
                      {source === "tasks" && (
                        <>
                          <dl>
                            <dt>状态</dt>
                            <dd>
                              {labels[status(selected)] || status(selected)}
                            </dd>
                            <dt>测试用例</dt>
                            <dd>{text(selected.case_ids)}</dd>
                            <dt>种子用例</dt>
                            <dd>{text(selected.seed_ids)}</dd>
                          </dl>
                          <div className={s.planned}>
                            <button disabled className={s.button}>
                              运行回归
                            </button>
                            <p>
                              当前执行器为旧链路。自主科研运行时接入前，不从这里发起模型任务。
                            </p>
                          </div>
                        </>
                      )}
                      {["seeds", "cases", "generated-cases"].includes(
                        source,
                      ) && (
                        <dl>
                          {[
                            ["任务输入", selected.prompt],
                            ["预期行为", selected.expected_behavior],
                            ["参考来源", selected.reference_urls],
                            ["必需里程碑", selected.required_milestones],
                            ["评测维度", selected.dimensions],
                            ["来源轨迹", selected.source_trace_id],
                          ].map(([key, value]) => (
                            <div key={String(key)}>
                              <dt>{String(key)}</dt>
                              <dd>{text(value)}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                      {source === "dimensions" && (
                        <dl>
                          <dt>路径</dt>
                          <dd>{text(selected.path)}</dd>
                          <dt>定义</dt>
                          <dd>{text(selected.description)}</dd>
                        </dl>
                      )}
                      <details className={s.raw}>
                        <summary>原始记录</summary>
                        <pre>{JSON.stringify(selected, null, 2)}</pre>
                      </details>
                    </>
                  )
                )}
              </div>
            </aside>
          )}
        </div>
      </section>
    </main>
  );
}
