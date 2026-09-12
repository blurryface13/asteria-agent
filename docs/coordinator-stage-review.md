# Coordinator 阶段复核与实验开发入口

2026-09-12 · Codex（GPT-5）

## 结论

以下保留 `6823597e` 的审计快照；收口实现已推进，当前契约见 spec §22.7，真实运行和验证见 DEVELOPMENT_LOG.md 的 Coordinator 收口节点。不要把下文历史缺陷误作最新状态，也不要把一次成功运行当作全面能力成绩。

复核基线为 `6823597e`。科研运行时和后台持久化已有可用基础，普通请求首轮分流也有效，但 Coordinator 尚未达到新旧会话统一协调的完整交付边界。本轮只检查、复测并记录，不修改业务代码、不重启服务、不启动远程实验。

## 实际检查

- dora：`test_scientific_intent.py`、`test_autonomous_review.py`、`test_workspace_contract.py` 共 22 项通过，6 项依赖弃用警告。包含独立研究循环、主 Agent 委派、共享证据及受约束重规划；这些是受控测试，不是开放域真实模型成绩。
- 开启隔离 PostgreSQL schema 的 `test_durable_runs.py`，3 项通过。只创建并清理测试自身 schema，不修改业务数据。
- 前端 3023 首页、后端 8018 Skill API 均 HTTP 200；实际打开历史 Chat 和研究报告，无本次新出现的 SSR 500。没有调整端口、依赖、dora、代理或缓存。
- 历史 Chat `69baad11-b0f9-40df-bc53-e93a3543e0fa` 深链接能恢复“设计测试用例”；查询 latest Run 返回 null，首轮确实未创建研究任务。
- 在该页面只提交一次“把你刚才给出的改写结果翻译成英文，只输出译文。”，系统却创建新对话 `dd950b46-fef6-4cc4-a69b-8ec8b371bfb9`，回答要求重新提供原文。新对话 latest Run 也为 null：分流正确，但上下文与会话接续失败。保留此记录作为回归样例。
- 历史研究 Run `3726b79dd71c4a2ba73bcd9fd2d1d683` 仍为 completed，43 条事件、13 个产物索引、9 次模型调用/34,495 tokens。数据库口径：排队 0.718 秒、执行 66.514 秒（其中人工等待 28.378 秒）；67.232 秒是从创建到完成，不能再称为纯执行耗时。历史产物存在不代表本轮重新跑通了完整科研链路。
- 本地 HEAD 与 GitHub 实时功能分支 SHA 一致；工作树检查开始时干净。本轮没有 push 或合并。

## 优先收口

### P1：统一会话上下文，而不只是首句分类

`app/page.tsx:handleDisplayResult` 只发送当前 message；`handleCoordinatorChat` 每次创建新会话。后端虽然接受 messages，意图分析本身也只看当前句。现有 `handleChat` 则要求已有报告，不能承担普通 Chat 续聊。

下一笔应让 Coordinator 接受 conversation_id 和 request_id，服务端校验归属并读取历史；新建、续聊、报告追问都表达清晰的上下文来源，显式“新任务”才另建会话。既有报告问答能力保留，不把它误送去新调研。自然语言改策与“继续”必须关联当前任务状态；不以关键词代替语义判断。

### P1：消息有序持久化与提交生命周期

Chat 用户/助手消息通过 Promise.all 并发落库，数据库按 sequence_no 排序。历史 Chat 的消息接口实际返回 assistant、user，已经出现顺序错误；页面把初始问题单独提取展示，掩盖了这一点。仅刷新看到两句话不足以证明持久化正确。

先保证用户消息先入库、助手消息关联对应 turn；请求幂等，失败留状态，重试不重复收费/写入。当前 Coordinator 请求期间还未设置 processing/loading，发送按钮仍可点击。本轮没有通过连点制造额外费用，但代码缺少请求锁。只加 loading 不足以解决浏览器断开前尚未持久化的回答。

### P1：恢复已完成调研的活动展示

页面完成报告后会把 isInChatMode 设为 true，却又以 !isInChatMode 控制 showResearchActivity。真实历史报告页面能看到正文和 PDF 入口，但主 Agent/工具活动区消失。应以会话实际类型决定是否存在研究轨迹，以输入模式决定如何追问，两个状态不能复用。保持当前前端设计和折叠交互，不重画页面。

### P2：消除二次分类并补齐入口计量

`websocket_manager.py:run_agent` 将已识别的 general_research 转成 None，随后又命中意图分析条件。literature_review/experiment_design 不受此分支影响，但“worker 不重复识别”的文档表述过宽。显式区分“尚未识别”与“已经选择通用研究”，并覆盖无需再次调用模型的测试。

usage_sink 当前在 research worker 中设置；Coordinator 的分类和直接回答未接入同等持久化计量。研究 Run 的 usage 不能代表包含入口分类的用户端到端总费用。后续按 turn 保存真实 provider usage、路由决定与耗时；缺失费用不填零、不用字符估算。

### P2：网页公式与历史报告说明

历史精读正文仍显示 `$d_k$` 等原始数学标记。当前内联报告使用的 markdownHelper 只有 GFM/HTML，没有数学渲染；TeX/PDF 编译修复不等于网页公式修复。后续只调整渲染层并保留 HTML 消毒，不改变报告证据内容。

该历史正文还保留“不承诺已生成 PDF”的出版说明，尽管产物已生成。应在新报告回归中检查写作规范是否生效；不覆盖历史产物冒充当时已修复。

## 后续增量与完成条件

1. **Coordinator 收口**：上述 P1 与二次分类/入口用量。浏览器验证首轮普通问答 → 同一会话续聊 → 刷新 → 原报告追问；路由只执行一次，消息顺序正确，不误建研究 Run，报告轨迹保留。补一次通过新入口完成的研究正例；开放域委派另用有合理范围和预算的真实任务检查，不能用单篇任务 0 子 Agent 推断自主性失败或成功。
2. **服务器设置 E2a**：HostProfile、凭据引用、SSH host key 核验、连接诊断、WorkspaceGrant 与资源上限。连接成功不自动授予执行权限；日志/提示词不含密钥。先做设置与只读诊断，不直接开放任意远程 shell。
3. **受控实验 E2b/E3**：复用后台 Run/Job/Approval，增加 Attempt、隔离环境和 submit/inspect/cancel；首次以小型确定性实验跑完授权、提交、观察、结果归档。之后再增加 Agent 根据真实日志自主修正，超出授权重新询问。未知提交结果先按 job_id 对账，不自动重复训练。
4. **实验交付与评测**：保存代码/环境/参数/种子/指标/产物，区分建议、原文结果和实测结果。评测继续遵循 experiment-evaluation-roadmap：执行与评分独立，历史产物可补评；先明确分母与计量，再谈 P95/P99 和提升。

不新增长期后台子 Agent 作为自主性的形式门槛。保留现有 lead 动作选择、工具观察、委派、证据回流、充分性结算与有界改策，这些才是实验 Agent 应复用的基础。

## 既有记录勘误

- spec §22.5 的“worker 不重复调用意图模型”只对部分能力成立，通用研究仍需修正。
- 旧记录把消息 422 归因于 timestamp，现有 MessageCreateRequest 默认忽略额外字段，metadata 则必须是 dict；不要继续把 timestamp 归因当作已证实结论。后续遇到 422 应保留脱敏后的 validation detail。
- 首轮 Chat 恢复可用不等于多轮协调完成；现将二者拆开记录，不删除旧测试与失败样例。
