# Agent 工作流 + RAG 技术栈 · 面试系统表达指南

> 目标:面试时能**系统地、分层地**讲清这个项目,而不是碎片化报菜名。
> 每节先给"30 秒版本"(电梯陈述),再给展开细节和公式,最后给可能的追问。

---

## 0. 全局一张图(开场先立框架)

**30 秒版本**:
> "这是一个科研调研 Agent 系统,四条能力线:①单智能体调研 pipeline(问题→子查询→联网检索→上下文压缩→带引用报告);②LangGraph 多智能体(planner/researcher/writer/fact-checker,支持 STORM 式多视角);③一个 336 篇论文的 RAG 知识库(混合检索+重排,MCP 协议暴露);④一个 ReAct 文档改写 Agent(基于知识库溯源改论文)。检索和 Agent 两层各自有量化评估体系。"

```
用户 → Next.js UI → FastAPI(JWT 鉴权)
                      ├── 单智能体调研 pipeline(固定 workflow,可复现)
                      ├── LangGraph 多智能体(+ STORM perspectives 开关)
                      ├── RAG 知识库(Chroma + bge-m3 + BM25 + RRF + qwen3-rerank)
                      │     └── 同时是 MCP server(query_knowledge_hub)
                      └── Doc Agent(ReAct + ToolRegistry,知识库溯源改写)
评估:检索层(Hit@10 / MRR / Ragas)+ Agent 层(Coverage / Citation / Success / P95)
```

**面试表达要点**:先讲这张图,让面试官知道你有"系统观",再让他挑感兴趣的线深入。**主动说出哪里是固定 workflow、哪里是真 agentic**——这个诚实的区分本身就是加分项。

---

## 1. Agent 工作流

### 1.1 单智能体调研 pipeline(确定性 workflow)

**30 秒版本**:
> "输入一个研究问题,LLM 先拆成 3-4 个聚焦子查询;每个子查询并发走'多引擎检索→全文抓取→上下文压缩';压缩后的证据连同引用约束喂给 LLM 写报告;引用列表来自独立维护的真实访问记录(visited_urls),不是模型输出——从机制上杜绝编造引用。"

**一次真实 report 行为的时间分解**(实测,`什么是对抗攻击`,DeepSeek + DuckDuckGo + 本地 bge-m3):

| 阶段 | 耗时 | 占比 | 做了什么 |
|---|---|---|---|
| 选 agent 人设 + 子查询规划 | ~5s | 5% | LLM 决定"扮演什么专家"、拆出子查询 |
| 检索 + 抓取 + 上下文压缩 | ~40s | 45% | 多引擎并发搜索、抓全文、切块过滤 |
| 报告写作(流式) | ~45s | 47% | LLM 按证据+引用约束逐字生成 |
| 导出(md/docx/pdf) | ~4s | 3% | 文件落盘 |
| **端到端** | **~94s** | | 成本约 $0.01/篇 |

**为什么主流程故意做成固定 workflow**(必被追问):
> "学术调研要求可复现、可溯源、可调试。让 agent 自由决定'要不要搜'会引入不确定性且难以排错。我把确定性留给主管线,把自主性放在三个真正需要决策的位置(见下)。什么时候用 workflow、什么时候用 agentic loop,是工程判断,不是能力上限。"

### 1.2 三处真正的 Agentic(LLM 决定控制流)

| 位置 | 机制 | 代码 |
|---|---|---|
| 对话追问自主搜索 | LLM 判断问题是否需要联网,自主调 `quick_search`(LangChain `@tool` + `bind_tools`) | `backend/chat/chat.py` |
| MCP 工具循环 | `bind_tools` → 模型吐 `tool_calls` → 执行 → 回填;还有 LLM 先从工具池挑 top-3(工具路由) | `asteria_researcher/mcp/research.py`、`tool_selector.py` |
| Doc Agent(ReAct) | 自研 ToolRegistry + 手写 ReAct 循环,LLM 每轮决定调哪个工具 | `backend/doc_agent/` |

**Doc Agent 的铁证案例**(演示"不是固定流程"):实测轨迹为
`read_document → search×3(自己精炼query) → propose_edit 失败×2(原文非逐字匹配) → 自己重新 read_document → propose 成功`——**从工具错误中自我恢复**,控制流由模型在运行时决定。

