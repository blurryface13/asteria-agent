# Agent 用量与长任务可靠性：可复现的面试 Story（2026-09-26）

以下只陈述本机已验证的能力。报告阶段重放不是用户登录后发起的新端到端任务；数据库故障注入不是在 Windows 生产机真的杀死 Worker。本轮开启隔离 PostgreSQL 合同测试的全量 pytest 为 **397 passed**。

## Story 1：用量归因 → 精确去重试验 → 质量回归 → 暂缓上线

**问题。** 长科研任务中多个 Search 子 Agent 会读到相同论文段落。原样汇总给 Writer 时，第一份保存资料含 384 段、其中 152 段完全重复；第二份不同主题的保存资料含 336 段、其中 71 段完全重复。直接缩减 Writer 上下文有机会节省模型逻辑输入，但不能删除不同原文、限定条件或子 Agent 阅读归属。

**改动。** `ASTERIA_WRITER_EVIDENCE_DEDUP=1` 只对 Writer 的临时输入做完全相同段落去重，附上其他阅读者归属；证据账本及 CitationAgent 输入不变。默认关闭，可回滚。用 `scripts/audit_writer_evidence.py` 离线预估输入大小，用 `scripts/replay-research-report.py` 固定保存的检索资料，分别重放 Writer→CitationAgent→PDF，并记录真实供应商用量及阶段标签。

| 保存任务与结果 | 基线 Writer 输入 | 去重 Writer 输入 | 交付质量门槛 |
| --- | ---: | ---: | --- |
| 开放词汇 3DGS 长综述 | 143,185 | 108,233（本次 -24.4%） | 两版均生成 PDF，CitationAgent `completed`；人工抽查两版均有方法名/论文链接错配 |
| 长任务 Agent 架构综述 | 104,169 | 90,455（本次 -13.2%） | 基线生成 PDF，但正文 2,867 长度单位、短于用户要求的约 3,500–5,000；去重版经过定向修稿后仍有 2 处引文映射缺口，**未交付** |

第一份基线为 `outputs/report_replay/review_2215dd9d6c20445ba0e954bff3c8f49c`，去重为 `outputs/report_replay/review_eea6ee15d15d4918830162dae27e0d98`。第二份基线为 `outputs/report_replay/review_f71b7850f4f84498b9973a39bf4c1eaf`，去重失败记录为 `outputs/report_replay/review_f559769524f94cf8958e568c1689690d`。这些目录均在 `.gitignore` 中，不上传原文或模型输出。

**验收与结论。** 两份资料都测到 Writer 阶段逻辑输入下降，但第二份未通过交付门槛；不能给出“平均节省 X% 且质量不下降”，也不能把未完成运行的总 Token 和已完成运行直接比较。供应商前缀缓存命中差异很大，账单费用亦不可由这两对样本推断。开关保持**关闭**。面试可讲“发现重复、做可回滚单变量实验、测出局部收益、质量回归发现反例并暂缓上线”，不可讲“线上成本下降 X%”。下一轮若继续此候选，先处理明显引用错配，再增加不同主题的多次冷/热交叉运行。

复现这两对试验（会产生真实模型费用；`--max-model-calls` 是每次重放的保护上限）：

```bash
python scripts/replay-research-report.py outputs/review_1e8293741f5847fa99519cb3bf5a119d --max-model-calls 20
python scripts/replay-research-report.py outputs/review_1e8293741f5847fa99519cb3bf5a119d --writer-evidence-dedup --max-model-calls 20
python scripts/replay-research-report.py outputs/review_e4cdb4537afd485b88d66e4a67b1c418 --max-model-calls 24
python scripts/replay-research-report.py outputs/review_e4cdb4537afd485b88d66e4a67b1c418 --writer-evidence-dedup --max-model-calls 24
```

## Story 2：后台任务断连与 Worker 失联——先保证不重复执行

**问题。** 实验室多人可提交耗时研究任务。浏览器刷新、API 断连或 Worker 失联时，不能把旧事件写入新任务，也不能为同一请求重复调用付费模型。

**设计与测试。** PostgreSQL 保存 Run/Job/Event，`request_id` 幂等；事件按 Run 序号追加、观察端按游标补拉；Worker 租约与所有权检查阻止过期进程写入。隔离 schema 的合同测试中，5 个并发同键提交只生成 1 个 Run；相同键、不同内容被拒；20 条并发事件序号连续。故障注入使 Worker 租约过期后，旧 Worker 写入被拒，回收将任务置为 `interrupted`，新 Worker **不自动重领**，防止未知外部工具动作重复发生。取消中的协程会终止，空报告不能被标为完成。

**结果与边界。** 本机隔离 PostgreSQL 合同测试 `3 passed`。它验证数据库状态机和重复执行保护；尚未验证 Windows 主机真实进程被杀后的逐动作自动续跑。当前 Agent Loop **没有**通用的动作级恢复 checkpoint，不得说“崩溃后无缝续跑”。

```bash
ASTERIA_RUNS_DB_TESTS=1 /Users/dora/miniconda3/envs/dora/bin/python -m pytest -q tests/test_durable_runs.py
```

## Story 3：引文阶段失败后的定向交付恢复

**问题。** 一份研究已完成资料检索和 Writer 初稿，但 CitationAgent 留下 1 处证据缺口；若从用户请求重新开始，会重复检索、写作并增加费用。

**恢复与验收。** 保存初稿、已读证据、图表与已审核正文位置；`scripts/recover-research-delivery.py --resume-draft` 从引文阶段修复并重新发布，原失败 Run 不修改。现存案例中恢复用了 4 次模型调用，缺口从 1 降到 0，生成 PDF；独立的只读审计脚本验证来源归属、原失败状态、恢复完成状态和 PDF 存在。

```bash
python scripts/audit_recovery_story.py \
  outputs/review_1a8e2232b7924b85a79bf2e33a4f5c77 \
  outputs/delivery_recovery/review_c84bb2136ac9457daeca2c8d0a396e5f
```

**边界。** 这是**已有证据的离线交付恢复**，不是所有中断阶段都能自动恢复，也不是一条新的认证端到端成功 Run。下一步若要做真正的长任务无缝恢复，应先为无副作用的阶段建立原子 checkpoint，再为外部工具设计操作 ID、结果查询和幂等语义；不应直接自动重放未知结果的工具调用。
