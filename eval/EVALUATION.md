# Agent Evaluation Loop

这是一套运行在 Asteria 科研 Agent 上的本地、可复现评测链路。它借鉴 GoodQuestion 的产品载体，但不要求复刻其全部字段：核心对象是评测任务、种子题目、维度、Trace、BadCase、生成样本和回归报告。

## 链路

```text
线上/本地 Trace(JSONL)
        ↓
TraceIngestor → Agent/LLM/Tool 树
        ↓
BadCaseAnalyzer → 失败类型、失败 span、证据、维度建议
        ↓
trace_to_seed → 种子题库
        ↓
TaskGenerator → 按维度扩展 + 严格对齐检查 + 专家复核入口
        ↓
EvaluationRunner → 重复运行、工具/大纲/引用/里程碑/延迟评分
        ↓
报告 → 失败轨迹再次回流
```

## GoodQuestion 对应关系

| GoodQuestion 载体 | Asteria 初版 |
| --- | --- |
| 应用资产/Know-How | `EvalTask.metadata`、`GenerationConfig.know_how_documents`、`inline_know_how` |
| 29 个风险/能力维度 | `DimensionCatalog` |
| BadCase 日志 Trace 树 | `TraceEnvelope` + `TraceSpan` |
| 种子题库 | `SeedCase` |
| 泛化题库 | `GeneratedCase` |
| 专家质检 | `quality_status`、`quality_note` 和后续 API 页面 |
| 任务预览 | `preview_task()` |

## 使用

```bash
python scripts/evaluation_cli.py import-traces eval/samples/production_trace.jsonl --batch-id demo
python scripts/evaluation_cli.py analyze demo-trace-001
```

`ASTERIA_EVAL_DATA_DIR` 可将 JSONL 数据目录切换到独立实验目录。默认写入 `outputs/evaluation/`。真实模型执行必须通过 `EvaluationRunner(executor=...)` 注入，避免离线预览误触发外部调用。

## 指标边界

大纲覆盖、引用数量、工具 precision/recall、里程碑完成度和延迟可以确定性计算；引用支撑率目前提供“参考 URL 命中”的启发式结果，真正的语义支撑判断应通过单独的 judge adapter 注入，并和启发式值分开记录。
