# Asteria Agent 开发记录

本文只记录可追溯的开发节点、真实运行结果和下一步执行计划。产品目标、架构约束、接口契约和安全边界统一维护在 [`spec.md`](spec.md)。每个功能增量都按“实现 → 针对性测试 → 真实运行 → 产物检查 → commit”的顺序推进；运行失败也保留记录，不用成功文本覆盖失败状态。

## 当前状态

- 分支：`feat/doc-edit-agent`
- Python：dora / Python 3.10
- 前端：Node 22 / 3023
- 后端：8018
- Embedding：Ollama 0.33.3 / `bge-m3` / 1024 维
- 文献综述主线：自然语言任务理解、可修订计划、人工确认、并行研究 Agent、原文阅读、引用关系追踪、证据充分性审查、Markdown/LaTeX/PDF 交付。
- 当前 Agentic 边界：研究视角和工具动作由 Agent 根据证据自主选择，子 Agent 可并行执行；已实现分阶段 Skill 发现、按需注入及用户指定。工具预算、证据来源和交付校验由运行器约束；远程自主实验执行尚未完成。既有离线 RAG 独立保留，不等于已完成在线研究成果的全量自动入库。
- 当前开发路线以 [自主实验与评测路线](docs/experiment-evaluation-roadmap.md) 为准；下文保留历次节点，不以历史待办覆盖最新实现状态。

## 开发节点

### 2026-09-12：云端 Documents 依赖复现与前端恢复（GPT-5）

- 复现了 3023 前端首页 SSR 500，而 8018 后端健康与报告接口仍为 HTTP 200 的分层故障。前端日志先后出现缺失 `@swc/helpers/_/_interop_require_wildcard`、`jsdom` 读取迟滞以及 macOS `Unknown system error -11`；这不是研究 Agent 或后端接口逻辑报错。
- 根因确认：项目位于 macOS `Documents` 云同步范围内，`node_modules` 中部分文件曾处于 `compressed,dataless` 或云端按需读取状态。手工读取会触发恢复，Node/Next 首次编译则可能在依赖链上等待或看到不完整模块，因此表现为偶发 SSR 500、卡住或启动后无响应。
- 按 `package-lock.json` 使用 Node 22 重新执行 `npm ci --ignore-scripts --prefer-online`，共恢复 870 个锁定版本依赖；未升级 `package.json`、未改写 lockfile、未执行 `npm audit fix`。精确依赖恢复后，`scripts/check-frontend-files.cjs` 的 Next/SWC、jsdom、DOMPurify 导入检查通过。
- 启动器复核发现，用户级 launchd 直接执行 Documents 内 bash 脚本会被 macOS 返回 `Operation not permitted`（退出码 126），而直接由 launchd 拉起 Node、先切换到 `frontend/nextjs` 再加载 Next 可以正常运行。当前常驻实例采用后者，保留 `WATCHPACK_POLLING=false`、Node 22、3023 和既有环境变量，不修改系统隐私设置。
- 首次冷编译首页约 68.5 秒、研究深链接约 18.9 秒；编译完成后根页面与研究页面均 HTTP 200，8018 `/api/reports` HTTP 200。未认证的 3023 `/api/reports` 返回 401 属于现有鉴权契约，不是 SSR 500；浏览器应沿用已有本地登录/鉴权状态。
- 长期约束：源码可继续放在 Documents，但应避免把 `node_modules`、`.next` 和大缓存作为云同步对象；在不改变系统存储设置的前提下，后续可将依赖/构建目录迁出云同步范围。启动前检查只负责失败快报，不用关闭消毒器、删除缓存或切换端口掩盖问题。

### 2026-09-12：真实新调研入口分流修复与 LaTeX 发布复测（GPT-5）

- 首次从页面输入单篇论文精读请求时，页面创建了会话却没有创建 durable Run；服务端实际收到的是旧移动端 `/api/chat` 请求，Tavily 未配置后返回空回答，页面显示旧版 apology。根因是新调研按视口进入了仍保留的旧直聊函数，不是自主研究器完成后的失败。该次失败会话为 `57dd441c-2490-4f50-ade2-80d06078e717`，作为入口分流 BadCase 保留。
- 修改 `frontend/nextjs/app/page.tsx`：删除移动端新调研的旧 `/api/chat` 实现，`onResearch` 在所有视口统一走 `handleDisplayResult` 和 `useDurableResearch.start`；移动端报告问答仍使用独立 `/api/chat`。因此视口只影响布局，不再决定新调研的执行协议。前端 TypeScript 检查通过。
- 首次真实运行还发现生成报告含有 `d_{\\text{model}}` 时，受控数学转换器允许 `\\text`，但模板未加载 `amsmath`，XeLaTeX 在发布阶段失败。学术和简报模板均补充 `amsmath`；`tests/test_agentic_runtime.py` 增加同类公式的真实 PDF 编译覆盖，定向测试 16 项通过。格式 Skill 同步明确：编译器/工具内部说明不能写入报告正文，发布状态由 Artifact 与事件记录。
- 修复后从 `http://127.0.0.1:3023/` 真实提交单篇 `Attention Is All You Need` 精读请求，页面经历范围确认、人工审批、原文读取、充分性审查重试、写作 Skill 加载、引用图、报告校验和 PDF 发布。conversation `49d05f96-e9fd-4b08-8327-792b011ecc5a`，Run `3726b79dd71c4a2ba73bcd9fd2d1d683`，最终 `completed`；43 条持久化事件，9 次模型调用、34,495 tokens，排队 0.72 s，含审批执行 67.23 s。浏览器显示“研究与交付已完成”，PDF/Markdown 入口可见；产物为 `outputs/scientific_70c5cc24ea854c30a2ce87d239961a1c/`、`outputs/review_0d6bbccea735483bb42e42a30f0fffda/`。
- 本次任务显示 0 个研究子任务，但事件实际包含 lead、assessor、writer 三类角色及自主研究动作；因为请求限定单篇原文，协调器选择直接路径是合理决策，不把“0 子任务”直接判为自主规划失败。开放域综述仍需通过任务范围和证据缺口触发并行研究员。

