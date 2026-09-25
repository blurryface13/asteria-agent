# 4060 实验室部署与跨领域研究报告计划

状态：按角色 DeepSeek 管理界面及金融长报告运行路线已接入；Mac 本地完成一条受限 NVIDIA 年报真实报告冒烟，**尚未打包或在 Windows 4060 主机验收**。单个报告成功不等于跨主题稳定性或性能达标。

## 1. 当前边界与决策

- 主模型当前为远端 DeepSeek。4060 首先用于 Ollama `bge-m3` Embedding；用户数与长报告吞吐仍受 API 额度、研究 Worker 槽位、外部检索、数据库、磁盘和网络影响，不能用显存推断并发容量。
- DeepSeek 对相同输入前缀默认尝试缓存；Claude 的 `cache_control` 属于 Anthropic 请求格式。借鉴其“工具／稳定角色／稳定背景在前，本轮用户输入与工具观察在后”布局和缓存用量指标；只有切换到 Anthropic 供应商时才加供应商专属断点，并做冷／热 A/B，不向 DeepSeek 请求盲传该字段。
- 学术长链路已有 Lead／并行子 Agent／Data Analyst／Writer／CitationAgent。金融简答仍走 `financial_research` Specialist；用户要求报告时由 AgentOrchestrator 交给持久化 Research Lead，复用同一交付链。金融 `search_public` 只登记允许列表中的官方链接，原文 `read` 成功后才可形成证据。历史“官方资料”短答复混入 Wikipedia 的 BadCase 仍保留，短答路线尚未完成同等严格的一手来源约束。
- 前端会给普通对话也附带研究参数；因此是否进入金融长报告不能以 `research_request` 是否存在单独判断，而由意图结果中的 `report_requested` 表示实际交付需求。短问答保持 Specialist 路径，不因界面默认参数误触发收费长链路。
- 管理员可在工作台 Agent → 模型中给意图路由、Lead、子 Agent、Writer、CitationAgent 等分别选择 DeepSeek 模型及 API Key。数据库仅存加密密文，界面只显示密钥尾号；不配置时沿用服务端环境变量。配置快照按一次调用链冻结，下一任务才切换。API 与 Worker 必须持有同一 `ASTERIA_MODEL_SETTINGS_SECRET`（未设置时从稳定的 `JWT_SECRET` 派生）；变更密钥前要导出备份并规划重加密，否则旧密文无法读取。管理员会话和传输仍需 HTTPS 防护。
- 推荐 Docker Compose 交付 API、独立 Worker、前端、PostgreSQL、Redis；4060 首先承担宿主机 Ollama `bge-m3` Embedding，通过容器 `host.docker.internal` 访问。论文／知识库索引依赖 modular-rag-engine，必须作为明确的外部服务或纳入 Compose，不允许静默缺失。

## 2. 4060 交付顺序

1. **主机预检**：确认 Windows 10/11、WSL2、Docker Desktop、NVIDIA 驱动、显存／内存／SSD 可用空间；验证 Docker Linux 容器与宿主 Ollama 的连通性。若让容器内推理使用 GPU，先独立验证 `--gpus all`，不把本项目启动与 GPU 驱动调试绑在一起。
2. **镜像与配置**：锁定 Python／Node 依赖和 Git 提交；构建 amd64 API／Worker 镜像（含 XeLaTeX、CJK 字体和 `Adobe-GB1-UCS2` CMap），另构建 Node 22 前端镜像。Mac 为 Apple Silicon 时不要默认其本机构建镜像可直接部署至 x86_64 Windows PC。`.env`、模型密钥和密码不入镜像或 Git。
3. **持久化与网络**：数据库、Redis、工作区、Chroma、RAG 索引和 `outputs` 分别持久化；容器之间用服务名通信，不用 `127.0.0.1` 指向别的容器。浏览器访问 API 采用同源反向代理或在前端构建时设定实际可访问地址——`NEXT_PUBLIC_*` 在 Next 构建时会固化。实验室访问限内网／VPN，关闭开发免登录并配置 HTTPS、账号隔离与 CORS。
4. **部署预检**：让 `check-research-deployment.py` 支持 Compose 内的 API 地址；检查 PostgreSQL、Redis、Ollama Embedding、两个 MCP、modular-rag-engine、XeLaTeX/CMap、账号和授权下载。先在隔离 Compose 环境跑，不能覆盖当前 Mac 数据。
5. **功能验收**：两账号隔离；金融公开检索问答；一条带原文证据和 PDF 的学术研究；重启后任务状态、登录、索引和产物仍可读取。失败的模型任务不得被 Worker 自动重放收费。
6. **测试与上线**：Agent TestLab 的 Requests／pytest 验接口与状态，JMeter 分开测试认证后的提交／轮询控制面和少量真实模型任务。目标为 10–15 个实验室账号，但需实测排队时间、P95、429、错误率和模型费用后才能声称容量；研究 Worker 初始并发建议保守配置，再按结果调整。
7. **更新与回滚**：先备份数据库及持久卷，确认无运行或等待审批任务；按固定镜像版本更新 API／Worker／前端，并执行同一套冒烟与回归。旧镜像回滚不等于数据库模式自动回滚，若有迁移需配套快照恢复预案。

