# Skill 设计对照

2026-09-12 · Codex（GPT-5）

## 核对范围

对照当前产品页面、公开代码和论文，区分页面可观察行为与内部实现。没有安装外部技能、运行第三方脚本或改动参考服务配置；本轮只复核设计，并维护本项目已有 Skill 链路。

## 1. ClawsGO：能力入口与可查看技能包

实际访问 [Agent / 技能界面](https://app.clawsgo.cn/chat)：

- 指令页单独管理主机上的 AGENTS.md，页面说明每次任务读取、修改从下一任务生效。
- 技能页区分内置、市场安装、自制技能，支持搜索、启用状态与查看正文。新增入口有市场、GitHub、zip 包和对话制作，并选择安装主机。
- 科研绘图详情将简介、SKILL.md 与 render.py 分成独立文件页，展示版本和许可。简介明确支持依据描述自主判断及 `/clawsgo-figure` 手动调用。
- 绘图指引描述调用渲染脚本、保存图像/源码/环境版本以及交付可预览产物的协议。它不是只有一段角色提示词。
- 此技能标为 Proprietary，仅作为功能分层参考，不复制正文或脚本。网页不能证明系统提示词的完整内容、模型每轮怎样发现技能，或 LaTeX 报告是否由另一套隐藏机制完成。

市场搜索 latex 看到了第三方格式和写作技能，不代表产品内置报告一定使用它们。候选 [agent-research-skills](https://github.com/lingzhi227/agent-research-skills) 将 writing、latex-formatting、paper-compilation 分开，但脚本依赖其宿主目录与工具，尚未做许可证及运行兼容性准入，不直接导入。

## 2. Gallant Lab：Playbook 驱动判断，脚本执行机械操作

读取 [README](https://github.com/gallantlab/literature-review-toolkit)、[PLAYBOOK](https://github.com/gallantlab/literature-review-toolkit/blob/main/PLAYBOOK.md)。入口让通用 Agent 阅读操作手册；检索子任务使用自包含提示词。引用核验、规范化、去重与渲染由 Python 脚本处理。文章内容与参考文献分别放在 content.json、rows.json，再由工具输出 DOCX。

这不是动态 Skill 注册器，也不是现成 LaTeX 模板库。本项目继续复用已留存许可的一手来源/归因节选，不整体注入其论文数量、默认不读 PDF、APA 和固定流程要求。

## 3. HKUDS AI-Researcher：章节 Composer 与出版工具分离

读取 [writing.py](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/writing.py) 与 [methodology_composing_using_template.py](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/methodology_composing_using_template.py)。写作入口显式依次调用方法、相关工作、实验、引言、结论、摘要，再修正 TeX 并编译。方法章节使用研究记录、代码与写作样例，先组织结构，再展开小节、按 checklist 修订。

writing template 是内容表达样例，不等同于字体/页边距模板；章节提示词仍嵌在 Python 中，不是通过通用 manifest 自主发现。借鉴它的“内容证据 → 写作指导 → 章节草稿 → 渲染”，不移植固定章节顺序到自主研究循环。

## 4. PaperMentor：模块化指导按职责注入

核对 [论文 §4 与附录](https://aclanthology.org/2026.acl-demo.39/)、[Orchestrator 源码](https://github.com/jiarui-liu/overleaf/blob/HEAD/services/web/app/src/Features/Chat/AiTutorReviewOrchestrator.mjs) 和 [LaTeX 指导](https://github.com/jiarui-liu/overleaf/blob/HEAD/services/web/app/src/Features/Chat/ai-tutor-skills/06_writing_style/latex_formatting.md)。

代码以 skillFiles 为审阅角色配置文件，loadSkill 读取正文，拼入该角色的系统提示词；论文类型识别及投稿场景再补充指导。章节、写作风格、LaTeX/数学格式、图表等职责分开。它主要生成定位到源码的修改建议，而非自主开展调研或从零产出论文。

LaTeX 指导确实独立，但包含投稿末尾章节顺序、匿名投稿与页数要求，并非所有报告都适用的纯排版规范。尤其不能把其中的 Limitations 章节要求变成“被综述论文必须有独立局限章节”。本轮不复制其 AGPL 项目内容进现有 Skill；若以后复用，先确认许可和适用场景。

## 对本项目的结论

| 层次 | 当前实现 | 接续方向 |
| --- | --- | --- |
| 发现与选择 | 元信息目录、阶段过滤、load_skill、用户指定 | `/skill` 复用同一接口；角色内细粒度发现 |
| 内容指导 | 一个主内容 Skill，可叠加辅助指导 | 论证、比较、归因、图表说明等独立指导 |
| 格式 | 输出契约与 academic/brief 模板独立 | 投稿规范按需选择，不能冒充通用规则 |
| 工具 | 注册处理器与权限校验，Skill 不扩权 | BibTeX、格式检查、资产管理分别接入 |
| 可追溯 | 版本、哈希、来源、阶段、指定/自选记录 | 历史任务完整 Skill 资源快照与兼容性记录 |

现阶段保留分阶段自主选择，不将所有知识一次塞入系统提示词。可复用的是内容与格式的解耦、细粒度指导和工具契约，不是他人的全部流程与宿主假设。