### 2026-09-12：审查证据标准、打回上限与 SSR 读取修复（Codex）

- 审查答案新增 direct / synthesis / inference / unknown 分类，保存 answer、reasoning、qualification。综合与推断必须附原始证据、推理链；推断须有限定，未知不能判为 supported。原文未实测的数字不能由推断代替。初审与一次语义复核使用同一证据原则，不新增研究编排或改变子 Agent 并行机制。
- Writer 接收逐目标审查答案与类型，区分作者事实、跨来源综合和分析；相同来源可在明确的论断组/段落统一引用，避免逐句重复链接。仍不声称已实现全文逐句事实核验。
- 默认同一目标连续 3 次独立证据审查被拒即停止自动补研（首审后最多两轮），通过 `REVIEW_MAX_GOAL_REJECTIONS` 设置 1–8。新 evidence ID 不重置未解决目标的计数，已满足目标不计入连续拒绝；缓存重读不重复计数，保留既有无证据增量停止保护。达到上限返回 incomplete、记录 review_limit 和缺口，不强行交付。过程要求也遵守此上限。
- 测试：审查、Agent、Run、workspace、评测合计 52 项通过。新增限定推断合同、未知拒绝、不同新证据下仍受打回上限约束、临界轮真实通过不被拦截等用例。
- 真实定点回放：复用失败目录 `review_c2a9133e57844b2e81364ccaa74fe0fa` 的同一计划和原文证据，未重新搜索/下载/写报告。`review_49670f0eb70844d7820c2453a3ba1ce3` 一次审查 ready=true，3 个目标 supported，局限回答区分直接说明与条件推断；10.90 s，输入 8,572 / 输出 1,830，共 10,402 tokens。反例 `review_6b39c1071e954883beceefb480bfd48b` 要求原文没有的百万 token 序列实测显存数字，一次审查为 missing/unknown；5.42 s，共 8,966 tokens。模型适配器为既有 deepseek-chat；费用未计价。定点验证不等于又跑完一次广域研究。
- SSR 根因证据：短暂诊断记录具体失败路径 `node_modules/dompurify/dist/purify.es.mjs`；`ls -lO` 显示 compressed,dataless。前台读取将内容恢复本地后，错误继续暴露 `tldts` 元数据及 jsdom/entities/css-tree 内部文件的云端读取问题。恢复占位文件，并按锁文件版本、SHA-512 校验的官方包修复 jsdom 29.1.1、entities 6.0.1、css-tree 3.2.1，保留 jsdom 嵌套依赖；未升级依赖、修改 lockfile、关闭消毒器或删除 .next。旧包留在 `/tmp/asteria-jsdom-repair.oruHWU/jsdom-before`、`/tmp/asteria-package-repair-mY1Exj/before`、`/tmp/asteria-package-repair-db0wJv/before`，属于临时可恢复备份。
- 启动新增 `scripts/check-frontend-files.cjs`：在独立进程实际导入 jsdom/DOMPurify，最多 30 秒；失败输出依赖可读性诊断，不带错误进入服务。终端启动与本机 launchctl 均接入检查，临时读取追踪已撤下。只检查实际 SSR 消毒依赖图，未保留全 node_modules 云端下载方案。系统仍可能再次卸载云端文件；长期应将依赖目录保持下载，或单独规划迁出云同步目录，不擅自改系统存储设置。
- 确认无活动研究后按原 dora/Node22、8018/3023 重载 API、worker 与前端，使新审查代码生效；没有打断用户进行中的任务。
- 修复后首页、历史报告深链接均为 HTTP 200，Run API 为 200，worker ready；启动依赖检查实际成功，诊断用 NODE_OPTIONS 已移除。原构建缓存与前端样式保留。

### 2026-09-12：公式出版修复与本轮收尾（GPT-5）

- 在不改变报告模板、PDF 安全边界和前端设计的前提下，修复 Markdown → LaTeX 转换：行内 `$...$`、`\(...\)` 和独立行 `$$...$$`/`\[...\]` 进入受控数学环境；正文仍使用原有严格转义。仅保留出版所需的常见数学命令，未知命令和 `\input` 等执行性命令继续转义，`xelatex -no-shell-escape` 保持不变。
- 回归覆盖数学结构保留、恶意 TeX 不执行、真实中文 PDF 编译。复用已保存报告渲染 PDF 后，公式已显示为排版后的数学式；本机 Poppler 截图仍提示缺少 Adobe-GB1 中文映射，中文缺字属于本机预览器字体包问题，不影响 TeX 编译和浏览器 PDF 产物。
- 最终验证：Python 回归 69 项通过，TypeScript 检查通过，`git diff --check` 通过；3023 首页与 8018 报告接口均为 HTTP 200，前端、API、worker 用户级服务 `LastExitStatus=0`。没有重新发起付费研究任务。
- 本节点由 GPT-5 执行并记录；后续独立待办仍包括完整报告的论断级引用/推断审查、数学以外的 LaTeX 结构支持，以及将云同步目录中的 `node_modules` 迁出或固定下载。
- 收尾冷启动复测发现旧的 `WATCHPACK_POLLING=true` 会放大云端 Documents 下 Next 开发服务的依赖读取死锁；清理本项目残留 Next/构建进程后，以原生 watcher 重启，3023 首页、研究深链接和报告 API 均恢复 200。启动脚本默认改为 `false`，`true` 仅作为遇到 `EMFILE` 时的显式选项。本项由 GPT-5 完成。

