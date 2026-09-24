# 🐰 Asteria Agent

面向文献调研、综述写作和实验设计的科研智能体工作台。用自然语言描述目标，Agent 自主规划、委派研究、阅读与追踪论文，在证据充分后交付带引用的报告。

Python · AgentOrchestrator / BaseAgent · MCP · FastAPI · Next.js · PostgreSQL · Redis · ChromaDB · Ollama

当前主入口按 EchoMind 的角色编排方式适配：`AgentOrchestrator` 负责意图与主辅路由，工作角色共享 `BaseAgent` 工具循环；科研支路由 Lead 安排互补子目标并行调查、按批综合与补研，Writer 成稿后交给 CitationAgent 核对正文和原文出处。不是原样复制 EchoMind，也不是把旧 LangGraph 节点全部串行跑一遍。详见 [入口骨架](docs/echomind-alignment-plan.md)和 [科研多 Agent 架构图及工具清单](docs/anthropic-research-alignment.md)。

## ✨ 能做什么

- **自主研究**：根据任务目标安排检索、原文阅读与引用追踪，动态委派并行研究 Agent；计划支持人工确认与修订，补研依据证据缺口，而不是固定章节流水线。
- **按需使用 Skill**：Agent 发现技能并按阶段加载，用户也可查看、指定技能。内容写作指导、格式契约、LaTeX 模板和编译工具分别维护。
- **报告交付**：生成 Markdown、LaTeX 与 PDF，在工作台检查报告、源码、研究轨迹和引用关系；支持围绕报告继续问答。
- **项目与知识库**：项目组织多轮对话，历史内容持久化到 PostgreSQL。离线 RAG 保留独立入口，支持混合检索与重排；在线研究可选择启用 RAG。
- **科研工具与 MCP**：Lead/子 Agent 可检索论文、公开一手资料及授权实验室知识库；知识库与文件工具使用真实 stdio MCP。子任务完整结果独立保存，Lead 按需读取产物与阶段记忆；CitationAgent 对报告补充出处，发现引文缺口时定向修稿重检。
- **分层记忆**：PostgreSQL 保存会话原始记录，Redis 缓存近期上下文；用户偏好和项目主题以可编辑 Markdown 保存，并由独立 ChromaDB 集合索引主题记忆，按用户、项目与当前问题做语义召回。论文知识库的向量索引与个人记忆隔离。
- **实验室账号**：管理员创建邮箱账号并设置密码，成员的项目、对话、任务和记忆各自隔离；知识库可设置为实验室共享。邮件验证码仅在单独配置 SMTP 后启用。
- **后台运行**：桌面研究由独立 worker 执行，刷新或关闭页面不终止任务；进度、人工确认、模型用量与交付产物持久保存，重新打开即可继续查看。
- **评测工作台**：查看研究历史、导入 Trace、展开父子调用、检查规则报告；对 BadCase 质检并回流种子题库。当前自主运行时的语义评分与版本对比正在接入。

## 🖥️ 工作台

已完成的文献综述：研究进度与报告并排查看，细节按需展开。

![科研工作台与报告预览](assets/readme/research-workspace.png)

评测中心：示例 Trace 的规则归因、人工质检与种子回流，共用研究工作台的侧栏和详情面板。

![评测工作台](assets/readme/evaluation-workspace.png)

## 🛠️ 开发

当前本地开发使用 **Python 3.10（dora）与 Node.js 22**；Next.js 为 14.2 系列。研究 API、前端与 Embedding 服务独立运行，模型凭据保存在本地环境配置中。

服务启动后可执行 `python scripts/check-research-deployment.py` 检查数据库、Redis、Embedding、PDF 编译器和两个内置 MCP；`python scripts/accept-research-chain.py --approve-plan` 执行真实模型的多来源综述验收，保留任务、事件与交付产物（会使用模型额度）。

- [开发规范与当前进度](spec.md)
- [界面设计规范](DESIGN.md)
- [开发节点与真实运行记录](DEVELOPMENT_LOG.md)
- [后台任务与服务启动](docs/durable-runs.md)
- [评测工作台与评分策略](docs/evaluation-workspace.md)
- [自主实验与评测路线](docs/experiment-evaluation-roadmap.md)
- [Lead 分工与代码调研协作](docs/agentic-collaboration-plan.md)
- [科研多 Agent 架构图、运行边界与 MCP/Tool 清单](docs/anthropic-research-alignment.md)
- [协作验收、测试指令与当前限制](docs/agentic-collaboration-acceptance.md)
- [EchoMind 骨架对齐与真实请求验收](docs/echomind-alignment-plan.md)
- [实验室部署与登录排查](docs/lab-deployment.md)

调研引擎位于 `asteria_researcher/`，API 与持久化位于 `backend/`，Web 工作台位于 `frontend/nextjs/`。既有 LangGraph 工作流保留在 `multi_agents/`，与自主研究运行时分开维护。

## 🗺️ 接下来

- 授权主机与工作区内的自主实验执行、日志观察和结果复现。
- 当前 Agent 的历史补评、独立裁判、版本对比与 BadCase 回归。
- 进程异常后的检查点恢复、模型费用计价与运行指标展示。

## 🙏 致谢

项目从 [GPT Researcher](https://github.com/assafelovic/gpt-researcher) 的开源实现起步，也从 [STORM](https://github.com/stanford-oval/storm) 的多视角研究方法中获得了启发。感谢这些工作让科研助手的探索有了扎实的起点。

界面交互参考 [ClawsGO](https://clawsgo.cn/) 与 Codex。引入的第三方技能材料保留各自的来源与许可证。
