# 本地三层测试与评测：基线及下一步（2026-09-26）

本页区分「已实测」「尚未实测」和「官方 Benchmark」。第一层传统测试基线来自 Asteria `691b70d`、TestLab `cae821e`；Writer 去重及报告阶段重放在后续本地改动上执行。本地 API `127.0.0.1:8018`，传统基线测试时没有重启正在使用的服务。评测产物可能包含真实请求，不上传原始 Run、凭据或用户资料。

## 1. 传统自动化测试与性能

已实测：

| 范围 | 结果 | 结论边界 |
| --- | --- | --- |
| Asteria 全量离线 pytest | 基线 388 passed、5 skipped；Writer 改动后 391 passed、5 skipped | 跳过项不算通过；不是在线科研任务验收 |
| TestLab 后端 pytest | 16 passed | 包含对当前 Asteria API 的只读 Requests 冒烟 |
| Postman Collection 经 Newman 重放 | 6 requests、11 assertions、0 failures | 只读/未认证合同验证；不涵盖登录后业务链路 |
| JMeter 本机阶梯试跑 | 5 线程 50 请求、10 线程 100 请求，均 0 错误；10 线程均值 3.82 ms、P95 6 ms、P99 12 ms | 只请求 `/openapi.json` 与 Agent Discovery；**不能**推出 10 人同时提交科研任务的容量 |

JMeter 10 线程原始 JTL：`/tmp/asteria-local-eval.8nX51q/readonly-10u.jtl`（临时目录，重启/清理后不保证存在）。复现见 TestLab 的 `performance/asteria-readonly.jmx` 和 `docs/TRADITIONAL_TEST_BASELINE.md`。

下一步需要独立测试账号及隔离项目，覆盖登录、项目/会话、任务提交、状态轮询、取消与授权下载。先以 pytest/Requests 做正向、重复请求、异常和数据隔离断言；再让 JMeter 对**认证后状态查询/轮询**按 1/5/10 用户阶梯负载，记录 P95/P99、错误分类及数据库/worker 指标。真实模型任务只做受预算限制的小样本排队/完成时间，不把压 API 解释成模型吞吐。每个问题按「复现请求→根因→修复→同用例回归」留证。

## 2. Agent 用量、质量与节省 Token 的回归

已实测：`scripts/evaluate-orchestrator.py --live` 使用固定的**虚构领域材料**，4/4 路由/协作样例通过，18 次有用量的模型调用（上限 20）；这是入口协作冒烟，**不是**真实科研报告质量评测。结果在 `outputs/orchestrator-eval-6088097126/summary.json`（本地忽略目录）。用量：逻辑输入 22,687、输出 5,065、缓存读取输入 12,544；18 次调用全部带阶段及缓存字段。阶段包括 `intent_router`、`general_chat`、`company_research`、`financial_research`、`orchestrator_compose`。缓存读取占逻辑输入约 55.29%，**不是**节省 55.29% Token 或成本。新统计脚本另外给出非缓存读取输入 10,143；没有价格表、完整报告任务和 A/B 对照，不能据此报节省金额。

旧成功长任务 `outputs/acceptance_f999c8db7b` 有大量真实用量，但没有阶段标签；不可倒推 Lead/Writer/CitationAgent 的分摊。新阶段标签的完整学术 Run 尚需单独执行。

本轮又定位到一个可做 A/B 的具体点：在一份已完成长任务的 `evidence.json` 中，Writer 输入候选的 384 段证据只有 232 段内容不重复。保留所有不同 Agent 的阅读归属后，证据 JSON 视图从 406,676 字符缩至 272,520 字符（约 33.0%）。另一份长任务从 282/187 段、313,098 字符缩至 232,876 字符（约 25.6%）。这只是 **Writer 证据字段**的离线体积，不是整次任务或供应商 Token 的实测降幅。复现：`python scripts/audit_writer_evidence.py outputs/review_1e8293741f5847fa99519cb3bf5a119d/evidence.json`。

已加入可选 `ASTERIA_WRITER_EVIDENCE_DEDUP=1`：只移除完全相同的证据段，并在保留段上记录其他子 Agent 的阅读归属；原始账本和 CitationAgent 输入不变。默认**关闭**，待多任务质量 A/B 通过后才考虑打开。Writer 运行事件会记录 `evidence_view` 模式、前后段数与字符数，不记录原文。单元测试验证不同原文/限定条件不会合并。

### 一次真实报告阶段的配对试跑（不是端到端节省结论）