### 2026-09-12：E1 后台研究运行与页面恢复（Codex）

- 新增 PostgreSQL Run、Job、Event、Approval、Artifact；桌面研究由独立 dora worker 执行，API 接收请求、审批与取消，浏览器按事件序号补拉。现有主 Agent、并行研究员、Skill 和出版编排不改写，移动端与外部 LangGraph 分支不迁移。
- 提交幂等、同会话活动任务互斥、worker 租约与过期写入拒绝、审批绑定、真实取消和服务端保存报告已实现。进程异常退出标记 interrupted，不自动重跑未知工具动作。真实 provider usage 随并行上下文归档，缺失用量和费用显示 null，不推算账单。
- 前端沿用 DESIGN.md，只修正状态含义与恢复逻辑：停止不再等于关闭连接；完成报告保留后续问答；独立进行中对话进入侧栏；临时服务错误重试观察，不重发任务。React StrictMode 会清理并重放 effect，恢复请求世代与深链接 guard 必须一起复位，否则可能留下空白任务页。修改依赖数组后需等编译完成再完整刷新，不能把热更新中途的旧闭包当成稳定状态。
- 运行中对话不允许删除，已结束对话按用户删除动作事务清理关联数据库记录；错误时前端不伪装删除成功。输出文件不递归清理。
- 启动问题：launchd 不继承交互终端 PATH，初始 worker 无法发现已安装的 xelatex。新增 `scripts/start-research-service.py` 固定 cwd 与进程路径，worker 启动前检查编译器；未更换 dora、Node22 或端口。remove 后立即 submit 同名 launchctl 标签可能与旧标签退出竞争，必须确认旧服务移除再提交；前端不重启、不删除 .next。
- 针对性测试：`tests/test_durable_runs.py`、`tests/evaluation`、`tests/test_workspace_contract.py` 与 `tests/test_agentic_runtime.py` 共 25 项通过，覆盖幂等提交、竞争领取、用户所有权、审批幂等、事件序号、取消、租约过期、空报告失败与删除互斥；前端 TypeScript 和增量 ESLint 通过。数据库测试在随机独立 schema 中运行，仅清理测试自身数据。首次沙箱拒绝本地数据库连接是执行权限问题，经批准在同一 dora 环境复测通过。

#### 本轮真实运行记录

| Run | 结果 | 执行墙钟 | 模型用量 | 说明 |
| --- | --- | --- | --- | --- |
| `2641df32955b4d80bdf6844e249ac486` | failed | 13.14 s | 7,146 tokens，5/5 次返回 usage | 600 字原文精读请求在 Planner 目标分类合同校验失败，尚未研究；刷新保留同一 Run，不放宽合同掩盖错误。 |
| `a7142532375f4a0da74930856f9e985b` | cancelled | 96.25 s，含审批 15.25 s | 7,683 tokens，4/4 次返回 usage | 1000 字原文精读计划修复后进入审批，网页停止真实取消 worker，刷新后仍为 cancelled。 |
| `36b7550e5d3a40cca0d7b81e93dd38d6` | failed | 1.67 s，另排队 60.24 s | 未返回 usage，不能记作 0 token | DeepSeek HTTP 402；未进入论文阅读，未换模型或继续重复扣费请求。排队含 worker 重启间隔。 |

以上执行墙钟不含排队；费用字段未计价，不能用 token 数冒称人民币账单。原计划分类失败单独保留为研究质量 BadCase，不等同于后台任务持久化失败。

- 用户确认充值后，以同一 1000 字精读请求创建 Run `f2b07aadb31244ffa4508a651b6818d1`，conversation `e861deab-3e49-4f5a-aaff-1ebf7891f64b`。人工审批期间单独重启 API，worker 保持，Run ID、审批 ID 和事件序号 18 不变；刷新恢复审批并经网页确认后开始原文阅读。关闭测试页面后研究继续，最终真实状态 failed，108 条事件，执行墙钟 406.31 s，其中审批等待 243.97 s；32/32 次返回 usage，共 345,425 tokens（输入 316,501、输出 28,924）。费用未计价。
- 该次失败为既有充分性审查的语义误阻塞：g1 核心机制、g2 实验条件已 supported；g3 已有复杂度、任务范围与未来工作原文，复核仍要求“其他局限直接自述”，将可明确标注的推断性限制当作必须被原文直接陈述的事实。主 Agent 多次 finish 被拒，最终按不足终止，没有伪造报告。原有提示词虽禁止要求独立局限章节，但仍未稳定解决“直接事实与推断的证据标准”混淆。此问题列为下一项研究审查修复，不在 E1 中通过删目标、放宽所有验证或切回旧 workflow 掩盖。

