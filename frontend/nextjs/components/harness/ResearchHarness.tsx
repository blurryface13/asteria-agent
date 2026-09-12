"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ResearchHistoryItem, ChatBoxSettings } from "@/types/data";
import { markdownToHtml } from "@/helpers/markdownHelper";
import Icon from "./Icon";
import s from "./harness.module.css";
import LatexPreview from "./LatexPreview";
import SkillBrowser from "./SkillBrowser";
import { useWorkspace } from "@/hooks/useWorkspace";

interface Props {
  skillsSupported?: boolean;
  selectedId?: string | null;
  history: ResearchHistoryItem[];
  active: boolean;
  question: string;
  answer: string;
  loading: boolean;
  chatting: boolean;
  stopped: boolean;
  prompt: string;
  setPrompt: (value: string) => void;
  chatPrompt: string;
  setChatPrompt: (value: string) => void;
  onResearch: (value: string) => void;
  onChat: (value: string) => void;
  onNew: () => void;
  onEnter: () => void;
  onStop: () => void;
  onSelect: (id: string) => void;
  settings: ChatBoxSettings;
  setSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
  logCount: number;
  artifactPaths?: Record<string, string>;
  children: React.ReactNode;
}

const scenarios = [
  [
    [
      "撰写文献综述",
      "筛选重要论文，梳理方法与证据，交付引用完整的结构化综述。",
      "请围绕【研究主题】撰写文献综述，对比主要方法、实验结论和研究空白，列出可核验的参考文献。",
    ],
    [
      "论文精读与对比",
      "拆解问题、方法与实验，比较多篇论文的贡献和局限。",
      "请对【论文名称或链接】进行精读，分析方法、实验设置、主要结论及局限。",
    ],
    [
      "分析科研数据",
      "整理数据与统计方法，生成图表和可复现的分析报告。",
      "请分析【数据集与问题】，先制定数据清洗、统计检验和可视化方案。",
    ],
    [
      "设计复现实验",
      "从论文到实验计划，明确环境、数据与验证标准。",
      "请为【论文或方法】设计复现实验计划，明确环境、数据、基线、指标与验收标准。",
    ],
  ],
  [
    [
      "技术方案调研",
      "检索一手资料，比较方案边界与适用条件。",
      "请调研【技术主题】，对比可选方案、适用场景与实现成本。",
    ],
    [
      "证据核验",
      "交叉核验来源，区分事实、推断与证据缺口。",
      "请核验【观点或结论】，提供一手来源并标明证据不足之处。",
    ],
    [
      "专题研究",
      "围绕问题建立证据链，输出结构化分析。",
      "请研究【专题】，明确研究问题并形成有引用支撑的报告。",
    ],
    [
      "报告审阅",
      "检查结构、论证与引用，给出修改建议。",
      "请评审【报告内容】，检查论证、引用及遗漏。",
    ],
  ],
  [
    [
      "开源项目调研",
      "梳理架构、依赖与扩展点，形成技术笔记。",
      "请调研【开源项目】，梳理架构、主要模块和部署方式。",
    ],
    [
      "实验环境规划",
      "整理依赖与运行要求，准备环境检查清单。",
      "请为【实验】制定环境与依赖检查清单。",
    ],
    [
      "基准测试设计",
      "确定基线、数据和指标，设计可重复测试。",
      "请为【系统】制定可复现的基准测试方案。",
    ],
    [
      "部署方案对比",
      "分析资源、性能与运维约束，比较部署路线。",
      "请对比【模型或系统】的部署方案和资源要求。",
    ],
  ],
  [
    [
      "公司深度调研",
      "梳理财报、行业与竞争格局，标注数据来源。",
      "请对【公司】进行调研，分析财报、行业与竞品，区分事实与假设。",
    ],
    [
      "行业趋势分析",
      "交叉核验公开信息，建立行业分析框架。",
      "请调研【行业】的技术趋势与竞争格局，提供来源。",
    ],
    [
      "公开数据分析",
      "明确数据口径，比较指标与变化趋势。",
      "请分析【公开数据】，说明来源、口径与局限。",
    ],
    [
      "产品竞品研究",
      "比较定位与能力，整理可追溯的竞品矩阵。",
      "请对比【产品列表】的定位、功能与适用场景。",
    ],
  ],
];

