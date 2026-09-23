# EchoMind 骨架对齐

日期：2026-09-22。目标：实际入口与执行代码对齐，不只更换架构描述。

## 不变的产品边界

- 入口统一为 `AgentOrchestrator`：融合意图识别、澄清、主辅角色选择、执行与汇总。入口不是科研 Lead。
- 工作角色复用 `BaseAgent` 的有界“模型决策 → 工具校验/执行 → 观察 → 再决策”循环；角色契约、Skill、工具范围决定差异。
- Lead 是科研支路的增强角色，负责不同子目标的分工和并行回收，不再次充当用户入口。
- Reviewer 在 Lead 尝试交付时独立验收，返回缺口，由 Lead 决定下一步；移除每三次动作自动审查。预算耗尽时可做最后一次验收。
- 不强制每个任务依次经过调研、代码、审核；Coding 可以直接读论文，也可以针对具体障碍请求研究帮助。
- 保留已有证据校验、人工文件变更审批、身份隔离、取消和预算约束；不增加任意 Shell 或实验执行权限。

## 实施与验收

1. 提取共享角色契约和 BaseAgent 执行驱动，接入领域、代码和 Lead/研究子角色；验证状态隔离、白名单、最后一轮交付和取消。
2. 提取 AgentOrchestrator 的 Request / RoutingDecision / 执行注册表；HTTP 层只装配已鉴权上下文、业务适配器和持久化。提供 `/api/orchestrator`，旧 `/api/coordinator` 与数据库表/请求字段保留兼容。
3. 只对只读普通领域角色开放可选主辅并行；科研复合任务仍由 Lead 按不同子目标派工，不能把同一代码写请求重复执行。
4. 单独建 Reviewer 角色边界，取消周期性审查，验证交付不通过后返回原 Lead 循环。
5. 核查遗留固定流程的实际调用入口，迁移可兼容的支路并明确剩余边界，不把旧路径留存误称为全量对齐。
6. 运行原有回归、新架构测试和有界真实模型探针；记录脚本替身与真实模型结果。服务无活跃任务才重载。

## 参考与适配

本地 EchoMind：`agents/agent_orchestrator.py` 中的 AgentProfile、Request、RoutingDecision、BaseAgent、AgentOrchestrator 和 ResponseComposer。
沿用上述职责分层；Asteria 保留当前多供应商模型适配及结构化 JSON 工具动作，不整体搬入 Anthropic SDK。
原来的持久化 Run、用户数据及科研产物不迁移/删除。其他未提交的实验室登录、共享知识库与前端改动不纳入本轮提交。

## 完成记录

### 代码映射

| EchoMind 概念 | Asteria 当前实现 | 责任与差异 |
| --- | --- | --- |
| AgentOrchestrator / Request / RoutingDecision | `agentic/agent_orchestrator.py` | 融合识别、澄清、主辅角色选择、执行注册表、汇总；不承担科研派工 |
| AgentProfile / BaseAgent | `agentic/base_agent.py` | 共用有界决策驱动、解析、角色白名单、最后一轮交付；保留各工具的观察和权限适配 |
| 普通角色配置 | `agentic/capabilities.py`、`backend/server/specialists.py` | 通用对话、学习、投稿、企业与财务；同一循环，不同职责/Skill/工具范围 |
| 可选多角色并行与汇总 | AgentOrchestrator.run_parallel | 同一原始请求交给只读领域角色，各有独立上下文；入口汇总，不重复执行代码写请求 |
| 科研增强 Lead | `agentic/autonomous.py`、`collaboration.py` | 自主选择研究或派发不同子目标，检查覆盖/区分度，as_completed 提前保存阶段结果 |
| 独立 Reviewer | `agentic/reviewer.py` | 交付时验收依据与代码产物，缺口交回 Lead；不路由入口请求，不每三次动作强制审查 |
| Coding | `agentic/coding.py` | 使用 BaseAgent；直接读论文或定向求助，回到原任务继续；保留已有证据与提案保护 |

HTTP 适配层 `backend/server/orchestrator_handlers.py` 注入已鉴权工具和持久化研究提交。
新客户端访问 `/api/orchestrator`；旧 `/api/coordinator`、`coordinator_turns` 表、`coordinator_capability` 请求字段仅为兼容保留，不迁移历史数据。

### 哪些仍不是 EchoMind 原样实现

- 当前模型适配仍用结构化 JSON 动作，不是假称已经换成 EchoMind 的 Anthropic 原生 tool_use 协议。
- 知识库问答保留“权限校验 → 检索 → 基于片段回答”的确定性专用适配器；Writer 保留有界报告生成/格式修复。它们没有为增加角色数量而强行套无限工具循环。
- 文献调研与实验设计现共用科研自主运行时，后者加载实验 Skill 并检查基线、数据、指标、环境、验收等交付项。旧实验设计固定轮次流程已退出活动入口。
- 普通公开资料研究使用领域 BaseAgent，自主调用有界公开检索并交付来源；当前依据是检索摘要，不声称通读网页。域名限制在工具返回处强制过滤。此角色暂不接指定网页全文/本地文件请求，明确报错而非悄悄丢弃来源限制；文档问答走知识库。
- `multi_agents/` 的旧 LangGraph 工作流和 `agentic/runtime.py` 的历史 Coordinator 留作旧接口/重放兼容，不是新 AgentOrchestrator 的入口骨架。后者已无生产调用方。
- 并行子任务仍按批次回收，阶段结果先展示不等于 Lead 随到随派新一批；不是通用 DAG 调度器。
- 不新增宿主 Shell、实验执行、自动应用修改或服务器调度。

### 回归与真实模型验收

使用现有 dora Python 环境与 Node 22；数据库测试使用隔离临时 schema，不改用户项目数据。

```bash
python -m pytest tests -q
ASTERIA_RUNS_DB_TESTS=1 python -m pytest tests/test_lab_release.py tests/test_durable_runs.py tests/test_coordinator_turns.py -q
python scripts/evaluate-orchestrator.py --live
python scripts/evaluate-collaboration.py --live --case planning
python scripts/compare-coding-research.py --live --native-policy
```

- 数据库/身份隔离、持久化、取消专项：14 通过（与全量重叠，不叠加宣称数量）。前端 TypeScript 检查与 8 条组件/历史/Markdown 测试通过。
- 真实模型 Lead 分工探针：2 次模型调用，一次分工即通过覆盖和独立语义检查。`outputs/collaboration-eval-b375beb452/`；只验证规划质量，没有冒充完整在线调研。
- 真实 Coding 对照：直接阅读 4 次模型调用 / 10.905 秒；研究求助 7 次 / 19.929 秒，其中求助等待 6.869 秒。两者均取得冻结材料并产出语法有效的 diff，未写文件、未运行代码。`outputs/coding-research-comparison-8a4d71556f/`；单例耗时不作为性能收益或成功率指标。
- 初次入口探针 3/3 通过（普通问答、科研路由、预分类领域并行），记录 `outputs/orchestrator-eval-d7fb21652e/`。
- 扩展自动主辅路由探针发现 badcase：路由正确，但角色误以为要自行协调其他角色；两个角色都澄清时汇总仍标 completed。保留原失败记录 `outputs/orchestrator-eval-69e78c31c7/`。修复：每个角色注入 assigned_role / participating_roles / composition_owner，明确入口负责汇总；clarify/incomplete 不再等同 completed。缺少材料时澄清本身是合理行为，不强制检索或伪造结论。

最终回归计数、badcase 复测和服务重载状态待最后验收补记。