- 最终交付联调 Run `d36eff15f3264a35afec27b435690818`（conversation `7591aaff-7c19-44a6-972d-577e3a1a1395`）完成。任务限定 Attention Is All You Need 原文的注意力机制精读，保留自主工具和 Skill 选择，不涉及局限分析。09:03:03.891 UTC 开始、09:06:13.160 UTC 完成，排队 0.030 s，执行墙钟 189.269 s，含人工审批 161.834 s；扣除审批约 27.435 s，但不是模型纯推理耗时。8/8 次返回 usage，输入 23,869、输出 2,365，共 26,234 tokens，费用仍为 null。
- worker 保存 41 条事件及 13 项产物索引；逐项校验文件大小与 SHA-256，Markdown、TeX、PDF 下载均返回 HTTP 200。新开会话链接从服务端恢复已完成报告、轨迹及报告问答模式，无需重新研究；LaTeX 面板能关联加载源码与 PDF。该短任务验证 E1 后台运行与交付闭环，不代替上述局限审查失败用例，也不代表开放域综述效果已全面验证。
- 出版预览发现既有公式处理缺陷：Markdown 公式未排版，TeX 转换把 `$`、反斜线等作为普通文本转义，导致编译成功却显示公式源码。记录为下一笔独立出版修复：保留受控数学节点、区分正文转义与数学表达式，并验证网页及 PDF 公式渲染；不把本次 HTTP/哈希校验视作排版质量通过。无需新付费研究，可用本次已保存报告复测。
- E1 提交 `d0c1d6c2` 已同步远端 main 与功能分支。最终 HTTP 检查发现独立前端问题：3023 服务仍监听，API 与报告读取为 200，客户端可恢复已保存报告，但首页 SSR 返回 500，日志为 `Unknown system error -11, read`，根因尚未确认。准备保留原 Node22、端口及全部参数的短暂重启以定位读取文件；执行授权审查拒绝了停止/重启操作，因此未实际停止服务、未改变启动参数、未清缓存。需用户明确允许此次前端短暂维护后继续，不能声明当前所有页面健康。

### 2026-09-12：评测工作台 Task0、设计规范与项目展示

- 复用现有深色 harness 外壳与图标，新增运行记录、批次、题库、BadCase、标准目录；通过既有认证接口读取真实数据，保留错误、加载、空态和缺失指标口径。自主运行时评分、重跑与版本对比尚未接入，相应按钮明确禁用。
- JSONL 导入、父子 Trace 展开、规则归因、人工采纳及种子回流已经从网页联调。点击当前标签不会清空列表，详情关闭恢复列表焦点；历史会话可返回研究页，不会重新发起调研。
- 联调用库中已有 `demo-trace-001`，生成 BadCase `6f9f858ba55f4d9f9e4336299736c0b0`，人工采纳并回流种子 `93cc0fa93f5b4dcfb19e1dc1d8cd16be`。备注明确这是界面联调示例，不纳入冻结测试集；新种子仍需独立质检。非法 JSONL 返回 400，没有伪造成功。此次没有发起新的收费模型任务。
- 针对性检查：dora 环境 `tests/evaluation` 6 项通过，前端 TypeScript 检查通过，新增评测页面 ESLint 无警告。网页验证搜索空态、批次空态、29 项标准读取、侧栏开关和历史报告预览；未修改研究任务的运行逻辑。README 使用真实历史综述与评测页截图替代原框架图；新增 DESIGN.md 与评测路线文档，保留当前研究界面的设计语言。
- 生命周期排查：临时终端进程在会话中断后退出，单纯 nohup 未解决；当前由用户级 `com.asteria.frontend3023` 保持前端运行。macOS 拒绝该后台环境通过 bash 读取 Documents 内脚本，改为直接启动 Node，不改变系统隐私权限。必须先 `process.chdir(frontend/nextjs)` 再加载 Next：仅传项目绝对路径而不切 cwd，会使 Tailwind 相对 content globs 扫描错误，表现为样式丢失，而不是 Agent 服务故障。
- 环境未升级：Node 22 / Next 14.2、dora / 8018、前端 3023；未删除缓存、切换模型或关闭 TLS 校验。后续维护先查现有进程和工作目录，避免多实例争用。

### 2026-09-11：证据驱动的综述链路

- 将研究目标、过程要求和交付约束分离，避免“写约 2500 字”被错误当作研究充分性目标。
- 增加充分性审查、证据 ID、已读取来源约束、引用关系图和写作后交付校验。
- 保留在线 RAG 可选开关：开启时使用混合检索，关闭时由 Agent 通过原文页段工具阅读；两种模式都不允许引用未读取来源。
- 真实回放完成过一条已有证据的综述交付；新的开放式联网任务受 arXiv 限流、Ollama 生命周期和模型余额等外部条件影响，均按实际状态记录。

### 2026-09-11：Planner 契约修复

- 原因：模型可能为多个研究目标生成相同的 `g1`，导致研究还未开始就触发“研究目标 ID 重复”。
- 第一轮修复：增加一次显式 `plan_repair`，将候选计划和校验错误交回 Planner；修复失败时明确终止，不继续研究。对应 commit：`95c55287`。
- 真实复测发现：模型可能收到修复指令后原样返回候选计划，单靠第二次模型输出仍不可靠。
- 第二轮修复：在第二次输出进入 Pydantic 校验前，增加只修改重复/非法 `gN`、`pN` 标识的确定性归一化；不修改描述、用户原话、研究范围或可选扩展。对应 commit：`a5afa6a4`。
- 回归：完整 Python 测试 `77 passed`；真实 WebSocket 任务已越过 Planner，进入 `plan waiting → delegate → 3 个并行研究 Agent → 论文读取 → 充分性审查`。

### 2026-09-11：Safari 真实综述运行

- 用户从 Safari 发起数字水印综述任务，使用 DS4 Flash（模型名称由用户确认）。
- 运行目录：`outputs/review_3ea4b134b7c44e7a9ef34ef307ba685e/`
- 结果：`completed`，无错误；19:20:18 开始，19:29:15 完成，运行器耗时 `536.14s`（约 8 分 56 秒）。
- 统计：70 次模型调用、46 次 Agent 操作、4 个子 Agent、读取 19 篇论文、87 次 embedding 调用/1050 条 embedding 文本、下载 `100,044,410` bytes（约 95.4 MiB）。在线 RAG 开启，Markdown、LaTeX、PDF、引用图、证据和充分性审查产物均生成。
- 额度：用户侧自查约 `2.41 元人民币`。当前运行器只保存字符数和调用次数，没有保存上游 token/usage 字段，因此该金额不能由本地记录独立复算，也不能用字符数替代官方额度。
- 对应文档 commit：`5d2edde9`；后续计划文档 commit：`4ca3efc9`。

