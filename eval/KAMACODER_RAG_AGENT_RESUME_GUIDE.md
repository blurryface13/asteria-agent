# RAG 与 Agent 项目：面试官关注点对照

来源整理：

- [RAG 项目简历写法](https://notes.kamacoder.com/jianli/llm/llm_6.html#rag项目-面试官到底想看什么)
- [Agent 项目简历写法](https://notes.kamacoder.com/jianli/llm/llm_7.html#agent项目-面试官到底想看什么)

这不是原文转录，而是结合 Asteria Agent 当前实现做的面试与简历检查清单。

## 一句话区分

| 项目部分 | 面试官真正想确认的事 | 当前项目的可验证证据 |
|---|---|---|
| RAG | 检索链路如何做决策、如何评估和调优 | bge-m3 dense + BM25 + RRF(k=60) + qwen3-rerank；336 篇论文、90 条 Golden Query 的 Hit@10 / Ragas Faithfulness |
| Agent | 多步任务怎样稳定执行、工具与状态怎样受控 | LangGraph StateGraph、章节并行、Human-in-the-loop、LangChain Tool / MCP、checkpoint、并发上限与 timeout |

不要把二者混成“做了 Agent + RAG”。前者的主叙事是**检索质量**，后者的主叙事是**任务完成与执行可靠性**。

## RAG：应该讲什么

### 1. 检索链路设计

你要能顺着链路讲清：

`文档解析 → 切块 → embedding → dense / BM25 召回 → RRF 融合 → rerank → 受约束生成 → 引用`

本项目的事实：

- 文本切块为递归切分，知识库侧 `chunk_size=1000`、`chunk_overlap=150`；Modular RAG 侧 overlap 为 200。
- bge-m3 负责 dense 语义检索；BM25 补足精确术语、论文名与方法名命中。
- 两路分数不直接相加，而是用 RRF 融合排名：

  `RRF(d) = Σ 1 / (60 + rank_r(d))`

- qwen3-rerank 对融合结果做 query-passage 精排；是否启用是显式模式选择，而非隐式黑箱。

回答不要停在“用了 Chroma / LangChain / embedding”。要说“为什么需要两路召回、为什么 RRF 用 rank 而非原始分数、rerank 放在哪一层、代价是什么”。

### 2. 优化与量化结果

可以安全使用的全量 benchmark：

| 语料与任务 | 指标 | 结果 |
|---|---:|---:|
| 336 篇论文、25,832 chunks、90 条 Golden Query | dense Hit@10 | 0.933 |
| 同上 | BM25 Hit@10 | 0.922 |
| 同上 | RRF Hit@10 | 0.922 |
| 同上 | RRF + qwen3-rerank Hit@10 | 0.978 |
| 同上、top-5 contexts | Ragas Faithfulness | 0.847 |

表达示例：

> 针对论文标题、方法名等精确术语和自然语言提问共存的问题，设计 bge-m3 dense 与 BM25 稀疏检索的混合召回，使用 RRF(k=60) 融合后接 qwen3-rerank 精排；在 336 篇论文、90 条 Golden Query 上，最终 Hit@10 达 97.8%，并以 Ragas Faithfulness 0.847 约束生成内容的证据支撑。

不要写“准确率提升到 97.8%”：这里是**文档级 Hit@10**，不是分类准确率。也不要把 Faithfulness 说成“回答正确率”，它衡量回答论断是否被检索上下文支撑。

### 3. 面试高频追问

- 为什么不是只用向量检索：embedding 擅长同义改写，BM25 擅长精确术语；两路漏召回不完全相同。
- 为什么不直接融合分数：BM25 与余弦相似度量纲不同，RRF 只利用排名，避免脆弱的分数校准。
- 为什么需要 rerank：召回阶段偏向高召回，cross-encoder / reranker 用更深的 query-passage 交互换取更好的最终排序，但有延迟成本。
- Chunk 为什么重要：chunk 太小会丢上下文，太大降低语义聚焦；大小、overlap、文档格式解析都应能解释为检索质量决策。
- 如何处理幻觉：生成 prompt 只基于检索上下文，保留真实访问来源；用 Faithfulness 衡量“有无证据支撑”，而不是只看回答流畅度。

## Agent：应该讲什么

### 1. 先说明模式选型

本项目不是把所有事情都塞给自由 ReAct：

- 研究报告主链路使用 LangGraph `StateGraph`，因为学术调研强调可复现、可观察、可人工审核。
- 对话搜索与 MCP 路径使用 LangChain `@tool` + `bind_tools`，由模型根据 schema 决定是否调用工具。
- Doc Agent 使用 ReAct + ToolRegistry，因为文档阅读、检索、提出改写需要依据运行时结果继续决策。

推荐回答：

> 我把稳定性要求高、步骤可预期的报告生成设计成 workflow；把是否检索、调用哪个工具、如何根据工具结果继续的部分留给 agentic loop。选型依据是控制流的不确定性，而不是为了堆 Agent 名词。

### 2. 工具系统要讲完整闭环

面试官会追问“新工具怎么被发现和调用”。本项目可按以下链路回答：

`Python 函数 → @tool 包装为 Tool 对象（名称、描述、参数 JSON Schema、执行器） → tools 列表 → llm.bind_tools(tools) → LLM 返回 tool_calls → 按 tool name 分发 ainvoke(args) → 工具结果回填消息 → LLM 继续决策`

MCP 与 LangChain Tool 的共同本质是：`name → (schema, handler)` 的注册表，只是 MCP 额外标准化跨进程/跨应用暴露方式。

### 3. 稳定性与恢复

当前项目中可讲的工程点：

- Human-in-the-loop 审核节点可将不合格大纲打回 planner，并有最大重规划次数。
- 章节研究通过 `asyncio.gather` 并行，但多视角模式设共享 semaphore，最多并行 2 条完整研究管线，避免外部搜索/模型连接被瞬时打满。
- 每条视角研究有 360 秒 timeout；失败视角不会让整个章节永久阻塞。
- Agent benchmark 每完成一个 case 落 checkpoint，长时运行遇到网络波动仍能审计或续跑。
- Doc Agent 使用 read-before-edit、propose/apply 分离和副本写入，防止模型直接破坏原文。

不要泛泛写“支持错误恢复”。要落到触发条件、控制策略和影响范围，例如“外部调用并发过高导致连接堆积后，用共享 semaphore 与超时把失败隔离到单个视角”。

### 4. 端到端 Agent 评估

当前 Golden Set：4 个研究任务 × 3 个变体。指标为标题覆盖率、引用数、LLM 裁判的 Citation Support、任务完成率、平均/P95 延迟。

| 变体 | 引用支撑率 | 完成率 | 平均耗时 |
|---|---:|---:|---:|
| Basic | 0.438 | 100% | 68.2s |
| Multi-Agent | 0.844 | 100% | 284.7s |
| Multi-Agent + Perspectives | 1.000 | 100% | 399.4s |

诚实的结论：多 Agent 增强了引用支撑，但延迟显著上升；多视角在目前四个 case 中**未提升**标题覆盖率，不能写成“STORM 已显著提升大纲质量”。这个结果适合用来说明你会做回归评估，而不是只挑好看的数字。

原始数据：`outputs/agent_eval/agent_eval_report.json`。

## 简历检查清单

- 每个 bullet 都含“技术决策 + 解决的问题 + 可验证指标”中的至少两项。
- RAG bullet 聚焦 chunk / retrieval / rerank / grounding / evaluation，不把 LangChain 当成果。
- Agent bullet 聚焦 tool schema、状态编排、失败边界、重试/超时/人工审核，不只写 Function Calling 或 ReAct。
- 指标注明口径：Hit@10、Faithfulness、Citation Support、P95 都不是同一件事。
- 小样本结果明确说明 benchmark 规模和局限，避免把 4-case LLM 裁判分数包装成生产级结论。