固定一份已完成的开放词汇 3DGS 长任务资料快照 `outputs/review_1e8293741f5847fa99519cb3bf5a119d`，分别重放 Writer→CitationAgent→PDF，未重新检索；两次均完成 CitationAgent、生成 PDF。命令：

```bash
python scripts/replay-research-report.py outputs/review_1e8293741f5847fa99519cb3bf5a119d --max-model-calls 20
python scripts/replay-research-report.py outputs/review_1e8293741f5847fa99519cb3bf5a119d --writer-evidence-dedup --max-model-calls 20
```

| 指标 | 原始证据版 | Writer 精确去重版 | 解读 |
| --- | ---: | ---: | --- |
| Writer 逻辑输入 Token | 143,185 | 108,233 | 本次减少 24.4%；但只是一对模型采样 |
| 全报告阶段逻辑输入 Token | 1,075,262 | 890,826 | 本次少 17.2%，**不可全归因于去重**：报告内容和 CitationAgent 调用次数也变了 |
| CitationAgent 模型调用 | 16 | 13 | 输出变化引起批次/补读变化，非受控的 Citation 优化 |
| 正文长度单位 | 5,457 | 4,289 | 两版均有三项实验假设；去重版更接近“约 4000 字”，但信息覆盖仍需人工判定 |
| 参考文献/图 | 21 篇／2 张 | 20 篇／2 张 | 均超过任务的 10 篇要求；数量不代表引用准确 |
| CitationAgent 审核 | completed、0 gaps | completed、0 gaps | 只代表当前核对器未报缺口，**不是事实正确保证** |

产物：`outputs/report_replay/review_2215dd9d6c20445ba0e954bff3c8f49c`（基线）与 `outputs/report_replay/review_eea6ee15d15d4918830162dae27e0d98`（去重）。最初 12 次调用上限的基线重放在引文核对中途停止，不计为成功样本；完整基线用了 18 次，故脚本默认上限改为 20。两次的 `usage-summary.json` 与 `citation-review.json` 均留在各自产物目录。

**质量门槛尚未通过。** 抽查发现两版正文表格都有论文名称—URL 错配；例如去重版把 LangSurf 行标到 `2412.02245`，而保存的该论文首页明确是 SparseLGS；LangSurf 的已读原文是 `2412.17635`。CitationAgent 的 `completed` 未识别此类元数据错配。另有顺序缓存干扰：基线 Writer 143,185 输入中 142,720 是供应商缓存命中（此前失败重放已热身），去重版 Writer 仅命中 31,360；因此**不能用这对样本推算账单降幅**。本轮结论是“找到并测出 Writer 重复上下文；质量核验暴露新的引文缺陷”，不是“已上线节省 Token”。开关保持关闭；后续先补文献名/URL 的确定性校验，再做多任务、冷/热顺序交叉对照。

第二份不同主题的长综述又做了同资料配对：基线 Writer 输入 104,169 Token 且完成 PDF；去重版 Writer 输入 90,455 Token，但 CitationAgent 修稿后仍剩 2 处引文映射缺口，未交付。故目前只有“两个样本的 Writer 局部输入下降”，**没有**“质量不下降的多任务 Token 节省”结论。完整实验记录及两个长任务可靠性 Story 见 [Agent 用量与长任务可靠性 Story](agent-usage-reliability-stories.md)。

建议用下面的可复现实验建立求职中的优化故事：

1. 固定 3–5 条有代表性的请求（概念问答、单领域调研、复杂综述），固定代码 SHA、模型、检索范围/资料快照、并发和最大行动轮次。每条保留请求 hash、运行配置、Run ID、成功/失败及报告质量核验。
2. 先以默认模式跑完整基线，再只打开 Writer 精确去重开关，用相同请求、检索资料快照与模型配置对照；不要同时改提示词、行动预算或 CitationAgent。不要用语义相似的问题直接复用旧报告。DeepSeek 前缀缓存已由供应商提供，单独的缓存命中率提高不等于逻辑 Token 减少。
3. 同请求分别测冷/热运行，各至少 3 次；记录各阶段调用数、逻辑输入、非缓存读取输入、输出、缓存读取、耗时、失败重试次数；有可核实计费规则时再换算费用。质量门槛是任务成功、必要内容覆盖和正文引用可核验，不允许靠删证据或缩短报告造出“节省”。
4. 优化成立的表达必须包含基线、对照、样本数和质量结果，例如「在 N 条固定科研任务上，优化后每任务逻辑输入中位数下降 X%，引用核验通过率未下降」。**X/N 尚无真实 A/B，不写入简历。** 因为模型输出可能影响后续流程，离线 JSON 缩小不能代替端到端回归。