### 2026-09-11：启动与运行问题

- 旧后端进程未加载最新代码，重启后才确认 Planner 修复实际行为。
- 受限执行环境无法创建既有 `logs/app.log`，导致服务启动权限错误；在允许个人项目写入自身日志的会话中，用 dora 恢复原 8018 端口。
- 第一次 90 秒真实冒烟在修复前因 Planner 契约失败；第二次在确定性 ID 修复后成功进入研究阶段，但测试脚本到时主动取消，状态为 `cancelled`，不计为完整报告交付。
- 启动约束：优先复用 3023/8018/11434；先查端口和健康状态，确需重启时正常停止所属进程；不通过递增端口、清理 `.next` 或切换 Python 环境规避问题。

## 后续计划

计划按两个层级维护：第一层是大方向，第二层是可以独立实现、测试和提交的功能任务。

### 2026-09-11：持久化与项目/对话层级（第一笔实现）

- 现状确认：报告、项目、对话和对话消息均已有 PostgreSQL 存储；浏览器 `localStorage` 只承担首屏缓存、显示名称、当前项目选择和旧草稿迁移，不再承担已保存任务的唯一事实来源。
- 参考 JAgent 后确定边界：PostgreSQL 保存项目、对话、消息和报告索引等长期事实；Redis 只保留验证码、短期状态等易失数据；向量库继续服务 RAG，不承担会话主数据。
- 已实现：新增 `workspace_projects`、`workspace_conversations`、`workspace_messages` 表及幂等启动建表；新增按用户隔离的项目、对话、消息 CRUD API。
- 当前提交：`backend/auth/workspace_*` 与 `backend/auth/schema_bootstrap.py`；现有报告 API 保持兼容，前端已通过 Workspace API 读取项目/对话并把新研究绑定到 conversation/project。
- 下一笔实现：补正式的报告索引/外键关系、从 conversation 恢复完整报告视图、项目内任务分组和服务端批量清理接口。
- 提交 `0ba8d1f0` 完成后端 Workspace 持久化基础；提交 `4fc684f6` 接入前端项目读取、项目创建和 Workspace API 代理，并让新研究使用稳定的 report/conversation ID。
- 真实验证：本机 PostgreSQL schema bootstrap、标识长度迁移、创建/写入/查询/删除会话闭环均通过；重载 dora 后端至 8018、Node 22 前端至 3023 后，后端接口、前端代理和首页均返回 HTTP 200。
- 提交 `44a9fbf6` 让新研究读取当前项目并绑定 conversation，补充项目删除和侧栏对话计数刷新；研究首条问答与后续 Chat 消息同时写入 Workspace 消息表。
- 提交前端服务端优先恢复改动后，即使浏览器没有 `localStorage` 历史，也会从 PostgreSQL 加载报告；本地缓存只用于首屏展示和旧草稿迁移，不再因为本地没有 ID 而跳过服务端查询。
- 真实验证：通过 3023 前端代理创建项目、创建带 `project_id` 的 conversation、写入并读取消息、按项目筛选，均返回预期结果；临时项目和 conversation 已删除，数据库恢复为空。
- 启动复核发现：后端不是热更新模式，源码新增路由后必须重启既有 8018 进程；曾因此出现源码有 DELETE 路由但运行实例返回 405。后续每次后端功能提交后都要重启或确认 reload，并检查路由 HTTP 方法，不用递增端口掩盖旧进程。
- 当前边界：报告与 conversation 仍通过相同稳定 ID 关联，正式外键/报告索引字段、从 conversation 直接恢复完整报告视图和服务端清空历史仍待后续独立实现。
- 本轮增量：研究提交前先创建 conversation，因此项目下会先出现进行中的子任务；项目详情面板增加“在此项目中新建任务”和项目任务列表，完成任务可直接打开，运行中的任务显示状态。桌面和移动端共用同一个 conversation/report ID。
- 本轮前端微调：侧栏已有项目行新增独立的“新建对话”按钮，直接激活项目并回到主任务输入区，不再先打开项目详情弹窗；项目名称仍可点击进入详情，项目与对话绑定逻辑保持不变。
- 本轮前端收敛：移除项目详情中重复的新建任务按钮和说明文字，将侧栏图标作为唯一的新建对话入口，详情面板只保留项目任务列表。

### 大方向一：运行稳定性与可观测性

1. **运行记录对象统一**
   - 功能实现：为每次 Run 固化 task、provider、model、参数、Skill/Tool 版本、开始/结束时间、状态、取消原因、产物路径和环境指纹。
   - 功能实现：在模型适配层记录 input/output tokens、cached/reasoning tokens（上游提供时）、费用和请求级失败原因；密钥不落盘。
   - 功能实现：前端用量面板区分模型额度、embedding 用量、下载量和本地耗时。

2. **启动与故障诊断收敛**
   - 功能实现：将 dora、Node 22、Ollama、3023、8018 的检查收敛到一个可重复执行的启动前检查。
   - 功能实现：区分旧进程、端口占用、日志权限、代理/TLS、模型余额、Ollama 退出和上游限流；错误必须带具体阶段和恢复动作。

### 大方向二：文献综述从工作流继续演化为 Agent

1. **意图与计划控制**
   - 功能实现：用户只输入自然语言；Planner 输出任务目标、证据问题、过程要求、交付约束和可选扩展，不要求手动选择任务类型。
   - 功能实现：保留一次人工确认和可修改计划；补充计划版本、目标 ID 稳定性和用户要求/模型扩展的来源标记。