## 3. 金融报告不另造一套 Agent 骨架

保留 `financial_research` 短问答：概念解释和少量公开资料查询不应都付出完整报告的时延与费用。用户要求跨期分析、行业比较或正式报告时，入口改投**持久化的通用研究任务**，复用 Lead 分解互补子目标、并行检索／阅读、综合、Writer、CitationAgent 和产物发布。路由条件应包含所需交付物与证据深度，而非仅凭“金融”关键词。

难点在证据层，不在换人设：现已为长任务加金融源白名单与官方来源优先的公开检索包装，仍共用已读来源、页段、RAG、图表、CitationAgent 和产物账本。本地 `asteria-public-finance` MCP 用 `discover_financial_sources` 搜索公开官网链接，随后 `read` 工具才读取原文；与 Anthropic 金融 Skills 的提示词指导分开。未授权商业数据连接器不参与运行；可读取的 SEC、央行、交易所、统计机构及少量投资者关系站点采用明确主机列表和 HTTPS，网页读取仍限制大小与重定向。NVIDIA 官网目录页可登记其年度报告 PDF 链接与来源边，目录页本身不冒充年报。白名单不是所有企业财报都可访问的承诺；未覆盖的公司或反爬网页必须报告资料缺口，不拿摘要凑证据。下一步应增加报告期、币种、单位、发布日期的机器可检查元数据，并扩展实际需要的官方主机。

金融 Lead 可按实际问题分派“公司披露与财务口径”“行业／竞争与公开政策”“风险与反证”等互补子目标，不固定人数或章节。Data Analyst 只把有来源、同币种／单位／期间的数字制图；Writer 区分披露事实、模型推断和建议；CitationAgent 核验具体原文位置及数字口径。原有 Anthropic 金融 Skills 提供分析方法，**不能替代原文工具或数据授权**。

第一条完整验收任务选 NVIDIA FY2026 与 FY2025：比较收入与经营现金流、解释一项风险，给出原文链接／页码、报告期和单位，并生成 Markdown／PDF。已完成一次 Mac 本地真实模型冒烟，过程与局限见 `docs/financial-report-acceptance.md`。仍需在认证工作台路径与 Windows 4060 上复验，并加入其他行业、非美国主体及资料不可读的样本；不以报告篇幅、路由命中或 LLM 自评单独判通过。

## 4. Token 与缓存评估

使用现有阶段化用量事件，固定模型／资料版本／问题集合，记录 Lead、各子 Agent、Analyst、Writer、CitationAgent 的调用数、输入／输出、缓存读取、耗时、失败尝试和交付质量。先建立冷／热调用基线，再尝试重排稳定提示词前缀；比较**总成本和质量**，不缓存最终报告以回答语义相似的新任务。若后续真的切换 Claude，另测显式 `cache_control` 的创建／读取量与费用，且不把提供商缓存命中当成来源证据缓存。
