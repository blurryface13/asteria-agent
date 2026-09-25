# 本轮需求、验收与授权清单

## 原始需求（保持架构）

1. 优先复用 Anthropic 官方 Research Lead / Subagent 提示词与角色设计；允许必要的工具名与权限适配，不另造一套不同架构。
2. 引入 Data Analyst，真实证据 → 图表数据 → 图表文件 → Writer；报告不仅有文字，也有能帮助判断创新空间的图表。
3. 完善 Writer 的图文综合与 CitationAgent 的邻近引用。Hooks 关联并行子 Agent、工具调用、错误与耗时。
4. 检索 MCP 以可用性为准；金融官方资源按动态 Skill 先引入，不给未授权服务填假凭据。
5. 用 CV 博士探索方向的复杂任务验收，不把代码硬编码为某个 CV 主题；原任务不因测试失败而降低目标。

## 通过标准

- 研究：回答表示、对齐机制、局限和创新空间；不是论文摘要拼贴。至少 10 篇已读相关论文，来源可追溯。
- 创新：2–3 个候选方向包含与已有工作的差异、可证伪假设、基线、评价协议、关键消融和失败风险；明确“建议实验”尚未执行。
- 图表：至少一幅有真实来源的数据/方法图，紧凑比较表；不同协议数字不可伪装成排行榜。图表解释与正文相连。
- 引用：论断附近标注出处；事实、跨来源推断、研究建议区分。参考条目与正文编号一致。
- 交付：PDF 每页可读、无缺字、遮挡、越界或残缺图表；Markdown、数据及图表文件可追溯。
- 工程：自动回归通过；真实登录→提交→确认→并行→报告→授权下载链路另验。不把离线重放说成端到端成功。
- 结果：保留失败记录和 BadCase，解释修复；不能仅凭模型自评宣布质量通过。

## 当前失败与恢复原则

原 Run 05837182c44b4d3dbfcdac00d72f1260 已失败：24 篇已读、6 子 Agent、75 次行动、95 次模型调用；共享调用上限使 Lead 在最后综合前失去调用机会。
这不是资料不足，而是研究与交付争抢预算。按官方“接近预算时停止研究并综合”的策略，改为停止新检索但允许结构化 handoff，给 Lead/Analyst/Writer/CitationAgent 留调用额度。
已有材料续跑另存目录，不修改原 Run 状态；后续新的真实 Run 验证修复后的全链路。

## 中断后发现的具体问题与修复

- `ddfe158d727c49d9bc0b50072d399a3c`：新的真实登录/提交链路完成了研究，但 Lead 因出版元数据未确认等限制返回 incomplete，旧代码直接禁止 Writer 交付。现在由同一 Lead 做一次有界的交付判断，区分核心证据缺失与可报告的限制；不增加新 Reviewer、不抹掉原始 incomplete 状态、不替代用户要求的真实实验执行。
- Writer 把明确标为未读的后续阅读候选放进参考文献，全篇重写两次仍保留同一问题。现在只修对应行；候选可保留为明确未读的名称，不能作为引用证据。
- CitationAgent 把建议消融、假设的否定条件以及表头当成待证明的实验结果。现在传递章节语境、排除纯表头、明确事实/建议的评分契约；不是放过虚构结果或错引。
- 图表的中文宽度估算与相对行高导致溢出、标题重叠。改为真实字体测量换行、按行数分配物理高度、独立标题区域。PDF 中长协议名称增加安全断行，数学符号映射到可信数学命令。
- 模型 402 曾中断在已完成 Writer 之后。`recover-research-delivery.py --resume-draft` 从校验通过的草稿恢复 CitationAgent，保留独立恢复目录，不重跑全文检索与 Writer；鉴权/余额等不可重试 HTTP 状态不再指数退避重试。

## 原证据续跑（不等同新端到端验收）

```sh
python scripts/recover-research-delivery.py outputs/review_7a840471255940c5925394e1202925ec \
  --checkpoint outputs/delivery_recovery/review_ab67fc8dcb6e4d8dad3da5174cbe92dc --resume-draft
```

仅检查排版、不调用模型：`python scripts/preview-research-report.py <已校验草稿目录>`。预览带“非验收交付”声明，不能作为最终报告。

## 明天集中处理的授权

| 服务 | 用途 | 申请/授权入口 | 当前状态 |
|---|---|---|---|
| Consensus | 跨学科学术检索 MCP，补充 arXiv | https://consensus.app/home/mcp/；https://help.consensus.app/en/articles/13694300-how-to-use-consensus-in-claude | initialize 实测401，需要有效授权；未购买额度 |
| Semantic Scholar | 可选学术元数据、引用图、出版状态核验 | https://www.semanticscholar.org/product/api#api-key-form | 未配置；可先申请免费 API Key，不是本轮报告阻塞项 |

优先申请 Consensus；网页账户 OAuth 与自建客户端的 token/API 授权不是同一件事，申请后先确认服务支持的接入方式。不要把密码、验证码或长期 Token 写进仓库/聊天记录，后续填写本地环境配置。
FactSet/LSEG/PitchBook 等商业金融数据暂不要求购买。已导入 sector-overview/model-update 是分析 Skill，不等于已接通上述数据库。先用公开财报/监管披露作为替代来源。
服务额度可能变化，以上不承诺匿名可用或固定免费额度。