2. **自主证据扩展与结算**
   - 功能实现：子 Agent 根据不同证据缺口自主选择检索、阅读、引用追踪或补充视角，不将所有视角固定为必做步骤。
   - 功能实现：沿已读论文参考文献递归发现候选论文，基于原始书目和实际读取状态建立引用关系图。
   - 功能实现：增加独立结算/充分性审查角色，只检查核心研究问题、过程要求和证据支持；篇幅与格式在写作后校验。
   - 功能实现：加入重复论文、无效补研、证据不足、冲突来源和预算耗尽的明确停止分支。

3. **研究轨迹工作台**
   - 功能实现：前端默认按阶段聚合 `plan / research / evidence / synthesis / delivery`，不平铺全部工具事件。
   - 功能实现：每个阶段可展开查看具体 Tool、Skill、Sub-Agent、输入摘要、输出摘要、耗时和失败原因。
   - 功能实现：报告段落、证据片段、论文来源、引用图节点和 LaTeX/PDF 页面可以互相定位。

### 大方向三：复现实验与可控工具生态

1. **实验任务与工具选择**
   - 功能实现：从用户意图识别“设计实验”和“执行实验”，由 Planner 决定需要的工具组合，不把实验流程写死成固定节点。
   - 功能实现：定义实验专用 Skill、Tool Schema 和 Experiment Manifest；记录数据、代码版本、参数、命令、环境和产物 hash。
   - 功能实现：根据工具是否需要长上下文、代码执行或外部服务，决定使用专用 Sub-Agent、MCP 或现有工具适配器。

2. **安全边界内的执行闭环**
   - 功能实现：用户配置允许访问的服务器地址、工作区和命令白名单，执行前展示计划并请求确认。
   - 功能实现：实现执行、日志采集、超时/取消、结果校验、失败重试和可复现重跑；禁止越过授权范围访问文件或服务。
   - 功能实现：优先支持论文复现实验和可重复的数据分析，不先扩展到无边界的通用代码执行。

### 大方向四：在线调研与离线知识库

1. **在线调研支线**
   - 功能实现：保留在线 RAG 开关、原文阅读和证据追踪；在线内容必须先经过来源核验再进入报告。

2. **离线知识库支线**
   - 功能实现：允许用户从已完成任务中选择论文、报告、实验结果入库，保存来源、版本和内容 hash。
   - 功能实现：Chat 入口根据当前上下文明确区分“报告问答”和“知识库问答”，不能误触发新调研。
   - 功能实现：离线回答只使用知识库内容，展示命中文档和证据位置；后续再比较在线/离线 RAG 的质量、延迟和费用。

### 大方向五：Agent 评测与持续优化

1. **评测载体**
   - 功能实现：优先适配稳定的开源评测运行器，复用现有 Trace、Dataset、Solver、Scorer 和 BadCase 结构，不重新实现一套平行 Agent。
   - 功能实现：固定任务集、语料快照、模型/Skill/Tool 版本和预算，支持同一任务多次重复运行。

2. **指标与回归**
   - 功能实现：评测意图路由、计划契约、工具选择/参数正确性、论文发现召回、引用关系准确性、claim-source 支持率、核心目标完成率、无效补研率、停止决策、延迟和费用。
   - 功能实现：将线上失败轨迹转为可复现 BadCase，支持定向修复、回放、指标对比和回归门禁。

### 2026-09-11：综述报告写作 Skill 第一笔增量

- 现状盘点：已有 `literature_review.md` 主要约束研究范围、证据、补研与停止条件；已有 `latex.py` 负责安全 Markdown→TeX→PDF，但报告写作规范和 LaTeX 兼容性约束尚未独立建模。
- 本轮实现：新增 `agentic/skills/report_writing.md`，将综述结构、证据/引用纪律、比较条件和 LaTeX 兼容写作规范从研究 Skill 中分离；现有 `AutonomousReview` 的 writer 同时加载研究 Skill 与写作 Skill，不改变 Planner、子 Agent、补研和停止逻辑。
- 本轮实现：新增 `agentic/report_tools.py`，抽取确定性的引用来源、篇幅和标题检查；报告检查事件额外保存问题列表与标题摘要，修订请求携带机器校验结果。
- 本轮实现：能力注册表补充 `report_structure_check`、`citation_audit`、`latex_compile` 三类工具契约，并注册 `report_writing` Skill。当前工具仍在进程内复用，属于能力边界声明和可测试校验，不宣称已经实现完整 BibTeX 或复杂排版。
- 设计来源：参考 UC Berkeley Gallant Lab 的证据台账/引用核验/前置文献追溯思路，以及 PaperMentor 的细粒度写作 Skill 思路；只借鉴机制，不直接复制外部代码。
- 待验证：使用 dora 环境运行新增单测和现有 Agentic 回归；随后再决定是否引入综述 LaTeX 模板、BibTeX 和结构化报告中间层。

## Commit 规则

- 一个 commit 只解决一个清晰的能力或问题。
- 代码改动必须同时补针对性测试；运行器/前端改动需要额外做真实启动或浏览器复测。
- 运行成功、运行取消和运行失败分别记录，不能用单元测试替代真实任务结果。
- 每次提交前检查 `git diff --check`、工作区状态和产物路径；远程同步以个人仓库和明确分支为目标。

### 2026-09-11：复用外部综述 Skill 与通用格式 Skill（GPT-5）

