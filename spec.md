# Asteria Agent 开发规格

> 本文档用于记录项目当前状态、设计决策和后续开发计划。实现过程中如果实际约束发生变化，先更新这里，再调整代码。

## 1. 项目目标

Asteria Agent 是一个本地优先的科研协作系统，当前重点是学术调研和综述报告撰写。系统需要从“能够按固定步骤生成报告”逐步发展为“能够理解任务、选择能力、调用工具、处理异常并交付可复现产物”的 Agent。

第一阶段不追求覆盖所有科研场景，优先把下面这条主线做扎实：

```text
科研问题 → 任务理解 → 研究计划 → 资料检索与阅读 → 证据整理
        → 报告撰写 → 引用核验 → 文件交付 → 任务复盘与继续执行
```

在不破坏学术调研主线的前提下，后续扩展到技术调研、数据分析、实验复现和其他需要长任务执行的场景。

## 2. 设计原则

### 2.1 稳定主线和自主决策并存

报告生成、引用归档和文件输出需要稳定、可调试、可回放；任务拆解、工具选择、补充检索、异常恢复和结果核验可以由 Agent 自主决策。不要为了体现 Agent 而把所有步骤都改成不可控的自由循环。

### 2.2 Skill 定义方法，Sub-Agent 执行角色，Tool 执行动作

三者职责保持清晰：

```text
Task Type → Skill → Sub-Agent → Tool / MCP
```

- `Task Type`：用户要完成什么类型的工作。
- `Skill`：这类工作采用什么方法、需要什么输入、产出什么结果、如何验收。
- `Sub-Agent`：在限定职责内做判断和执行。
- `Tool / MCP`：提供可验证的具体动作。

Sub-Agent 不需要和 Tool 一一对应。工具少且逻辑简单时可直接使用进程内 Tool；需要独立环境、跨项目复用或权限隔离时，使用 MCP。

### 2.3 所有长任务都必须可观察、可恢复

每次任务都应有独立的 Run ID，并保留：

- 当前阶段和已完成步骤
- Agent、LLM、Tool、Retriever 的调用轨迹
- 中间文本、结构化数据和文件产物
- 错误、重试和重规划记录
- 模型、Prompt、工具、数据和运行环境版本

浏览器关闭、单个工具失败或服务重启不应导致整个任务状态丢失。

### 2.4 Tool 执行必须受边界控制

任何文件读写、Shell、远程服务器和实验操作都必须经过用户配置的工作区、命令白名单、超时和权限策略。Agent 只能提交结构化任务，不能直接获得任意命令执行能力。

### 2.5 每项功能先验证，再提交

后续开发按以下节奏进行：

```text
小功能 → 单元测试/类型检查 → 本地启动 → 固定任务验证 → 检查 Trace/产物 → commit → push
```

每个 commit 尽量只解决一个清晰问题，避免在一个提交中同时改变编排、存储、前端和运行环境。

## 3. 当前项目状态（2026-09-10）

### 3.1 已有能力

- Python 调研引擎位于 `asteria_researcher/`，负责查询拆解、检索、抓取、上下文处理、引用和报告生成。
- 基于 LangGraph 的多 Agent 编排位于 `multi_agents/`。
- 当前多 Agent 角色包括 Researcher、Editor、Writer、Reviewer、Reviser、Fact Checker、Visualizer 和 Publisher。
- 主多 Agent 链路已经包含大纲规划、人工审核、章节并行研究、写作、事实检查、可视化和发布。
- `ResearchAgent` 已支持按 perspective 生成补充研究视角并行调研。
- MCP 已接入客户端管理、工具发现、工具选择、工具调用和结果归一化。
- MCP 路径支持关闭、快速复用和逐子查询深入执行等策略。
- 项目已有 WebSocket 流式日志、FastAPI 服务和 Next.js 前端。
- 已有初步评测模块：任务、Trace、Scorer、BadCase、SeedCase、GeneratedCase、Runner 和本地存储。
- 已有独立的评测文档和示例 Trace，可作为后续 Agent 评测的基础。
- 报告当前主要输出 Markdown、Word 和 PDF；尚未形成完整的 LaTeX 工作区和模板体系。

### 3.2 当前编排的真实边界

当前系统是“多 Agent Workflow + 局部 Agent 化能力”，还不是完全开放式的自主 Agent：

