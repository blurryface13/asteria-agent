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

- [x] 首页与研究任务页拆成两个明确状态：初始页保留直接输入和历史研究入口；提交任务后进入任务工作台。
- [x] 首页提供独立的“进入工作台”入口，空输入时发送按钮禁用，进入工作台不会创建任务或打开检索连接。
- [x] 首页和研究工作台开始统一为深色任务界面：左侧常驻工作区导航，中间任务/报告主区，底部 composer，减少说明性 Hero 文案。
- [x] 左侧导航支持完全收起和恢复，恢复按钮始终保留在主区左上角；窄屏使用抽屉与遮罩。知识库、RAG、文档编辑、评测保留在“更多工具”中。
- [x] 默认研究结果页的报告、来源、日志、问答和图片卡片已切换到统一的深色半透明视觉层，保留原有数据组件和交互。
- [ ] 继续将结果页的 transcript、步骤、子 Agent、产物和报告问答改造成统一任务工作台；不改变现有研究 API 和 report chat 语义。
- [x] 研究 WebSocket 在连接超时、异常关闭或服务端错误事件到达时结束 loading 状态，避免把后端异常伪装成无限检索。
- [x] 设置弹窗改为客户端加载，避免 Portal 与动画依赖在 Next.js 开发态服务端渲染时阻塞首屏。
- [x] 本地启动支持显式免登录模式，前端 AuthGuard、后端 HTTP API 和 WebSocket 使用同一组本地开发开关；生产/共享环境默认不绕过鉴权。
- [x] 确认 `Hero`、工作台布局、`/login` 和根页面可独立完成首次编译并返回 200。

本轮检索故障记录：真实任务能够完成网页抓取和报告生成，但日志暴露出两个独立问题。其一，当前网络路径下部分外部检索站点和模型端点出现连接重置、TLS 握手中断或超时，原实现的非流式 LLM 请求最多重试 10 次，导致用户侧长时间停留在 loading。其二，`ollama:bge-m3` 在本机 Ollama 0.23.2 上调用 `/api/embed` 时触发 Metal `failed to create command queue`，本地 embedding runner 直接退出；该异常在每个子查询中被记录后继续，造成上下文压缩阶段失去 dense 信号。当前已将 LLM 重试预算收敛为可配置的 3 次、统一服务端错误事件，并补齐前端错误终止逻辑；这只解决任务状态不透明问题，不能替代对网络代理和 Ollama 运行时的环境修复。官方后续版本已包含 macOS 26 相关 Metal 修复，项目启动脚本会要求不低于 0.23.3 并执行真实 embedding 自检。后续固定任务验证必须同时记录外部端点连通性、embedding 健康检查、检索结果数量和报告产物，不能只以页面停止转圈作为成功标准。

本轮排查记录：修改组件时曾先删除再重建多个文件，Next.js 热更新短暂出现 `Cannot find module`；随后旧开发进程还出现根页面请求长期不返回。干净进程逐页验证后，确认阻塞点来自设置弹窗在服务端渲染阶段的 Portal/动画依赖，而不是研究编排或后端服务。验证期间并行启动多个 Next 实例又触发了 macOS `EMFILE`，使 `build`、`lint` 和 `tsc` 出现长时间无输出；这类命令不能与开发服务器或彼此并行运行。今后前端改动遵循“先新增/替换后删除临时文件、单端口干净启动、逐页 HTTP 检查、再进行浏览器交互验证”的顺序；发现端口已监听但页面不返回时，以实际页面响应和日志为准，不直接复用旧热更新进程。

本轮登录循环排查记录：旧页面曾因失效 JWT 或前后端鉴权配置不一致收到 401/4401，原前端会在 HTTP 与 WebSocket 两条路径清理本地 token 并强制跳转 `/login`；同时本地免登录开关只存在于某次启动命令的进程环境中，手动启动 Next 或复用旧标签页时容易再次落入登录页。现已统一由 `isLocalAuthBypassEnabled()` 判断本地模式，固定补入前端 `.env.local`/`.env.example` 与启动文档；明确开启本地模式时，登录页会回到首页，401/4401 会保留真实错误并提示检查后端开关和 API 地址，不再形成登录循环。非本地模式仍保持失效 token 清理和登录跳转。验证方式为：干净重启 Next、直接访问 `/login`、刷新根页面，并请求 `/api/reports`；三者均通过后再测试 WebSocket，不能只看地址栏是否变化。

本轮任务/问答边界排查记录：参考端到端科研产品的交互后，确定首页 composer 的语义是“创建长任务”，任务工作区内的 composer 才是“围绕当前交付物继续追问”；知识库问答属于独立上下文，不应复用新建任务入口。原实现的 `handleChat()` 在移动端没有报告时会调用 `handleDisplayResult()`，导致 Chat 输入被误转成新的调研任务。现已删除这条调用路径：研究报告问答必须存在报告上下文，没有上下文时只提示用户进入知识库入口；工作区在报告完成前也不展示 Ask report 按钮。后续新增全局 Chat 或意图路由时，仍需保留 `research/create`、`report/chat`、`knowledge/ask` 三种明确命令语义，不能仅凭同一个输入框状态猜测。

参考交互原则：任务页应以持续 transcript 为主，用户输入、Agent 思考、工具动作、文件产物和最终报告都属于同一任务时间线；步骤、子 Agent、主机和用量是辅助检查面板，不应打断主线。当前前端按深色工作台、半透明层次和紧凑信息密度重组，同时保留本地项目的研究品牌；后续优先补任务状态时间线、工具调用明细、报告/知识库上下文标识和可恢复的任务输入。

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

