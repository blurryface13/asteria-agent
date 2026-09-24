# Anthropic 研究能力复用与带图报告验收

## 目标与不变项

保持入口路由、Research Lead → 并行 Search Subagents → Writer → CitationAgent 的骨架。
复用官方原始材料优先，只适配工具接口、权限和本地交付格式。数据分析读取已有研究材料，不重新做另一轮独立调研。

## 来源与复用边界

| 来源 | 固定版本 | 实际接入 |
|---|---|---|
| anthropics/claude-cookbooks | 813fbeec03cdedfda7808529438d1c7af71f26eb | Lead/Subagent 原始提示词及 MIT 许可完整保存；运行时直接提取委派、综合、停止条件、OODA、来源判断原文，并映射工具名 |
| anthropics/financial-services | 574ed3624aebd0418c7e96cd101262f30210ab26 | sector-overview、model-update 原文件与 Apache-2.0 许可完整保存；动态 Skill 加载时附加本地工具能力说明 |
| anthropics/claude-agent-sdk-demos/research-agent | 826b268506a5f3707623c9e6140b200befcbebae | 参考 Researcher → Data Analyst → Report Writer 与 Pre/PostToolUse 思路；不迁移 SDK 或 bypassPermissions；该目录未发现覆盖这些代码的许可证，未原样复制实现 |

上游生产 Lead 要求亲自撰写报告，SDK demo 则有独立 Writer，二者不是同一套运行时。
保留我们的 Writer/CitationAgent 分工，不同时注入互相冲突的写作指令。
上游固定次数、强制调用已启用的全部集成、不允许用户澄清等环境假设不引入。

原版文件位置：`asteria_researcher/agentic/skills/vendor/anthropic/`。
角色接入：`anthropic_roles.py`，动态目录：`skills/catalog.json`。
动态 Skill 采用官方 progressive disclosure：先暴露元数据，按需注入全文；不是每次把全部金融指令灌入 CV 调研上下文。
参考：https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

## 图表与报告交接

1. 用户需要图表时，Lead 研究收尾后交 Data Analyst；只读取当前任务的原文证据、子任务成果和 Lead 综合。
2. 结构化图表规格支持定性方法矩阵与定量横向柱图。每行保存 evidence_id、原文摘录、来源、条件和说明。
3. 摘录必须存在于给定原文；数值必须出现在摘录中。定量横向比较暂限同一原始表格/证据片段，不跨论文拼接不同协议的数字。
4. matplotlib 确定性渲染，不运行模型写出的 Python/Shell。图表原始数据保存在 analysis.json。
5. Writer 在解释附近插入注册图片；PDF 只接受注册的本地 PNG，不支持任意路径或远程图片下载。
6. CitationAgent 核对文字解释的支持关系；图片数据经过摘录校验，但这不等于自动保证语义分类正确。验收仍需看图和原文。

## Hooks

现有 events.jsonl 已记录工具参数和结果，并非完全没有观测。新增 tool-calls.jsonl 提供统一 PreToolUse/PostToolUse/ToolFailure 视图，按 trace_id/call_id/parent_call_id 关联并行子任务，记录取消与耗时。
使用 ContextVar 传播父调用，避免 SDK 示例中共享 current-parent 在并行协程里串线。第二份日志只记录输入输出摘要哈希与大小，不重复敏感正文。

## MCP 与金融边界

现有知识库检索通过认证 MCP bridge，公共论文检索仍由现有可靠工具执行。MCP 本身不保证上游网站可用性。
金融 Skill 已导入不代表商业数据 MCP 已授权或金融长链路已验收；先使用公开来源，不自动注册付费服务或宣称拥有实时行情。
后续 MCP 增补必须验证真实连接、参数/响应契约、超时与错误回传，不以安装成功代替业务可用。

## 验收

- 单元：源文件追溯、Skill 延迟加载、证据摘录/数值/路径校验、并行父调用归属、图表渲染。
- 集成：真实 XeLaTeX 中文带图报告，图像进入 PDF、源文件可追溯。
- 真实任务：CV 博士研究创新方向，至少 10 篇已读来源；对比方法、提出可证伪研究假设/基线/消融，图表有解释、出处及条件。
- 报告质量不以达到固定字数为通过标准；逐页检查图表文字、布局、论断引用、创新点可操作性。
- 真实端到端结果另行记录；未跑完不得用离线 PDF 测试替代。