本地只读用量复现：

```bash
python scripts/report_token_usage.py outputs/acceptance_f999c8db7b/events.jsonl
jq -c '.usage[] | . + {type:"usage"}' outputs/orchestrator-eval-6088097126/summary.json | python scripts/report_token_usage.py /dev/stdin
```

## 3. AstaBench（Windows 主机上的独立官方任务）

先选与科研问答相近的 ScholarQA 开发任务 `astabench/sqa_dev`，不从全套或高内存 Coding/E2E 开始。AstaBench 基于 InspectAI；官方说明文学任务的 `state.tools` 带语料/时间限制，Agent 必须保留任务工具约束及模型用量日志。我们的 Markdown 报告不能直接视作 ScholarQA 所需的结构化答案；先做输出/工具/usage Adapter 的替身契约测试，再跑 `--limit 1` 的官方开发样例。使用 Asteria 自有网页检索若越过约束，只能按官方 Custom 工具分类，不能包装成 Standard 结果。项目内四维 LLM-as-Judge 与 AstaBench 官方评分分别报告。

按用户决定，官方 Benchmark 在 Windows＋4060 主机运行，优先 WSL2/Docker 内的独立 Python ≥3.11 评测环境；不升级 Asteria Python 3.10 服务，也不占用 Mac 的运行盘。当前**尚未安装/运行官方任务，没有 AstaBench 分数**。先做 adapter/单题容量预检，切忌直接拉全套 Coding/E2E 镜像。官方文学检索工具需要 `ASTA_TOOL_KEY`，数据集需要用户在 Hugging Face 接受许可后的 `HF_TOKEN`；某些评分还需要相应模型供应商密钥。密钥只放隔离环境变量，不写进仓库。

官方文档：[AstaBench README](https://github.com/allenai/asta-bench)、[Asta MCP 申请](https://allenai.org/asta/resources/mcp)、[数据集许可](https://huggingface.co/datasets/allenai/asta-bench)。

顺序：完成第 1 层业务链路 → 第 2 层取得新长任务阶段基线与 A/B → 第 3 层接入一条官方样例。三层的数字不能互相替代。

## Anthropic 对齐后，真正值得做的增量

对照 [Anthropic Research 架构说明](https://www.anthropic.com/engineering/multi-agent-research-system)：Asteria 已有 Lead 按 aspect 委派、并行 Search 子 Agent、Run Memory、Writer 后 CitationAgent、工具轨迹；外层意图路由是本产品增加的入口，不必为了图一致再拆一个 Agent。仓库中的上游角色指导已按本地工具名绑定，并排除其固定调用配额；不能照搬与本项目不符的接口或预算。

1. **P0：交付与证据质量。** 长任务历史中发生过子 Agent 已读资料但结构化 `finish` 失败、CitationAgent 未保留原文适用范围的情况；本轮又实测出论文名称与 URL 错配能穿过 `completed`。先加入参考文献/表格标题与已读论文首页元数据的确定性核验，再以保存 Run 做「原文限定条件→子 Agent findings→Writer 句子→最终引文」抽样链路，验证失败分支仍能交付已有发现；比再增加角色更重要。
2. **P1：用量与质量共同优化。** 配对试跑已证实 Writer 精确去重能减少该样本的 Writer 逻辑输入，但尚未证明跨任务质量和费用收益；开关保持关闭。完整基线中 CitationAgent 16 次核对占 932,077 输入 Token，远高于 Writer 的 143,185；应先审计每批重复索引/证据上下文和缓存前缀，再考虑缩短核对上下文，确保逐段引文核验质量不下降。
3. **P1：真正的长任务恢复。** `working-memory.json` 和事件日志能供人检查，但当前尚不是进程异常后从精确节点自动续跑；Windows 部署与版本更新前，应验收 worker 中断、幂等恢复、审批/任务状态一致性。Anthropic 原文也将恢复与检查点视为生产可靠性问题。
4. **P2：慢分支体验。** 当前 Lead 按批等待，但前端可显示各路完成进展；Anthropic 同样承认同步批次会被慢分支拖住。先测首个可用发现、整批尾延迟和用户等待体验，再决定是否引入复杂的异步交接，不为“更 agentic”先重写调度器。

2026-08-13 的 [Anthropic 多 Agent 失败模式研究](https://www.anthropic.com/research/multiagent-systems)强调同质化、依赖协调与共享资源风险；本项目的相应验收点是委托目标重叠度、事实/限制的跨角色保留、共享工具预算，而非单纯扩大 Agent 数量。
