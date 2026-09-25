# 本地三层测试与评测：基线及下一步（2026-09-26）

本页区分「已实测」「尚未实测」和「官方 Benchmark」。被测代码为 Asteria `691b70d`；TestLab 为 `cae821e`。本地 API `127.0.0.1:8018`，测试时没有重启正在使用的服务。评测产物可能包含真实请求，不上传原始 Run、凭据或用户资料。

## 1. 传统自动化测试与性能

已实测：

| 范围 | 结果 | 结论边界 |
| --- | --- | --- |
| Asteria 全量离线 pytest | 388 passed、5 skipped | 跳过项不算通过；不是在线科研任务验收 |
| TestLab 后端 pytest | 16 passed | 包含对当前 Asteria API 的只读 Requests 冒烟 |
| Postman Collection 经 Newman 重放 | 6 requests、11 assertions、0 failures | 只读/未认证合同验证；不涵盖登录后业务链路 |
| JMeter 本机阶梯试跑 | 5 线程 50 请求、10 线程 100 请求，均 0 错误；10 线程均值 3.82 ms、P95 6 ms、P99 12 ms | 只请求 `/openapi.json` 与 Agent Discovery；**不能**推出 10 人同时提交科研任务的容量 |

JMeter 10 线程原始 JTL：`/tmp/asteria-local-eval.8nX51q/readonly-10u.jtl`（临时目录，重启/清理后不保证存在）。复现见 TestLab 的 `performance/asteria-readonly.jmx` 和 `docs/TRADITIONAL_TEST_BASELINE.md`。

下一步需要独立测试账号及隔离项目，覆盖登录、项目/会话、任务提交、状态轮询、取消与授权下载。先以 pytest/Requests 做正向、重复请求、异常和数据隔离断言；再让 JMeter 对**认证后状态查询/轮询**按 1/5/10 用户阶梯负载，记录 P95/P99、错误分类及数据库/worker 指标。真实模型任务只做受预算限制的小样本排队/完成时间，不把压 API 解释成模型吞吐。每个问题按「复现请求→根因→修复→同用例回归」留证。

## 2. Agent 用量、质量与节省 Token 的回归

已实测：`scripts/evaluate-orchestrator.py --live` 使用固定的**虚构领域材料**，4/4 路由/协作样例通过，18 次有用量的模型调用（上限 20）；这是入口协作冒烟，**不是**真实科研报告质量评测。结果在 `outputs/orchestrator-eval-6088097126/summary.json`（本地忽略目录）。用量：逻辑输入 22,687、输出 5,065、缓存读取输入 12,544；18 次调用全部带阶段及缓存字段。阶段包括 `intent_router`、`general_chat`、`company_research`、`financial_research`、`orchestrator_compose`。缓存读取占逻辑输入约 55.29%，**不是**节省 55.29% Token 或成本。新统计脚本另外给出非缓存读取输入 10,143；没有价格表、完整报告任务和 A/B 对照，不能据此报节省金额。

旧成功长任务 `outputs/acceptance_f999c8db7b` 有大量真实用量，但没有阶段标签；不可倒推 Lead/Writer/CitationAgent 的分摊。新阶段标签的完整学术 Run 尚需单独执行。

建议用下面的可复现实验建立求职中的优化故事：

1. 固定 3–5 条有代表性的请求（概念问答、单领域调研、复杂综述），固定代码 SHA、模型、检索范围/资料快照、并发和最大行动轮次。每条保留请求 hash、运行配置、Run ID、成功/失败及报告质量核验。
2. 先跑原版基线，再**一次只改一个点**，优先检查重复证据被多次送入 Lead/Writer/CitationAgent；可实验「按证据 ID 去重并保留来源定位」或稳定系统前缀。不要用语义相似的问题直接复用旧报告。DeepSeek 前缀缓存已由供应商提供，单独的缓存命中率提高不等于逻辑 Token 减少。
3. 同请求分别测冷/热运行，各至少 3 次；记录各阶段调用数、逻辑输入、非缓存读取输入、输出、缓存读取、耗时、失败重试次数；有可核实计费规则时再换算费用。质量门槛是任务成功、必要内容覆盖和正文引用可核验，不允许靠删证据或缩短报告造出“节省”。
4. 优化成立的表达必须包含基线、对照、样本数和质量结果，例如「在 N 条固定科研任务上，优化后每任务逻辑输入中位数下降 X%，引用核验通过率未下降」。**X/N 尚无实测，不写入简历。**

本地只读用量复现：

```bash
python scripts/report_token_usage.py outputs/acceptance_f999c8db7b/events.jsonl
jq -c '.usage[] | . + {type:"usage"}' outputs/orchestrator-eval-6088097126/summary.json | python scripts/report_token_usage.py /dev/stdin
```

## 3. AstaBench（独立官方任务）

先选与科研问答相近的 ScholarQA 开发任务 `astabench/sqa_dev`，不从全套或高内存 Coding/E2E 开始。AstaBench 基于 InspectAI；官方说明文学任务的 `state.tools` 带语料/时间限制，Agent 必须保留任务工具约束及模型用量日志。我们的 Markdown 报告不能直接视作 ScholarQA 所需的结构化答案；先做输出/工具/usage Adapter 的替身契约测试，再跑 `--limit 1` 的官方开发样例。使用 Asteria 自有网页检索若越过约束，只能按官方 Custom 工具分类，不能包装成 Standard 结果。项目内四维 LLM-as-Judge 与 AstaBench 官方评分分别报告。

当前**尚未安装/运行官方任务，没有 AstaBench 分数**。单独创建 Python ≥3.11 的评测环境，不升级现有 Asteria Python 3.10 服务。官方文学检索工具需要 `ASTA_TOOL_KEY`，数据集需要用户在 Hugging Face 接受许可后的 `HF_TOKEN`；某些评分还需要相应模型供应商密钥。密钥只放隔离环境变量，不写进仓库。Mac 当前剩余空间约 6.9 GiB；先做 adapter/单题的容量预检，避免全套容器和数据集占满正在工作的机器；必要时移至实验室服务器。

官方文档：[AstaBench README](https://github.com/allenai/asta-bench)、[Asta MCP 申请](https://allenai.org/asta/resources/mcp)、[数据集许可](https://huggingface.co/datasets/allenai/asta-bench)。

顺序：完成第 1 层业务链路 → 第 2 层取得新长任务阶段基线与 A/B → 第 3 层接入一条官方样例。三层的数字不能互相替代。