- `ChiefEditorAgent` 负责固定主图，节点顺序基本确定。
- `EditorAgent` 负责生成章节，`ResearchAgent` 负责章节研究，章节之间可以并行。
- `Reviewer`、`Reviser` 和 `FactChecker` 存在条件回路，但主要围绕预先定义的报告流程工作。
- MCP 工具选择和 perspective research 已有动态决策，但还没有统一的任务级重规划和停止策略。
- 现有角色没有全部形成“独立状态、专属工具集合、输入输出契约和失败边界”。
- 输出目录能够保存产物，但任务状态、运行状态、轨迹和文件尚未统一为一个可恢复的长任务模型。

因此，下一步不是简单增加更多 Agent，而是补齐任务状态、能力注册、工具边界、重规划和产物管理。

### 3.3 Phase 1 实现进度

- [x] 增加 `TaskSpec`、`IntentResult`、`SkillManifest`、`AgentProfile` 和 `ToolSpec` 契约。
- [x] 增加内存版 `CapabilityRegistry`，注册当前科研路径和未来实验、离线 RAG、数据分析扩展点。
- [x] 增加不依赖外部模型的 `IntentRouter`，用户不需要手动选择任务类型。
- [x] 为现有 Editor、Researcher、Writer 和 Fact Checker 建立初始 Agent Profile。
- [x] 为意图路由、Skill 解析、任务构造和重复注册增加单元测试。
- [ ] 将 Intent Router 接入 API 请求和现有主编排入口。
- [ ] 用结构化 LLM 分类器替换或增强规则路由，并保留确定性回退。

### 3.4 本轮前端与启动状态

- [x] 首页与研究任务页拆成两个明确状态：初始页保留 Bunny Research 的直接输入和历史研究入口；提交任务后进入白色液态玻璃工作台。
- [x] 首页空输入的提交按钮可以直接进入研究工作台，但不会创建空任务或打开检索 WebSocket；非空输入仍然直接启动研究。
- [x] 研究工作台保留左侧任务导航、中间过程/报告区和右侧协作面板，顶部只保留必要的任务状态与操作，不再展示冗余的说明性 Hero 文案。
- [x] 侧栏支持桌面端 Codex 式收起/恢复，收起后保留 56px 图标轨道，主内容区和顶部栏同步展开；点击主内容区不会触发移动端的点击外部收起逻辑。
- [x] 研究 WebSocket 在连接超时、异常关闭或服务端错误事件到达时结束 loading 状态，避免把后端异常伪装成无限检索。
- [x] 设置弹窗改为客户端加载，避免 Portal 与动画依赖在 Next.js 开发态服务端渲染时阻塞首屏。
- [x] 本地启动支持显式免登录模式，前端 AuthGuard、后端 HTTP API 和 WebSocket 使用同一组本地开发开关；生产/共享环境默认不绕过鉴权。
- [x] 确认 `Hero`、工作台布局、`/login` 和根页面可独立完成首次编译并返回 200。

本轮检索故障记录：真实任务能够完成网页抓取和报告生成，但日志暴露出两个独立问题。其一，当前网络路径下部分外部检索站点和模型端点出现连接重置、TLS 握手中断或超时，原实现的非流式 LLM 请求最多重试 10 次，导致用户侧长时间停留在 loading。其二，`ollama:bge-m3` 在本机 Ollama 0.23.2 上调用 `/api/embed` 时触发 Metal `failed to create command queue`，本地 embedding runner 直接退出；该异常在每个子查询中被记录后继续，造成上下文压缩阶段失去 dense 信号。当前已将 LLM 重试预算收敛为可配置的 3 次、统一服务端错误事件，并补齐前端错误终止逻辑；这只解决任务状态不透明问题，不能替代对网络代理和 Ollama 运行时的环境修复。官方后续版本已包含 macOS 26 相关 Metal 修复，项目启动脚本会要求不低于 0.23.3 并执行真实 embedding 自检。后续固定任务验证必须同时记录外部端点连通性、embedding 健康检查、检索结果数量和报告产物，不能只以页面停止转圈作为成功标准。

本轮排查记录：修改组件时曾先删除再重建多个文件，Next.js 热更新短暂出现 `Cannot find module`；随后旧开发进程还出现根页面请求长期不返回。干净进程逐页验证后，确认阻塞点来自设置弹窗在服务端渲染阶段的 Portal/动画依赖，而不是研究编排或后端服务。验证期间并行启动多个 Next 实例又触发了 macOS `EMFILE`，使 `build`、`lint` 和 `tsc` 出现长时间无输出；这类命令不能与开发服务器或彼此并行运行。今后前端改动遵循“先新增/替换后删除临时文件、单端口干净启动、逐页 HTTP 检查、再进行浏览器交互验证”的顺序；发现端口已监听但页面不返回时，以实际页面响应和日志为准，不直接复用旧热更新进程。