**Doc Agent 安全模型**(借 coding agent 思想,结构性强制而非提示词约束):
- read-before-edit:只能改写文档里逐字存在的片段
- propose ≠ apply:ReAct 循环只能产出 diff 提案;写盘是独立的用户确认动作
- 永不覆盖原文:apply 只写 `<name>.edited.tex` 副本

**ToolRegistry 一句话讲穿**(追问"和 LangChain tool 什么关系"):
> "本质是一张 name→(JSON Schema, handler) 的字典 + 两个操作:序列化成 tools 数组给 LLM、按名回调。LangChain 的 `@tool`+`bind_tools` 核心也是这个,多了 schema 自动推导和跨厂商格式转换。项目里两套并存:chat/MCP 路径用 LangChain(工具本来就活在它生态里),doc_agent 手写 70 行(自包含模块,避免依赖税)——一个证明会用,一个证明懂原理。"

### 1.3 LangGraph 多智能体(+ STORM)

**30 秒版本**:
> "用 `StateGraph` 编排 browser→planner→人工审核→researcher(并行)→writer→fact_checker→publisher。两处条件边:大纲人工审核不通过会打回 planner 重新规划(有最大修订次数);共享状态是 TypedDict,节点只返回增量更新。章节级并行靠子图多实例化 + `asyncio.gather`。"

**STORM 式多视角**(新增,配置开关 `perspective_guided_research`):
- 论文出处:Shao et al., *Assisting in Writing Wikipedia-like Articles From Scratch with LLMs*(STORM, 2024)
- 核心思想:单一视角检索容易证据面窄;先让 LLM 为每个章节规划 2 个**互补视角**(如"算法研究者"vs"落地工程师"),每个视角带 2 个具体问题,并行检索后再综合成单一章节
- 工程要点:planner 不动、下游 writer 契约不变、视角生成失败自动降级回普通子话题研究——**增量、可开关、可对比**

**技术栈一览**:LangGraph(StateGraph/条件边)、LangChain(统一 LLM 接口/`@tool`/text splitter)、FastAPI(路由/`Depends` 鉴权/WebSocket 实时推送)、Next.js 14、PostgreSQL(用户与报告持久化)、DeepSeek(生成)、qwen 系(rerank/vision/裁判)、Ollama bge-m3(本地 embedding)、Chroma(向量库)。

---

## 2. RAG 工作流(含公式)

### 2.1 全链路

```
Ingestion:  PDF → 解析 → 分块(1000 chars/150 overlap) → bge-m3 嵌入 → Chroma(HNSW)
                                              └→ BM25 索引(jieba 分词,持久化)
Query:      问题 ─┬─ Dense 检索(top-20) ─┐
                  └─ BM25 检索(top-20) ──┴→ RRF 融合 → qwen3-rerank → top-k
Answer:     top-k 段落 + 引用约束 prompt → LLM 合成带 [n] 引用的回答
```

语料:336 篇论文 / 25,832 chunks(174 篇物理信道水印 + 147 篇通用 CV/AI 干扰项 + 15 篇 CS);多模态:qwen-vl 给论文图表生成文字描述后一并入库,图表内容可检索。

### 2.2 Dense 检索(bge-m3)

- **bge-m3**:BAAI 出的多语言 embedding 模型,输出 **1024 维**向量,中英双语强;本地 Ollama 跑,零 API 成本、数据不出内网。
- 相似度用**余弦**:

$$\text{sim}(q, d) = \frac{\vec{q} \cdot \vec{d}}{\|\vec{q}\| \, \|\vec{d}\|}$$

- 索引用 **HNSW**(分层可导航小世界图):近似最近邻,查询复杂度近 O(log N),25k 向量规模下检索 <100ms。
- **强项**:跨表述匹配("换个说法也能找到");**弱项**:精确术语/型号被"语义平均"稀释。

### 2.3 Sparse 检索(BM25 / Okapi)