视觉上统一采用中性炭灰工作台：导航背景、任务主区、输入框三层明度，细边框与大圆角，不再叠加蓝黑渐变或玻璃卡片。初始页使用简短问候、场景示例与底部输入框；任务页使用导航、执行记录和右侧产物面板。系统字体承载操作控件，示例卡片标题使用中文衬线字体。弹窗的背景模糊只用于区分当前操作层。

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

## 15. 工作台实现记录与接入契约（2026-09-10）

### 15.1 本次前端边界

`frontend/nextjs/components/harness/` 承载新版工作台，根页面仍管理现有调研状态。保留按屏幕宽度选择不同请求链路的既有产品决策，本次不统一移动端与桌面端后端接口，也不替换模型、环境、鉴权或研究编排。

已接入：任务输入、原有调研与报告问答回调、历史报告读取、真实执行日志、检索策略设置、报告 Markdown 预览/源码/下载。历史列表点击后在当前工作台展示，原有直接报告链接保持兼容，独立报告路由的视觉迁移单独安排。

仅浏览器本地：显示名称、项目草稿。项目草稿不代表已创建后端目录，也不改变任务权限或存储位置。

界面占位：主机、目录浏览、SSH、人格、记忆、Skill 管理、任务附件、语音、团队订阅、轨迹导出及 LaTeX 编译。所有占位均明确标识待接入；不展示虚构工具耗时、Token 用量、子 Agent 状态或执行成功。现有断开按钮仍沿用原停止处理，不宣称服务端取消、暂停或可恢复。

首页分类只是可编辑提示词示例，不是强制 Task Type。用户可以直接输入任意目标；选择例子不会立即调用模型。PPT 不在本期范围，科研示例使用论文精读与实验计划。

### 15.2 下一阶段接口锚点

| 工作台位置 | 后端资源 / 命令（拟定） | 验收边界 |
| --- | --- | --- |
| 项目与任务列表 | Project、Task、Run | 项目绑定授权工作区；同一任务支持多次 Run，不把报告文件 ID 当作 Run ID |
| 主机与目录选择 | HostProfile、WorkspaceGrant | 服务端规范化路径并校验目录边界；拒绝符号链接越界；前端不保存 SSH 私钥 |
| Agent 配置 | AgentProfile、SkillManifest | 版本化工具白名单、输入输出契约、停止条件；仅暴露实际可用能力 |
| 记忆 | MemoryEntry、MemoryProposal | 区分用户偏好、项目事实、可复用经验；来源可查、支持删除，不自动存入秘密或未验证结论 |
| 任务过程与右侧面板 | RunEvent、ToolCall、Artifact | 流式事件带序号；断线后按序补齐，去重回放；展现决策摘要，不要求输出模型隐式思维链 |
| 任务操作 | cancel、retry、resume、approve | 命令需服务端确认；客户端断开不等价于服务端任务终止 |
| 报告预览 | ArtifactVersion、CompileJob | 同时保留 Markdown、结构化报告、引用、LaTeX/PDF 和编译日志，失败可定位 |

事件建议字段：`event_id`、`run_id`、`sequence`、`parent_event_id`、`agent_id`、`kind`、`status`、`timestamp`、`payload`、`artifact_refs`。敏感参数进入日志前必须脱敏。状态区分 `queued/running/waiting_approval/completed/failed/cancelled`，重试创建新的 attempt，不覆写旧失败记录。

### 15.3 从固定流程向 Agent 扩展

1. **保留成熟能力作为工具。** 将现有章节研究、检索、报告生成封装为可调用能力，而不是重写其内部流程。顶层协调者先判断是直接回答、引用报告/知识库、补充研究还是执行实验。
2. **按证据缺口调整计划。** 协调者维护目标、已知证据、未解决问题与预算。只有检索不足、来源冲突、工具失败或验收未通过才新增步骤、换检索方式或派发子 Agent；设置最大重规划次数、调用预算与截止时间。
3. **细粒度 Skill 组合。** 文献筛选、论文精读、方法比较、引用核验、数据口径核验、实验设计、LaTeX 排版是独立 Skill；任务可组合多个 Skill，按需加载，不向每个 Agent 注入全部说明。
4. **隔离子任务上下文和权限。** 子 Agent 接收问题、必要证据、允许工具、预算和输出契约；返回结果、证据引用、产物及未解决事项。并行研究共享证据索引而非互相追加完整历史。
5. **实验执行先过授权门。** 用户指定主机、目录、环境和资源预算；Recipe 固化可复用命令。安装依赖、覆盖文件、远程写入或长时 GPU 任务必须按风险要求确认。工具失败显式返回，不伪装成成功。
6. **在线成果由用户选择入库。** 报告与检索证据先作为任务产物，确认后进入离线知识库，记录来源、时间、版本和引用关系。报告问答、离线问答和新调研必须显示各自上下文，不互相静默升级。

实现顺序：持久化 Run/Event 与状态恢复 → 有预算的协调者和能力选择 → 子任务边界与证据索引 → 受控实验 → LaTeX 产物链路 → 轨迹/报告评测。每步单独测试、提交，不把全部规划一次性实现。

### 15.4 本轮验证口径

- Node 22 下执行 TypeScript 检查；补齐现有 `logs` 事件类型，未通过类型断言隐藏问题。
- 实际浏览器检查桌面与窄屏、侧栏收放、弹窗 Escape、场景填入、空输入进入工作台和占位状态。
- 保持 3023 前端与 8018 后端既有进程，不清理运行中的 `.next`，不重新安装依赖或另开 Next 实例。
- 本轮 UI 验证不等价于完整在线调研或模型质量回归；真实模型调用、远程工具、LaTeX 和恢复机制应各自记录专项测试结果。