function Thumbnail({ kind }: { kind: number }) {
  return (
    <span className={`${s.thumbnail} ${s["thumb" + kind]}`} aria-hidden="true">
      <span className={s.paper}>
        <b>
          {
            [
              "LITERATURE REVIEW",
              "METHOD & RESULTS",
              "DATA ANALYSIS",
              "EXPERIMENT PLAN",
            ][kind]
          }
        </b>
        <i />
        <i />
        <i />
        {kind === 2 ? (
          <span className={s.chart}>
            {[28, 48, 36, 66, 51, 80].map((h, i) => (
              <em key={i} style={{ height: h + "%" }} />
            ))}
          </span>
        ) : (
          <>
            <strong />
            <i />
            <i />
            <i />
            <i />
            <i />
          </>
        )}
      </span>
      <span className={s.paperSmall}>
        <b>{kind === 1 ? "A → B" : "RESEARCH"}</b>
        <i />
        <i />
        <strong />
        <i />
        <i />
      </span>
    </span>
  );
}

function Markdown({ value }: { value: string }) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    let live = true;
    markdownToHtml(value).then((v) => {
      if (live) setHtml(v);
    });
    return () => {
      live = false;
    };
  }, [value]);
  return (
    <article
      className={s.markdown}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default function ResearchHarness(p: Props) {
  const [rail, setRail] = useState(true),
    [category, setCategory] = useState(0);
  const [modal, setModal] = useState(""),
    [section, setSection] = useState("人格");
  const [panel, setPanel] = useState(""),
    [menu, setMenu] = useState("");
  const [mode, setMode] = useState<"research" | "chat">("research");
  const [username, setUsername] = useState("bunny"),
    [search, setSearch] = useState("");
  const [projectName, setProjectName] = useState(""),
    [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const { projects, conversations, loading: workspaceLoading, error: workspaceError, createProject } = useWorkspace();
  const [notice, setNotice] = useState(""),
    [sourceView, setSourceView] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null),
    input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    setRail(window.innerWidth >= 900);
    setUsername(localStorage.getItem("asteria.displayName") || "bunny");
    setActiveProjectId(localStorage.getItem("asteria.activeProjectId"));
    try { setExpandedProjects(JSON.parse(localStorage.getItem("asteria.expandedProjects") || "{}")); } catch { /* Ignore an obsolete UI preference. */ }
  }, []);
  useEffect(() => {
    if (modal) {
      dialog.current?.showModal();
    } else {
      dialog.current?.close();
    }
  }, [modal]);
  useEffect(() => {
    setMode(p.answer ? "chat" : "research");
  }, [p.answer]);
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu("");
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [menu]);
  const open = (name: string, tab = "") => {
    setModal(name);
    setSection(tab || (name === "Agent" ? "人格" : "概览"));
    setNotice("");
    setMenu("");
  };
  const pending = (name: string) => open(name);
  const select = (id: string) => {
    if (p.loading || p.chatting) {
      setNotice("请等待当前任务结束后再切换。");
      return;
    }
    p.onSelect(id);
    if (window.innerWidth < 900) setRail(false);
    setModal("");
  };
  const start = () => {
    if (p.loading || p.chatting) {
      setNotice("当前任务仍在运行，请先结束任务。");
      return;
    }
    p.onNew();
    setMode("research");
    setPanel("");
    setNotice("");
  };
  const value = mode === "chat" ? p.chatPrompt : p.prompt;
  const setValue = mode === "chat" ? p.setChatPrompt : p.setPrompt;
  const submit = () => {
    if (
      !value.trim() ||
      p.loading ||
      p.chatting ||
      (mode === "chat" && !p.answer)
    )
      return;
    if (mode === "chat") p.onChat(value.trim());
    else p.onResearch(value.trim());
    setNotice("");
  };
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([p.answer], { type: "text/markdown;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "research-report.md";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const menuButton = (name: string) => {
    setMenu(menu === name ? "" : name);
  };
  const nav = (
    label: string,
    icon: string,
    action: () => void,
    selected = false,
  ) => (
    <button
      type="button"
      className={`${s.navItem} ${selected ? s.selected : ""}`}
      onClick={action}
    >
      <Icon name={icon} />
      <span>{label}</span>
    </button>
  );
  const selectedProject = projects.find((project) => project.id === activeProjectId);
  const expandProject = (id: string, expanded: boolean) => {
    setExpandedProjects((current) => {
      const next = { ...current, [id]: expanded };
      localStorage.setItem("asteria.expandedProjects", JSON.stringify(next));
      return next;
    });
  };
  const newProjectTask = (id: string | null) => {
    if (p.loading || p.chatting) { setNotice("当前任务仍在运行，请先结束任务。"); return; }
    setActiveProjectId(id);
    if (id) { localStorage.setItem("asteria.activeProjectId", id); expandProject(id, true); }
    else localStorage.removeItem("asteria.activeProjectId");
    start();
    input.current?.focus();
  };
  const projectTaskIds = new Set(conversations.filter((item) => item.project_id).map((item) => item.id));
  const reportIds = new Set(p.history.map((item) => item.id));
  const standaloneTasks = [
    ...conversations.filter((item) => !item.project_id && !reportIds.has(item.id)).map((item) => ({
      id: item.id, question: item.title, timestamp: new Date(item.updated_at).getTime(),
    })),
    ...p.history.filter((item) => !projectTaskIds.has(item.id)),
  ].sort((a, b) => b.timestamp - a.timestamp);
  const selectedProjectConversations = selectedProject
    ? conversations.filter((conversation) => conversation.project_id === selectedProject.id)
    : [];
  return (
    <div className={s.shell} data-sidebar={rail ? "open" : "closed"}>
      {rail && (
        <button
          className={s.scrim}
          aria-label="关闭侧边栏"
          onClick={() => setRail(false)}
        />
      )}
      <aside className={s.rail} aria-label="工作台导航">
        <button className={s.brand} onClick={() => open("个人设置")}>
          <img src="/img/asteria-logo.png" alt="Asteria" />
          <span>个人</span>
          <Icon name="down" size={16} />
        </button>
        <nav>
          {nav("新任务", "new", () => newProjectTask(null), !p.active && !activeProjectId)}
          {nav("主机管理", "host", () => open("主机管理"))}
          {nav("Agent", "agent", () => open("Agent"))}
          {nav("团队与订阅", "team", () => open("团队与订阅"))}
          {nav("案例", "file", () => open("案例"))}
          {nav("搜索", "search", () => open("搜索"))}
        </nav>
        <div className={s.railScroll}>
          <details open className={s.group}>
            <summary>
              项目 <Icon name="down" size={14} />
            </summary>
            {nav("新建项目", "folder", () => open("新建项目"))}
            {projects.map((project) => (
              <div key={project.id} className={s.projectTree}>
              <div className={`${s.project} ${project.id === activeProjectId ? s.selected : ""}`}>
                <button
                  className={s.projectMain}
                  aria-expanded={!!expandedProjects[project.id]}
                  aria-controls={`project-${project.id}`}
                  title={project.name}
                  onClick={() => expandProject(project.id, !expandedProjects[project.id])}
                >
                  <span className={s.projectFolder}><Icon name="folder" size={17} /><Icon name={expandedProjects[project.id] ? "down" : "chevron"} size={14} /></span>
                  <span>{project.name}</span>
                </button>
                <button className={s.projectNew} aria-label={`查看项目“${project.name}”`} title="项目详情" onClick={() => {
                  setActiveProjectId(project.id); localStorage.setItem("asteria.activeProjectId", project.id);
                  setProjectName(project.name); open("项目");
                }}><Icon name="more" size={16} /></button>
                <button
                  className={s.projectNew}
                  aria-label={`在项目“${project.name}”中新建对话`}
                  title="新建对话"
                  onClick={() => newProjectTask(project.id)}
                >
                  <Icon name="compose" size={16} />
                </button>
              </div>
              {expandedProjects[project.id] && <div id={`project-${project.id}`} className={s.projectChildren}>
                {conversations.filter((item) => item.project_id === project.id).map((conversation) => (
                  <button key={conversation.id} className={`${s.projectTask} ${p.selectedId === conversation.id ? s.selected : ""}`}
                    title={conversation.title} onClick={() => {
                      if (p.loading || p.chatting) { select(conversation.id); return; }
                      setActiveProjectId(project.id); localStorage.setItem("asteria.activeProjectId", project.id);
                      select(conversation.id);
                    }}>
                    <span className={s.taskDot} data-status={conversation.status} />
                    <span>{conversation.title}</span>
                  </button>
                ))}
              </div>}
              </div>
            ))}
          </details>
          <details open className={s.group}>
            <summary>
              任务 <Icon name="down" size={14} />
            </summary>
            {standaloneTasks.map((item) => (
              <button
                key={item.id}
                className={`${s.task} ${p.selectedId === item.id ? s.selected : ""}`}
                onClick={() => {
                  if (!p.loading && !p.chatting) { setActiveProjectId(null); localStorage.removeItem("asteria.activeProjectId"); }
                  select(item.id);
                }}
              >
                <span className={s.taskDot} />
                <span>
                  <b>{item.question}</b>
                  <small>
                    {new Date(item.timestamp).toLocaleDateString("zh-CN")}
                    <span>
                      <Icon name="cloud" size={13} />
                      调研
                    </span>
                  </small>
                </span>
              </button>
            ))}
          </details>
          <details className={s.group}>
            <summary>
              更多工具 <Icon name="down" size={14} />
            </summary>
            {[
              ["/knowledge", "知识库"],
              ["/rag-workspace", "离线 RAG"],
              ["/doc-agent", "文档编辑"],
              ["/evaluation", "评测中心"],
            ].map(([href, label]) => (
              <Link className={s.navItem} href={href} key={href}>
                <Icon name="file" />
                {label}
              </Link>
            ))}
          </details>
        </div>
        <button className={s.user} onClick={() => open("个人设置")}>
          <span className={s.avatar}>{username.slice(0, 1).toUpperCase()}</span>
          <span>{username}</span>
          <Icon name="down" size={16} />
        </button>
      </aside>
      <main className={s.workspace}>
        <header className={s.topbar}>
          <button
            className={s.iconButton}
            aria-label={rail ? "收起侧边栏" : "展开侧边栏"}
            aria-expanded={rail}
            onClick={() => setRail(!rail)}
          >
            <Icon name="panel" />
          </button>
          {p.active && (
            <span className={s.taskPill}>
              <span className={p.loading ? s.running : s.taskDot} />
              {p.question || "新任务"}
            </span>
          )}
          <span className={s.spacer} />
          {p.active && (
            <>
              <button
                className={s.iconButton}
                aria-label="任务操作"
                onClick={() => open("任务操作")}
              >
                <Icon name="dots" />
              </button>
              <button
                className={s.iconButton}
                aria-label="切换任务详情"
                onClick={() => setPanel(panel ? "" : "总览")}
              >
                <Icon name="panel" />
              </button>
            </>
          )}
        </header>
        <div className={s.body}>
          <div className={s.conversation}>
            {!p.active ? (
              <div className={s.welcome}>
                <h1>你好，{username}</h1>
                <div className={s.categories} aria-label="任务示例分类">
                  {["科研学术", "专业服务", "工程开发", "商业分析"].map(
                    (name, i) => (
                      <button
                        aria-pressed={category === i}
                        className={category === i ? s.current : ""}
                        key={name}
                        onClick={() => setCategory(i)}
                      >
                        {name}
                      </button>
                    ),
                  )}
                </div>
                <div className={s.cards}>
                  {scenarios[category].map(([title, desc, prompt], i) => (
                    <button
                      className={s.card}
                      key={title}
                      onClick={() => {
                        setMode("research");
                        p.setPrompt(prompt);
                        input.current?.focus();
                      }}
                    >
                      <span>
                        <strong>{title}</strong>
                        <p>{desc}</p>
                      </span>
                      <Thumbnail kind={i} />
                    </button>
                  ))}
                </div>
                <button className={s.enter} onClick={p.onEnter}>
                  进入工作台 <Icon name="chevron" size={14} />
                </button>
              </div>
            ) : (
              <div className={s.transcript}>
                {p.question && <div className={s.question}>{p.question}</div>}
                {p.question && (
                  <div className={s.agentLabel}>
                    <Icon name="agent" />
                    Asteria Research{" "}
                    <span>
                      {p.loading
                        ? "运行中"
                        : p.stopped
                          ? "已停止"
                          : p.answer
                            ? "已生成报告"
                            : ""}
                    </span>
                  </div>
                )}
                {p.active && !p.question && (
                  <div className={s.emptyWorkspace}>
                    <Icon name="agent" size={28} />
                  </div>
                )}
                <div className={s.results}>{p.children}</div>
                {p.answer && (
                  <button
                    className={s.artifact}
                    onClick={() => setPanel("报告")}
                  >
                    <Icon name="file" />
                    <span>
                      <b>研究报告</b>
                      <small>Markdown · 点击预览</small>
                    </span>
                    <Icon name="chevron" />
                  </button>
                )}
              </div>
            )}
            <div className={s.composerWrap}>
              {notice && (
                <div className={s.notice} role="status">
                  {notice}
                  <button aria-label="关闭提示" onClick={() => setNotice("")}>
                    <Icon name="close" size={14} />
                  </button>
                </div>
              )}
              <div className={s.composer}>
                <div className={s.hostRow}>
                  <button onClick={() => open("选择工作目录")}>
                    <Icon name="cloud" size={17} />
                    执行环境 · 默认配置
                  </button>
                  {p.active && (
                    <select
                      aria-label="输入模式"
                      value={mode}
                      onChange={(e) =>
                        setMode(e.target.value as "research" | "chat")
                      }
                    >
                      <option value="research">新调研</option>
                      <option value="chat">报告问答</option>
                    </select>
                  )}
                </div>
                <div className={s.inputBox}>
                  <textarea
                    ref={input}
                    aria-label={mode === "chat" ? "报告问答内容" : "任务内容"}
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder={
                      mode === "chat"
                        ? "针对当前报告提问…"
                        : "描述你的任务，或从上方选择一个研究起点"
                    }
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        submit();
                      }
                    }}
                  />
                  <div className={s.toolbar}>
                    <div
                      className={s.menuAnchor}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        className={s.iconButton}
                        aria-label="添加内容"
                        aria-expanded={menu === "add"}
                        onClick={() => menuButton("add")}
                      >
                        <Icon name="plus" />
                      </button>
                      {menu === "add" && (
                        <div className={s.popup}>
                          {nav("上传文件", "file", () => pending("任务附件"))}
                          {nav("引用知识库", "folder", () => open("知识库"))}
                          {nav("选择技能", "skill", () =>
                            open("Agent", "技能"),
                          )}
                        </div>
                      )}
                    </div>
                    <button
                      className={s.modelButton}
                      onClick={() => open("调研设置")}
                    >
                      <Icon name="agent" size={18} />
                      {p.settings.search_strategy === "academic"
                        ? "学术检索"
                        : p.settings.search_strategy === "hybrid"
                          ? "混合检索"
                          : "通用检索"}
                      <span>·</span>默认模型
                      <Icon name="down" size={13} />
                    </button>
                    <span className={s.spacer} />
                    <button className={s.modelButton} onClick={() => open("Agent", "技能")} aria-label="查看和指定技能">
                      <Icon name="skill" size={16} />
                      {p.settings.skill_ids?.length ? `${p.settings.skill_ids.length} 项技能` : "技能"}
                      {p.settings.format_profile && <small> · {p.settings.format_profile === "brief" ? "简报" : "学术"}</small>}
                    </button>
                    <button
                      className={s.iconButton}
                      aria-label="语音输入"
                      onClick={() => pending("语音输入")}
                    >
                      <Icon name="mic" size={19} />
                    </button>
                    {p.loading ? (
                      <button
                        className={s.send}
                        onClick={p.onStop}
                        aria-label="停止当前任务"
                      >
                        <span className={s.stop} />
                      </button>
                    ) : (
                      <button
                        className={s.send}
                        disabled={
                          !value.trim() ||
                          p.chatting ||
                          (mode === "chat" && !p.answer)
                        }
                        onClick={submit}
                        aria-label="发送"
                      >
                        <Icon name="arrow" size={21} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
              <small className={s.disclaimer}>
                {mode === "chat" && !p.answer
                  ? "报告生成后可在此继续问答；知识库问答请进入离线 RAG。"
                  : "Asteria 也可能会犯错，请仔细甄别"}
              </small>
            </div>
          </div>
          {panel && (
            <aside
              className={`${s.inspector} ${panel === "报告" ? s.wideInspector : ""}`}
              aria-label="任务详情"
            >
              <div className={s.inspectorTabs}>
                {[
                  ["总览", "grid"],
                  ["文件", "folder"],
                  ["轨迹", "file"],
                  ["终端", "terminal"],
                  ["主机", "cloud"],
                ].map(([label, icon]) => (
                  <button
                    key={label}
                    className={panel === label ? s.current : ""}
                    title={label}
                    aria-label={label}
                    onClick={() => setPanel(label)}
                  >
                    <Icon name={icon} size={18} />
                    {panel === label && label}
                  </button>
                ))}
                <button aria-label="关闭详情" onClick={() => setPanel("")}>
                  <Icon name="close" size={17} />
                </button>
              </div>
              <div className={s.inspectorContent}>
                {panel === "总览" ? (
                  <>
                    <h3>任务状态</h3>
                    <p>
                      {p.loading
                        ? "正在运行"
                        : p.stopped
                          ? "已停止"
                          : p.answer
                            ? "报告已生成"
                            : "尚未开始"}
                    </p>
                    <h3>执行记录</h3>
                    <p>{p.logCount} 条已接收记录</p>
                    <h3>子智能体</h3>
                    <p>当前接口尚未提供独立子任务状态。</p>
                    <h3>产物</h3>
                    {p.answer ? (
                      <button
                        className={s.outline}
                        onClick={() => setPanel("报告")}
                      >
                        <Icon name="file" />
                        研究报告
                      </button>
                    ) : (
                      <p>尚无产物</p>
                    )}
                  </>
                ) : panel === "报告" ? (
                  <>
                    <div className={s.reportTools}>
                      <button
                        className={s.outline}
                        onClick={() => setSourceView(!sourceView)}
                      >
                        {sourceView ? "预览" : "源码"}
                      </button>
                      <button className={s.outline} onClick={download}>
                        <Icon name="download" size={16} />
                        下载
                      </button>
                      <button
                        className={s.outline}
                        onClick={() => open("LaTeX 报告")}
                      >
                        LaTeX
                      </button>
                    </div>
                    {sourceView ? (
                      <pre className={s.source}>{p.answer}</pre>
                    ) : (
                      <Markdown value={p.answer} />
                    )}
                  </>
                ) : panel === "文件" ? (
                  <>
                    {p.answer ? (
                      <button
                        className={s.outline}
                        onClick={() => setPanel("报告")}
                      >
                        <Icon name="file" />
                        research-report.md
                      </button>
                    ) : (
                      <p>任务还没有生成文件。</p>
                    )}
                  </>
                ) : panel === "轨迹" ? (
                  <>
                    <h3>执行轨迹</h3>
                    <p>
                      已接收 {p.logCount} 条记录，完整内容见对话中的执行过程。
                    </p>
                    <button
                      className={s.outline}
                      onClick={() => pending("轨迹导出")}
                    >
                      导出轨迹
                    </button>
                  </>
                ) : (
                  <>
                    <h3>{panel}</h3>
                    <p>此能力待接入，不会执行远程命令。</p>
                    <button
                      className={s.outline}
                      onClick={() => open("主机管理")}
                    >
                      打开主机管理
                    </button>
                  </>
                )}
              </div>
            </aside>
          )}
        </div>
      </main>
      <dialog
        ref={dialog}
        aria-label={modal || "工作台设置"}
        className={s.dialog}
        onCancel={() => setModal("")}
        onClick={(e) => {
          if (e.target === dialog.current) setModal("");
        }}
      >
        <div className={s.dialogInner}>
          <button
            className={s.dialogClose}
            aria-label="关闭弹窗"
            onClick={() => setModal("")}
          >
            <Icon name="close" />
          </button>
          {(modal === "Agent" || modal === "主机管理") && (
            <aside className={s.dialogRail}>
              <h2>{modal}</h2>
              {(modal === "Agent"
                ? ["人格", "记忆", "技能", "SSH 服务器"]
                : ["概览", "存储", "环境", "桌面", "终端", "设置"]
              ).map((tab) => (
                <button
                  key={tab}
                  className={section === tab ? s.selected : ""}
                  onClick={() => setSection(tab)}
                >
                  <Icon
                    name={
                      tab === "记忆"
                        ? "memory"
                        : tab === "技能"
                          ? "skill"
                          : tab === "SSH 服务器"
                            ? "cloud"
                            : "agent"
                    }
                    size={18}
                  />
                  {tab}
                </button>
              ))}
            </aside>
          )}
          <section className={s.dialogContent}>
            <h2>
              {modal === "Agent" || modal === "主机管理" ? section : modal}
            </h2>
            {modal === "LaTeX 报告" ? (
              <LatexPreview paths={p.artifactPaths || {}} />
            ) : modal === "个人设置" ? (
              <>
                <p>显示名称仅保存在此浏览器，不改变登录账号。</p>
                <label>
                  用户名
                  <input
                    value={username}
                    maxLength={32}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </label>
                <button
                  className={s.primary}
                  onClick={() => {
                    const name = username.trim() || "bunny";
                    setUsername(name);
                    localStorage.setItem("asteria.displayName", name);
                    setModal("");
                  }}
                >
                  保存
                </button>
              </>
            ) : modal === "搜索" ? (
              <>
                <input
                  autoFocus
                  aria-label="搜索任务"
                  placeholder="搜索任务…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <div className={s.searchResults}>
                  {p.history
                    .filter((x) =>
                      x.question.toLowerCase().includes(search.toLowerCase()),
                    )
                    .map((x) => (
                      <button key={x.id} onClick={() => select(x.id)}>
                        <Icon name="file" />
                        {x.question}
                      </button>
                    ))}
                </div>
              </>
            ) : modal === "调研设置" ? (
              <>
                <label>
                  文献综述 · 在线 RAG
                  <select
                    value={p.settings.online_rag === false ? "off" : "on"}
                    onChange={(e) => p.setSettings((v) => ({ ...v, online_rag: e.target.value === "on" }))}
                  >
                    <option value="on">开启：全文混合检索</option>
                    <option value="off">关闭：Agent 自主阅读原文页段</option>
                  </select>
                </label>
                <p>对下一次文献综述生效；两种模式均可联网发现论文与追踪引用。运行中不自动切换。</p>
                <p>以下仅用于通用调研引擎，不控制自主综述的工具选择。</p>
                <label>
                  通用引擎检索策略
                  <select
                    value={p.settings.search_strategy}
                    onChange={(e) =>
                      p.setSettings((v) => ({
                        ...v,
                        search_strategy: e.target
                          .value as ChatBoxSettings["search_strategy"],
                      }))
                    }
                  >
                    <option value="general">通用检索</option>
                    <option value="academic">学术检索</option>
                    <option value="hybrid">混合检索</option>
                  </select>
                </label>
                <label>
                  通用引擎报告类型
                  <select
                    value={p.settings.report_type}
                    onChange={(e) =>
                      p.setSettings((v) => ({
                        ...v,
                        report_type: e.target.value,
                      }))
                    }
                  >
                    <option value="research_report">研究报告</option>
                    <option value="detailed_report">深度报告</option>
                    <option value="multi_agents">多 Agent 报告</option>
                  </select>
                </label>
                <button className={s.primary} onClick={() => setModal("")}>
                  完成
                </button>
              </>
            ) : modal === "新建项目" ? (
              <>
                <p>创建可持久化项目。后续研究任务和工作目录可以归属到这里。</p>
                {workspaceError && <div className={s.pendingBadge}>项目服务不可用：{workspaceError}</div>}
                {workspaceLoading && <div className={s.pendingBadge}>正在加载项目…</div>}
                <label>
                  项目名称
                  <input
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    maxLength={80}
                  />
                </label>
                <button
                  className={s.primary}
                  disabled={!projectName.trim()}
                  onClick={async () => {
                    try {
                      const project = await createProject(projectName.trim());
                      setActiveProjectId(project.id);
                      localStorage.setItem("asteria.activeProjectId", project.id);
                      setProjectName("");
                      setModal("");
                    } catch (cause) {
                      setNotice(cause instanceof Error ? cause.message : "项目创建失败");
                    }
                  }}
                >
                  创建项目
                </button>
              </>
            ) : modal === "项目" ? (
              <>
                <h3>{projectName}</h3>
                <div className={s.searchResults}>
                  <strong>项目任务 · {selectedProjectConversations.length}</strong>
                  {selectedProjectConversations.length === 0 ? (
                    <p>还没有子任务，从上方开始创建。</p>
                  ) : selectedProjectConversations.map((conversation) => {
                    const completed = p.history.some((item) => item.id === conversation.id);
                    return completed ? (
                      <button key={conversation.id} onClick={() => select(conversation.id)}>
                        <Icon name="file" />
                        {conversation.title}
                      </button>
                    ) : (
                      <div key={conversation.id} className={s.pendingBadge}>
                        {conversation.title} · {conversation.status === "active" ? "进行中" : conversation.status}
                      </div>
                    );
                  })}
                </div>
              </>
            ) : modal === "案例" ? (
              <div className={s.exampleList}>
                {scenarios.flat().map(([title, , prompt]) => (
                  <button
                    key={title}
                    onClick={() => {
                      p.setPrompt(prompt);
                      setMode("research");
                      setModal("");
                      input.current?.focus();
                    }}
                  >
                    <Icon name="file" />
                    {title}
                    <Icon name="chevron" size={16} />
                  </button>
                ))}
              </div>
            ) : modal === "知识库" ? (
              <>
                <p>沿用现有知识库与离线 RAG 页面。</p>
                <Link className={s.outline} href="/knowledge">
                  管理知识库
                </Link>
                <Link className={s.outline} href="/rag-workspace">
                  进入检索问答
                </Link>
              </>
            ) : modal === "Agent" ? (
              <>
                <p>
                  {section === "人格"
                    ? "定义研究偏好、证据要求和输出习惯。"
                    : section === "记忆"
                      ? "管理可复用的研究偏好与项目经验。"
                      : section === "技能"
                        ? "按需加载研究方法、工具约束与输出规范。"
                        : "管理授权服务器、允许目录与实验执行权限。"}
                </p>
                {section !== "技能" && <div className={s.pendingBadge}>待接入运行时</div>}
                {section === "技能" ? (
                  <SkillBrowser settings={p.settings} onChange={next => p.setSettings(next)}
                    locked={p.loading || p.chatting} supported={p.skillsSupported !== false && mode === "research"} />
                ) : (
                  <div className={s.placeholder}>
                    <Icon
                      name={section === "记忆" ? "memory" : "agent"}
                      size={32}
                    />
                    <p>配置入口已预留，尚未启用{section}管理。</p>
                    <button className={s.outline} disabled>
                      添加
                      {section === "SSH 服务器"
                        ? "服务器"
                        : section === "记忆"
                          ? "记忆"
                          : "配置"}
                    </button>
                  </div>
                )}
              </>
            ) : modal === "主机管理" ? (
              <>
                <div className={s.pendingBadge}>待接入主机服务</div>
                <div className={s.placeholder}>
                  <Icon name="host" size={36} />
                  <p>{section}面板尚未接入。现有调研仍使用后端原有执行环境。</p>
                  <button className={s.outline} disabled>
                    连接主机
                  </button>
                </div>
              </>
            ) : modal === "选择工作目录" ? (
              <>
                <div className={s.directoryBar}>
                  <Icon name="folder" />
                  <span>默认执行环境</span>
                  <Icon name="refresh" />
                </div>
                <div className={s.placeholder}>
                  <Icon name="folder" size={36} />
                  <p>
                    主机目录浏览与授权边界待接入，当前不会更改后端工作目录。
                  </p>
                </div>
                <button className={s.primary} onClick={() => setModal("")}>
                  保留默认配置
                </button>
              </>
            ) : (
              <>
                <div className={s.pendingBadge}>待接入</div>
                <p>{modal}的界面入口已预留，尚未连接后端能力。</p>
                {modal === "任务操作" && (
                  <button
                    className={s.outline}
                    onClick={() => {
                      setPanel("总览");
                      setModal("");
                    }}
                  >
                    查看任务详情
                  </button>
                )}
              </>
            )}
          </section>
        </div>
      </dialog>
    </div>
  );
}