本轮登录循环排查记录：旧页面曾因失效 JWT 或前后端鉴权配置不一致收到 401/4401，原前端会在 HTTP 与 WebSocket 两条路径清理本地 token 并强制跳转 `/login`；同时本地免登录开关只存在于某次启动命令的进程环境中，手动启动 Next 或复用旧标签页时容易再次落入登录页。现已统一由 `isLocalAuthBypassEnabled()` 判断本地模式，固定补入前端 `.env.local`/`.env.example` 与启动文档；明确开启本地模式时，登录页会回到首页，401/4401 会保留真实错误并提示检查后端开关和 API 地址，不再形成登录循环。非本地模式仍保持失效 token 清理和登录跳转。验证方式为：干净重启 Next、直接访问 `/login`、刷新根页面，并请求 `/api/reports`；三者均通过后再测试 WebSocket，不能只看地址栏是否变化。

## 4. 目标架构

```text
Frontend
  ├── New Task / Task List / Project
  ├── Live Steps / Trace / Sub-Agents
  ├── Artifacts / Report / Logs
  └── Hosts / Skills / Memory Settings
          ↓
Research API
  ├── Task Manager
  ├── Run Manager
  └── Event Stream
          ↓
Agent Orchestrator
  ├── Task Planner
  ├── Skill Router
  ├── Sub-Agent Runtime
  ├── Replanner / Recovery
  └── Completion Checker
          ↓
Capability Layer
  ├── Literature Research Skill
  ├── Systematic Review Skill
  ├── Technical Survey Skill
  ├── Experiment Skill
  ├── Data Analysis Skill
  └── LaTeX Report Skill
          ↓
Tool Layer
  ├── Search / Browser / Paper Reader
  ├── Knowledge Base / MCP
  ├── Workspace / Artifact
  ├── Experiment Worker
  └── Citation / Report Validator
          ↓
Trace Store / Artifact Store / Memory / Evaluation
```

## 5. Agent、Skill 和 Tool 设计

### 5.1 首批能力类型

先支持以下能力，未来可以扩展其他任务类型：

| Task Type | 目标 | 主要能力 |
| --- | --- | --- |
| `literature_review` | 文献调研与综述 | 检索、阅读、证据整理、报告撰写 |
| `technical_survey` | 技术路线与方法比较 | 论文/文档检索、方法抽取、对比分析 |
| `systematic_review` | 规范化综述 | 检索协议、筛选、去重、证据表、引用检查 |
| `experiment` | 可复现实验 | 环境选择、命令执行、指标读取、产物归档 |
| `data_analysis` | 数据分析与图表 | 数据读取、代码运行、统计分析、图表生成 |

股票或公司调研可以作为后续新增的 `company_research` 类型，不应提前把当前科研主线硬编码成唯一任务形态。

### 5.2 首批 Sub-Agent

- `PlannerAgent`：理解任务，生成目标、阶段、约束和完成条件。
- `ResearchAgent`：执行检索、阅读和证据整理，拥有受控的研究工具。
- `EvidenceAgent`：建立结论与证据、来源和引用之间的关系，发现支撑不足和来源冲突。
- `AnalystAgent`：处理数据、运行分析代码和解释实验结果。
- `WriterAgent`：根据结构化研究结果撰写报告，不负责自由决定全部工具。
- `ReviewerAgent`：按 Skill 的验收标准检查报告和产物，必要时触发重规划。
- `ExperimentAgent`：生成和提交结构化实验任务，不能绕过工作区和命令权限。
- `ArtifactAgent`：管理 Markdown、LaTeX、图片、表格、日志和指标文件。

现有角色优先通过适配和职责收敛复用，不先重写。`ChiefEditorAgent` 后续逐步演化为 Orchestrator，`EditorAgent` 的规划能力可以迁移到 `PlannerAgent`，`ResearchAgent`、`WriterAgent` 和 `FactCheckerAgent` 保留为初始实现。

## 6. 工具与 MCP 规划

### 6.1 研究工具

第一阶段保留已有工具，并统一工具契约：

- 学术搜索、网页搜索和来源读取
- 文献内容抽取与摘要
- 知识库检索
- 引用和来源记录
- 工作区笔记读写