- 实际读取 Gallant Lab `literature-review-toolkit` 的公开 `PLAYBOOK.md`、`tools/search_prompt_template.md`、`tools/README.md` 与 `tools/review_paper.py`。其中 PLAYBOOK 以 MIT License 发布；AI-Researcher 的 `paper_agent/writing.py`、`section_composer.py`、`methodology_composing_using_template.py`、`tex_writer.py` 和模板目录用于结构参考，未复制其未声明许可证的代码。
- 复制并最小适配 Gallant 的检索提示词模板和综述写作核心到 `asteria_researcher/agentic/skills/vendor/gallant/`，保留来源 commit `4c95c5be9fd4e28a95458a4055af0f8affb64020` 与 MIT 许可证。外部内容不替代本项目的 `literature_review.md`，而是作为 Writer 的补充指导。
- 新增 `report_formatting.md` 通用格式 Skill，明确内容对象、格式 Profile、模板和 Renderer 的边界，允许未来企业背调、娱乐话题、数据分析在缺少领域 Skill 时复用通用写作规范。
- `AutonomousReview` 的 Writer 实际加载：`literature_review`、`report_writing`、导入的 Gallant 综述指导和 `report_formatting`。本轮不改变 Planner、子 Agent、在线 RAG、停止条件或 LaTeX 转换器。
- 新增 2 个 Tool 契约：`bibliography_resolver`、`citation_graph`。它们分别映射到已有的参考文献解析和引用图落盘能力；注册表从 6 个 Tool 增至 8 个，不宣称新增了外部服务或完整元数据验证器。
- AI-Researcher 的关键启发：章节写作可以通过 section composer + writing template + renderer 分层；但其模板是论文领域/章节相关的写作示例，不等于通用 LaTeX 模板。下一步继续拆出 `ReviewDocument`、独立 `survey` format profile 和 BibTeX 生成，不把格式细节继续堆进提示词。
- 待验证：dora 环境完整测试、`git diff --check`、外部 Skill 文件加载回归；通过后形成独立 commit。

### 2026-09-12：项目树与按需写作 Skill（Codex）

- 项目侧栏改为可展开的项目 → 对话树，悬停/键盘聚焦显示详情与新建按钮；项目内新建直接聚焦输入区。独立任务列表排除已有项目归属的会话；当前项按 ID 高亮，全局新任务清除项目上下文。保留深色样式及既有响应式路由。
- 对没有最终报告的会话，读取 workspace 会话和消息展示历史快照，不再把“暂无报告”当作不可打开。不会声称历史快照等于任务续跑。
- Skill 由 skills/catalog.json 和 SkillSession 统一发现、校验、按需注入。研究阶段新增真实动作 load_skill，主/子 Agent 各自持有加载上下文。写作阶段由模型单独选择内容 Skill 和 format_profile；初稿、修订共用相同注入。版本和内容 SHA-256 可追溯。
- 通用格式契约、内容指导、TeX 模板与发布工具分开。academic/brief 两套本地模板可交叉搭配内容 Skill；简单列表和表格确定性渲染，不执行模型宏。通用写作指导可复用，但未接此 Writer 的其他入口不因此自动获得新能力。
- 上游复用纠正：旧 review_article_skill.md 是历史改写，不是原文复制，停止注入；新增固定 commit 的原文 source_priority.md 与独立适配，保留 MIT 许可。旧 bibliography_resolver/citation_graph 只是既有能力的说明性契约，不计为新增可执行动作。

#### 验证与真实运行

- Node 22 TypeScript 检查通过；dora 的针对性检查 22 项通过（含真实中文 XeLaTeX 编译、写作修订、加载边界和能力注册）；git diff --check 通过。未开展大规模测试。
- 真实配置模型单独调用 select_writing 成功：选择 report_writing v2 + source_priority v2，版式 brief；注入 report_formatting v2，输出契约检查为 true。模型主动说明不选择 general_writing/experiment_design 的原因。这是写作选择验证，不等同于完整研究成功，也未证明本次研究循环实际选择了 load_skill。
- 浏览器创建“科研写作 · Skill 联调”项目，项目内直接新建、子任务归属和折叠层级正常；前端 3023 返回 HTTP 200，后端 8018、PostgreSQL、Ollama 与模型请求均曾实际响应。服务维持原端口和 dora/Node 22。
- 第一条真实任务 review_db1b21fa99cb45d0b568a2987558f489 在开发期间因 Next Fast Refresh 整页刷新而断开 WebSocket，运行器取消任务。运行任务期间不再修改页面或 hook 文件。
- 第二条 review_d4c35ed5608a4caabf3c886a90f69f95 经人工修订计划进入研究，但对话中断后最终记录为 cancelled：195.88s、6 次模型调用、0 次工具操作、0 篇已读论文。未生成 writing.json 或最终报告，不计端到端通过。耗时含人工等待，不是推理延迟；无账单 token/费用结论。
- 发现未解决问题：Planner 会将“无需检索/不追踪引用”错误归为正向 process_requirements；通过现有人工反馈可以纠正为 []。本轮不改停止条件，不掩盖该缺陷。下一轮应优先修正肯定/否定过程要求的语义分类，再进行一次完整浏览器交付。

#### 下次接续

1. 修复上述过程要求的极性分类，避免禁止行为反而成为完成门槛。
2. 冻结前端改动后跑完短篇综述，检查 writing.json、实际 Skill 事件及 Markdown/TeX/PDF 预览；不要把中断任务写成成功。
3. 后台任务与 WebSocket 生命周期解耦另立增量；复杂公式、图表资产、跨页表格和 BibTeX 按需求逐项补齐。

### 2026-09-12：Skill 指定、研究目标与停止条件（Codex，GPT-5）

- 完成任务级 Skill 指定/浏览、阶段加载和版式选择；目录 7 项，4 项可指定，3 个主内容 Skill 互斥，系统规范不可取消。用户指定、Agent 自选、系统契约分别记录，不新增任意脚本权限。
- 处理否定过程要求误分类、分类 ID 遗漏的有限反馈修正；保留原始需求，分类后约束可重新加载。移除审查上下文和 Writer RAG 中的章节/视角耦合；literature_review v4 只约束研究证据，不规定报告章节。
- 初审存在“有证据但要求更系统/独立章节”的误阻塞。增加一次有界语义复核，不以字符串规则或预算放行；原文 ID、引用片段与来源验证在两级审查中一致生效。无新证据复用结果，不反复审到通过。
- 没有改变动态 goal_ids 委派、独立研究循环与并行子 Agent；写作章节规范只在写作侧生效。设计与外部项目核对见 spec §21、docs/skill-reference-study.md。