$$\text{score}(D, Q) = \sum_{t \in Q} \text{IDF}(t) \cdot \frac{f(t, D) \cdot (k_1 + 1)}{f(t, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

$$\text{IDF}(t) = \ln\left(\frac{N - n_t + 0.5}{n_t + 0.5} + 1\right)$$

- $f(t,D)$:词 t 在文档 D 中的词频;$|D|$:文档长度;avgdl:平均文档长度
- $k_1 \approx 1.2\text{-}2.0$:词频饱和度(词频增益递减,防"堆关键词")
- $b \approx 0.75$:长度归一化强度(长文档天然含更多词,要打折)
- **强项**:精确术语命中(方法名、数据集名、型号);**弱项**:不认同义词("汽车"≠"轿车")。

### 2.4 RRF 融合(Reciprocal Rank Fusion)

$$\text{RRF}(d) = \sum_{r \in \text{rankers}} \frac{1}{k + \text{rank}_r(d)}, \quad k = 60$$

- **为什么用排名不用分数**:BM25 分数无界、余弦在 [0,1],两者**量纲不可比**,直接加权要做脆弱的校准;排名天然免校准。
- **k=60 的作用**:压低头部排名的绝对主导(rank1 vs rank2 的差距被 k 稀释),让两路都能有效贡献;60 是 RRF 原论文推荐值,评估集小时不调它以免过拟合。
- **实测价值**:dense 和 BM25 漏掉的是**不同的**文档,融合后 Hit@10 从单路 93.3% 提到 97.8%(配合 rerank)。

### 2.5 重排(qwen3-rerank)

- RRF 是**粗排融合**(只看排名,不再看内容);rerank 是**精排**:qwen3-rerank 对 (query, passage) 逐对做深层相关性打分,重新排序取 top-k。
- 代价:约 +1.2-1.5s/查询;收益:Hit@10 92.2%(纯RRF)→ 97.8%,MRR 提升明显。
- **精度/延迟是按调用可选的**(mode 参数:hybrid = 不重排,hybrid_rerank = 重排),调用方自己选权衡点。

### 2.6 上下文压缩(同一套思想反哺主调研管线)

调研 pipeline 抓回的网页内容,同样走"BM25+dense 双信号 → RRF 排名选择 → 近重复抑制(cosine>0.95 只留一份)"过滤,替换了原来的单信号绝对阈值(0.35)方案。**要点**:绝对阈值随 query 分布漂移、可能清空上下文;排名选择永远能选出相对最优的 k 个。这是 Context Engineering 的核心落点:**有限上下文预算里最大化信号密度**。

---

## 3. 评估体系(两层,分开讲)

### 3.1 为什么分两层

> "检索评估回答'资料找得准不准',Agent 评估回答'整个任务完成得好不好'——前者是组件级回归,后者是端到端验收。混在一起会互相污染归因。"

### 3.2 检索层评估

**Golden Set 构造**:从语料随机采样信息密集的 chunk,让 LLM 反向生成"这段能回答的研究问题",该 chunk 所属论文即期望命中——90 条,自动构造+人工抽查。
**已知偏差(主动坦白)**:反向生成的问题会复用原文术语 → 偏袒 BM25(词法匹配),其 Hit@1 被高估;真实用户口语化提问更依赖语义检索。所以不单看某一路,看融合后整体。

**指标定义**:
- **Hit Rate@k**(文档级 Recall@k):top-k 检索结果(按所属文档去重)包含期望论文的查询占比
- **MRR@10**:$\text{MRR} = \frac{1}{|Q|}\sum_{i} \frac{1}{\text{rank}_i}$,期望文档排名的倒数均值(越靠前分越高)
- **Ragas Faithfulness**:答案拆成原子论断,LLM 裁判逐条判断能否被检索段落蕴含,$= \frac{\text{被支撑论断数}}{\text{总论断数}}$——只管"有没有出处",不管"对不对"
- **Answer Relevancy**:让 LLM 从答案反推它在回答什么问题,取反推问题与原 query 的 embedding 余弦均值——衡量"是否切题"

**Benchmark 数字**(336 篇 / 25.8k chunks / 90 golden queries,qwen-plus 裁判):

| 阶段 | Hit@10 | 说明 |
|---|---|---|
| dense(bge-m3) | 0.933 | 单路语义 |
| sparse(BM25) | 0.922 | 单路词法 |
| RRF 融合 | 0.922 | 排名融合 |
| **+ qwen3-rerank** | **0.978** | 最终档位 |

- **Ragas Faithfulness = 0.847**(90 条 Golden Query 全量评估);它衡量答案论断是否能被 top-5 检索上下文支撑，不等价于事实正确率。
- 非 rerank 模式延迟 <110ms;rerank +~1.4s

**两个必讲的一手发现**:
1. **低 Faithfulness ≠ 幻觉**:分析低分样本,主因是"参数知识泄漏"——答案正确但检索段落里没有原文(如 ViT 的 16×16 patch 常识),Ragas 只认出处判 0。
2. **上下文精度 > 数量**(消融):把生成上下文从 top-5 扩到 top-8 并收紧 prompt,Faithfulness 反而 0.867→0.780——rank 6-8 的低相关段落被模型揉进答案,裁判判"支撑不足"。结论:喂给生成端的不是越多越好。

### 3.3 Agent 层评估(端到端)

**设计**:4 个调研任务 golden case(带参考大纲)× 3 变体对比:`basic`(单智能体)/ `multi_agent`(LangGraph)/ `multi_agent_perspectives`(+STORM)。

**指标**:
- **Outline Coverage**:生成报告的标题集合对参考大纲的语义覆盖率(SequenceMatcher 相似匹配)
- **Citation Precision**:LLM 裁判判断被引 URL 是否真实支撑其所在论断
- **Task Success Rate**:任务完成率
- **Latency(avg + P95)**:P95 用 nearest-rank 法;样本少时 P95 退化为最大值,如实报告

**结果**(4 个 Golden Case × 3 变体，2026-07-10):

| 变体 | Outline Coverage | 平均引用数 | Citation Support | 完成率 | 平均耗时 / P95 |
|---|---:|---:|---:|---:|---:|
| basic | 0.333 | 8.75 | 0.438 | 100% | 68.2s / 83.9s |
| multi_agent | 0.250 | 27.75 | 0.844 | 100% | 284.7s / 427.8s |
| multi_agent_perspectives | 0.250 | 16.25 | 1.000 | 100% | 399.4s / 425.5s |

这里的 Citation Support 是 LLM 裁判对带链接论断的抽样支撑率。结论不包装：多 Agent 明显增加了可溯源引用并提高引用支撑，但带来约 4 倍延迟；本轮 4 case 中，多视角没有提升基于标题相似度计算的 Outline Coverage，只能说明它值得作为可开关策略继续调参和扩充 benchmark，不能宣称“STORM 一定提升大纲质量”。原始结果见 `outputs/agent_eval/agent_eval_report.json`，runner 为 `scripts/evaluate_agent_workflows.py --judge-citations`。

### 3.4 评估的面试叙事(收尾用)

> "我最看重的不是数字本身,而是**回归能力**:golden set 固定后,任何检索/编排改动跑一遍就知道变好还是变坏。比如这次 STORM 式视角在 4 个 case 上没有提高大纲覆盖率，代价却增加了延迟；这就是继续调参或收缩使用范围的依据，不靠感觉。另外我清楚评估的局限:golden set 有术语偏差、LLM 裁判有方差、小样本 P95 退化——能说出局限，数字才可信。"

---

## 4. 高频追问速查

| 追问 | 一句话核心 |
|---|---|
| 为什么混合检索,不全用向量? | 术语精确匹配是 BM25 强项、embedding 会稀释;两路漏的文档不同,融合互补(93.3%→97.8% 有数) |
| RRF 的 k 为什么 60? | 原论文推荐值;控制头部排名主导度;评估集小,调它容易过拟合 |
| Faithfulness 为什么不是 1? | 参数知识泄漏(正确但无出处),不是幻觉;检索质量与 faithfulness 耦合 |
| 你的 agent 是不是固定 workflow? | 主管线故意确定性(可复现);三处真 agentic(对话搜索/MCP 循环/doc-agent ReAct),后者有"从工具错误自我恢复"的实测轨迹 |
| ToolRegistry 和 LangChain tool? | 同一本质:name→(schema,handler) 字典+序列化+分发;手写版证明懂原理,LangChain 版多 schema 推导和生态 |
| 评估集可信吗? | 自动构造有术语偏差(偏袒BM25),我主动校正认知:看融合整体+人工抽查;它是回归基线不是绝对真值 |
| 为什么 pgvector 换 Chroma? | 收敛为单一引擎(原双系统检索重叠是架构异味);Chroma 侧带 qwen-vl 多模态与 Ragas 评估生态,评估与产品同源 |
