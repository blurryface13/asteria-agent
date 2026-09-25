# 学术／金融路线与 Token 测试基线（2026-09-25）

本页记录**已经执行的检查**与下一轮的验收边界；不能把替身检索、只读接口压测或旧版产物描述为新部署的完整容量测试。

## 本轮结果

| 路线 | 已验证 | 尚未据此证明 |
| --- | --- | --- |
| 学术长任务 | `outputs/acceptance_f999c8db7b/result.json` 为 `completed`，执行约 615 秒；28 项产物中含 PDF、CitationAgent 核验记录，9 项经过认证下载验收。该 Run 有 88 次有用量的模型调用。 | 新增阶段标签后的完整 Run 尚未重跑；不能用旧产物证明新版本的阶段统计或 10 人并发。 |
| 金融／企业领域路由 | `scripts/evaluate-orchestrator.py --live`：4/4 场景通过，包括金融与企业角色并行及回复汇总；领域检索用固定测试资料。另一次 `financial_research` 真模型＋真实公开检索冒烟返回 `answer`，发生 2 次检索、共 5 条搜索结果。 | 金融路线目前是有界领域工具循环，以搜索摘要作材料；不是学术链路的 Lead／Writer／CitationAgent 长报告，也没有逐份原始财报阅读与财经事实人工核验。 |
| 性能只读基线 | Agent TestLab 的 `asteria-readonly.jmx` 对本机 `:8018` 运行 5 线程、50 次请求；错误 0、平均 4.4ms、P95 9ms、最大 36ms。JTL：`/tmp/asteria-jmeter.KEJ0N2/results.jtl`。 | 仅 OpenAPI／Agent Discovery 两个公开接口；不能推出登录、任务提交、状态轮询、10 人科研任务或模型吞吐量。 |

金融冒烟的具体 BadCase：明确要求“官方资料”，检索返回结果中仍混入 Wikipedia，且来源清单包含全部搜索结果。后续应测试来源筛选和“已读原文／仅看摘要”的标注；未解决前不将其称为可信金融深度报告。

## 用量记录现状

- 新调用的用量事件带 `stage`，包括 `intent_router`、领域角色、`research_lead`、`research_subagent`、`coding_subagent`、`data_analyst`、`writer`、`citation_agent`、`orchestrator_compose`；保留模型、供应商、尝试次数、真实用量与调用耗时。并行子任务用 ContextVar 隔离标签。
- `python scripts/report_token_usage.py outputs/acceptance_f999c8db7b/events.jsonl` 可按阶段汇总。旧 Run 只有 `unclassified`，不能凭现有事件反推各阶段。该旧成功 Run 的输入 2,777,666 Token、输出 65,786 Token，缓存读取 626,816 Token（输入中约 22.57%）；这是一个样本，不是平均值、成本估计或新代码效果。
- Claude Prompt Caching 的可复用原则是**稳定前缀在前、动态任务与观察结果在后、按真实缓存读取量验收**；当前 DeepSeek 已默认缓存相同前缀，不能直接套 Claude 的 `cache_control` 参数。缓存读取仍计入逻辑输入和上下文窗口，不等于零 Token。

## 下一轮分层测试

1. 功能：学术路线核验登录→路由→审批→互补派发→证据／图表→Writer→CitationAgent→PDF／授权下载；金融路线分别核验概念问答、真实公开检索、来源质量与失败降级。不以“意图选对”代替任务成功。
2. 用量：固定模型版本、资料范围和测试请求，对 3–5 个样本记录每阶段调用数、输入／输出、缓存读取、耗时、失败尝试；比较同一稳定上下文下的冷／热调用。先记录，再决定是否调整前缀或上下文压缩；不直接返回旧报告。
3. 性能：Agent TestLab 另建带认证的**任务提交＋状态轮询**场景，分开测控制面和模型任务。先测 1／5／10 虚拟用户的接口延迟、P95、错误与 429，再以少量真实模型任务观察排队与完成时间；真实模型压测设预算与取消条件。JMeter 公开只读结果不算这一项通过。
4. 回归：每个发现的 BadCase 保留原请求、可重现的环境与来源范围、修复前后轨迹。正式结果要区分自动通过、人工复核和未验证。

## Docker 决策

建议**下一阶段做 Docker Compose 交付**，而不是把当前 Mac 的 `.env`、数据库和 `outputs` 打成单一镜像。目标机是 Windows＋4060 时，用 WSL2 的 Linux 容器；API、独立研究 Worker、Next 前端、PostgreSQL、Redis 分服务，数据库、工作区、Chroma、论文索引与产物用持久卷。Ollama 可先运行在宿主机，容器通过可配置地址访问；GPU 只在实际需要容器内推理时再启用。完整学术链路还依赖 modular-rag-engine、bge-m3、XeLaTeX/CMap，这些必须纳入预检，不能仅凭 `docker compose up` 就宣布可用。

Compose 会让固定版本部署、分服务更新和回归环境重建更方便；**不会**自动解决迁移、密钥、GPU 驱动、RAG 外部依赖和长任务中断。先在本机隔离 Compose 环境跑通真实登录及一条受控学术／金融任务，再交付 Windows 主机，不直接替换现有可用服务。