工具统一声明名称、描述、JSON Schema、超时、重试策略、权限等级和返回结构。MCP 结果先归一化成项目内部的 `EvidenceItem`，避免下游 Agent 依赖某个 MCP 服务的原始返回格式。

### 6.2 MCP 使用边界

- 进程内的纯函数和轻量校验逻辑，优先使用 LangChain Tool。
- 知识库、远程执行、实验环境和需要跨 Agent 复用的能力，优先使用 MCP。
- 不把所有内部函数都暴露成 MCP Tool。
- Orchestrator 只看到少量高层能力，底层工具由对应 Skill 或 Sub-Agent 管理。

## 7. 受控实验执行

实验功能是独立能力，不与普通文献检索混在同一条无边界工具链中。

### 7.1 用户配置的运行环境

每个 Host Profile 至少包含：

```yaml
name: local-gpu
host: local
workspace: /path/to/project
python_env: dora
allowed_commands:
  - python
  - pytest
  - uv
network_policy: disabled
timeout_seconds: 3600
approval_required: true
```

远程主机额外记录 SSH 别名、远程工作区、GPU 信息和文件同步策略。凭据不进入任务 Prompt、Trace 或 Git。

### 7.2 Experiment Recipe

可复用实验不由 Agent 临时拼装成不可复现的命令，而是使用版本化 Recipe：

```yaml
name: reproduce_baseline
inputs:
  - dataset
  - checkpoint
  - epochs
steps:
  - command: python train.py --config configs/baseline.yaml
  - command: python evaluate.py --checkpoint outputs/best.pt
outputs:
  - outputs/metrics.json
  - outputs/figures/
validation:
  - outputs/metrics.json exists
```

执行器负责校验工作区、命令、参数、超时和输出；Agent 负责选择 Recipe、填写参数、解释结果和决定是否需要下一轮实验。

### 7.3 实验产物

每轮实验至少归档：

- Recipe 版本和实际命令
- 代码、数据和环境版本
- 标准输出、错误日志和退出状态
- 指标 JSON、图表和检查点路径
- Trace、Artifact Manifest 和运行时间

## 8. 报告与 LaTeX

LaTeX 采用“结构化内容 + Skill + 模板 + 确定性渲染”的方案，不让 LLM 直接自由生成整份排版源码。

### 8.1 报告中间结构

Writer 输出结构化报告对象：

```json
{
  "title": "...",
  "abstract": "...",
  "sections": [],
  "tables": [],
  "figures": [],
  "citations": [],
  "appendix": []
}
```

### 8.2 模板目录

```text
templates/
├── survey/
│   ├── template.tex
│   ├── preamble.tex
│   ├── template.yaml
│   └── bibliography.bib
├── technical_report/
└── conference_paper/
```

模板负责页面、字体、章节、图片、表格、公式、参考文献和附录样式；Skill 负责选择模板、填充内容和触发编译。

### 8.3 编译与校验

LaTeX Skill 需要支持：

- `latexmk` / XeLaTeX 编译
- 引用键存在性检查
- 图片路径和格式检查
- 表格、公式和交叉引用检查
- 编译日志归档
- 编译失败后的定向修复
- `.tex`、`.bib`、图片、PDF 和日志一并交付

## 9. 前端目标

前端首先服务于任务执行和过程理解，不先追求复杂的社交、订阅或全平台能力。

### 9.1 信息架构

- 新任务：直接描述目标，由意图路由识别任务类型，再补充 Skill、模型、工作区和输出格式。
- 项目：一个目录承载相关任务、资料和产物。
- 任务：展示状态、步骤、运行记录和历史版本。
- 主机管理：维护本地或远程 Host Profile。
- Agent：维护身份、能力和工具权限。
- Skill：查看方法说明、输入输出契约和可用工具。
- 记忆：管理项目级研究偏好、术语和长期事实。

### 9.2 任务工作区

任务页面至少分成三块：

```text
左侧：项目与任务导航
中间：对话、步骤流和实时执行过程
右侧：概览、子 Agent、工具、文件、日志和用量
```

重点交互包括：

- 查看当前步骤和下一步计划
- 展开某次 Tool Call 的参数、结果和错误
- 暂停、继续、重试和从某一步重跑
- 查看生成的报告、代码、图片、数据和 PDF
- 对局部产物提出修改要求

视觉上采用浅色、低干扰、信息密度适中的液态玻璃工作台风格；初始页强调直接输入和历史任务，执行页使用持久侧栏、步骤流和右侧协作面板承载可观测信息。具体颜色和组件后续继续沉淀为前端 tokens。