#### 真实运行记录

| 运行 | 结果 | 说明 |
| --- | --- | --- |
| review_45a4fe4926464764aa58d60f40532e75 | failed | 浏览器主动指定两个 Skill 和 brief，约 171 秒；已读论文但审查错误要求独立局限章节，没有交付。 |
| review_0f65351bc6f04f31bd4416825a0e0821 | failed | 分类输出遗漏目标 ID，停在研究开始前；随后补分类反馈修正。 |
| review_6f18263bdcf34f499c3ed1184d49220f | failed | 仅调整初审提示词仍要求系统性局限自述；保留原证据和失败轨迹。 |
| review_e9f32dc05d08483cac1fde6b86e0a810 | replay passed | 复用上述已读证据，审查、写作及 PDF 编译通过；不是完整检索测试。 |
| review_f62b4a4604b2459483201738039226b1 | completed | 同一请求通过实际 WebSocket 从规划、人工确认节点到原文读取、RAG、审查、写作及编译完成。测试脚本按预先限定的单篇原文范围确认计划，不代表 UI 人工点击。 |

最终请求：仅基于 arXiv:1706.03762，约 1000 字中文精读，说明核心机制、实验条件和局限，不检索额外论文，交付 LaTeX/PDF 简报。模型配置不变，online_rag=true；report_writing 与 source_priority 为用户指定，brief 版式被保留，report_formatting 为系统契约。

- run.json：研究+写作 61.74 秒（不含发布），18 次模型调用、8 次动作、3 次充分性审查、1 篇已读论文、2,215,244 bytes；embedding 7 次/53 文本。单篇任务未派子 Agent，本次不能证明并行性能或广域发现质量。
- 第 2 次审查触发复核且仍拒绝结束；补读原文复杂度表与适用条件后第 3 次通过，没有强制改状态。初始计划重复 ID 与分类错误都经既有反馈修正后继续。
- 产物：scientific_57e7cb056af94ea0ac12cb949820bcc2，Markdown、TeX、2 页 PDF 和编译记录均存在。写作检查 849 中文字符、1 个来源、无未读 URL；非逐句事实核验。writing.json 保留选择原因、实际注入内容、版本和哈希。
- PDF 两页已渲染查看，无裁切/重叠；复杂公式仍是当前支持范围内的简化文本，后续单独增强数学排版。系统 Poppler 缺 Adobe-GB1 映射，改用现有 dora PyMuPDF 检查，不重装依赖、不修改报告来迎合检查器。
- 字符计数不是账单 token，没有新费用估算；之前用户报告的 2.41 元不复用到本次运行。

#### 启动与检查

- dora 68 项针对性测试与 1 项传输测试通过（6 项依赖弃用警告）；Node 22 TypeScript 无增量类型检查通过。浏览器复核项目树与 Skill 入口，窄屏明确只读，保持原响应式路由。前端 3023 和后端 Skill API 均返回 200。
- 本轮续接时旧前端出现端口监听但 HTTP 不响应，在同一 3023 正常重启后返回 200；没有删除 .next 或升级 Next。后端正常停止拥有的会话，再在 8018 启动。续轮权限重置一度阻止日志写入，恢复目录权限后启动成功，不是应用功能故障。
- 仍未覆盖：浏览器断线后台续跑、通用旧入口主动 Skill 配置、任意社区包导入、复现实验实际执行。下一笔功能优先级沿用 spec，而不是在本轮追加平行 Agent 框架。

### 2026-09-12：口述稿、后续路线与 Git TLS 修复（Codex）

- 将当前设计的面试口述与四条目标简历归档到 docs/resume-agentic-draft.md，按自主调研、受控实验、评测回归、RAG 明确已实现和待完成范围。
- 新建 docs/experiment-evaluation-roadmap.md，区分大方向与 E1–E4 / V1–V4 功能增量。自主实验先处理后台生命周期与授权执行，再做诊断修正和可重现交付；评测主要确定运行适配、指标分母、冻结任务与消融口径，本轮未安装 Inspect 或开展新付费评测。
- 代码核对发现旧评测 Executor 未覆盖当前自主运行时，Scorer 中部分指标仍基于标题、URL 和工具名称集合；明确列为后续改造，未把这些启发式成绩描述为事实支持评测。修正文档中的动态 Skill 待实现、评测 SQLite 存储等过时状态。
- GitHub 实时查询：本次文档提交前功能分支与本地均为 545de9442ab296e85d439f1af73626779c7b4373，main 为 efc6dce05ca785a496b97649cb3b7331770b5751；功能分支相对 main 为 behind 0 / ahead 47。之前的提交已经在远端功能分支，不是未 push；此次不合并 main。
- TLS 排查：默认 CA 在当前执行环境报 issuer 错误，使用 dora CA 验证 GitHub 成功，宿主默认 TLS 亦正常；不修改系统信任库。仅设置当前仓库 GitHub URL 的 sslCAInfo 与 sslVerify=true；测试用强制代理设置已撤销，保持其他访问不变。
- 普通 git ls-remote 和 push --dry-run 在宿主执行均成功；dry-run 返回 Everything up-to-date。未关闭证书校验。后续提交同步以实时远端 SHA 验证。
- 本轮仅更新文档和本地 Git 连接配置；不改前后端代码，不重启服务，不重复跑研究任务。检查范围为文档差异和 Git 同步。