## 10. 评测方向（第二阶段）

评测系统暂不阻塞第一阶段的 Agent 功能，但执行层从现在开始必须保留足够的 Trace。

后续评测由两部分组成：

1. 科研任务和报告质量：参考 DeepResearch Bench，评估任务完成、证据覆盖、引用支撑和报告质量。
2. Agent 行为和工具轨迹：参考 TRAJECT-Bench，评估工具选择、参数、调用顺序、异常恢复和多次运行稳定性。

当前已有的 `Trace`、`EvaluationRunner`、`Scorer`、`BadCaseAnalyzer` 和种子题库先保留。后续重点补充：

- 固定任务集和版本信息
- claim–evidence–citation 级别的引用核验
- 工具参数、调用顺序和重规划评分
- 离线回放、重复运行和 `pass^k`
- BadCase 人工确认、样本生成和回归门禁

## 11. 分阶段计划

### Phase 0：基线确认

- 固化当前启动方式和开发环境。
- 跑通普通报告、多 Agent 报告和 MCP 研究路径。
- 检查 Trace、报告和输出目录。
- 不改变现有用户可用主流程。

### Phase 1：任务与能力模型

- 增加 Task Type、Skill Manifest 和 Agent Profile。
- 将现有角色和工具映射到能力模型。
- 统一工具 Schema、结果结构和错误类型。
- 增加 Run ID、任务状态和事件模型。

### Phase 2：局部 Agent 化

- 增加任务级 Planner。
- 支持动态补充检索、工具切换和有限重规划。
- 增加明确的完成条件、预算和停止条件。
- 保留稳定报告 Workflow 作为可复现模式。

### Phase 3：可恢复任务与工作区

- 将长任务执行从 API 请求中解耦。
- 保存中间状态和 Artifact Manifest。
- 支持暂停、继续、失败重试和从指定步骤恢复。
- 前端展示步骤、子 Agent、工具和文件变化。

### Phase 4：受控实验能力

- 增加 Host Profile 和权限策略。
- 增加 Experiment Recipe 和 Experiment Worker。
- 支持本地 dora 环境和用户配置的远程主机。
- 归档命令、环境、指标和实验产物。

### Phase 5：结构化报告与 LaTeX

- 增加报告中间结构。
- 增加综述和技术报告模板。
- 实现 LaTeX 渲染、编译和校验。
- 前端支持源码、PDF、图表和编译日志查看。

### Phase 6：评测和持续优化

- 建立科研 Golden Set、Adversarial Set 和 BadCase Set。
- 接入报告质量和轨迹级评分。
- 建立版本对比、回归门禁和趋势报告。
- 用评测结果反向优化 Prompt、Skill、工具编排和 Agent 策略。

## 12. Commit 计划

每完成并验证一个阶段性能力，再单独提交：

1. `docs: add agent architecture and development spec`
2. `feat: add task type and skill capability model`
3. `feat: unify tool contracts and agent profiles`
4. `feat: add task planner and bounded replanning`
5. `feat: persist resumable runs and artifacts`
6. `feat: add host profiles and experiment recipes`
7. `feat: add controlled experiment worker`
8. `feat: add structured report and latex renderer`
9. `test: add research task smoke and regression cases`
10. `docs: add deployment, experiment, and evaluation guides`

如果某个功能需要多次迭代，优先拆成“模型/接口—实现—测试—前端”的连续小提交，确保每个节点都能启动和验证。

## 13. 当前不做的事情

- 不在第一阶段实现 PPT、团队订阅、商业化和多端同步。
- 不为了增加 Agent 数量而重写已有 LangGraph 主线。
- 不把所有工具一次性暴露给顶层 Agent。
- 不允许 Agent 直接执行未授权的任意 Shell 或远程命令。
- 不在评测指标尚未稳定前宣称绝对质量提升。
- 不因为引入新能力而破坏当前普通报告生成路径。

## 14. 第一阶段完成标准

第一阶段至少应满足：

- 普通科研报告仍可正常生成。
- 多 Agent 报告仍可正常运行。
- Agent 能根据任务类型选择对应 Skill。
- 工具调用、失败、重试和重规划能够在 Trace 中看到。
- 任务可以保存中间状态并继续执行。
- 用户可以为实验指定主机、工作区、命令和时间边界。
- 实验结果和报告文件能够归档到任务工作区。
- 至少有一种综述报告能够通过固定 LaTeX 模板编译。
- 每个阶段性功能都有测试、运行记录和独立 commit。
