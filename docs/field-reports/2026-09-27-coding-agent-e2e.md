# Coding Agent 本机隔离部署与端到端验收（2026-09-27）

## 范围与结论

本轮在 `feat/coding-agent-executor` 分支实施。日常 Asteria API（8018）与前端（3023）未替换；测试 API 使用 8027、独立 PostgreSQL 库 `asteria_qa_coding_20260927`、Redis DB 9 与独立工作区。Coding 实验只挂载独立 scratch 到无网络 Docker 容器，不挂载原工作区。日常 API 在验收前后均返回健康状态。

调研后的取舍是保留 Asteria 的 Coordinator→Research Lead→Researcher/Coding→Writer/CitationAgent 架构，只给 Coding Agent 接入少量文件读写、运行、观察与修复工具；原工作区改动仍走审批提案。参考 Anthropic 的 [SWE-bench Agent 脚手架](https://www.anthropic.com/engineering/swe-bench-sonnet)与 [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)，但这里的 Docker scratch 是本项目的实现，不声称复现其全部安全保证或云端执行。

## 实测矩阵

| 场景 | 入口与断言 | 结果 |
|---|---|---|
| 创建并运行代码 | 真实模型驱动 Coding loop，写 `demo.py`，Docker 运行，`result.txt` 内容为 `42` | 通过；5 次模型调用、4 次工具调用、1 次执行、8.51 秒 |
| 失败后修复 | 预置 `ZeroDivisionError`，真实运行失败，修改并重跑，核对 `result.txt` | 通过；7 次模型调用、6 次工具调用、2 次执行（首次失败）、10.49 秒 |
| 原科研任务回归 | 读 ReAct 与 AutoGen 原文，Lead 分派 3 个 Researcher，Writer 写综述、CitationAgent 插入来源；不得调用 Coding | 通过；49 次模型调用、96.88 秒、2 篇已读论文、0 个 Coding 子任务；报告 5693 字符 |
| 真实用户 HTTP 链路 | QA 账号登录→创建会话→提交代码指令→意图路由→Coding Agent→Docker 运行→返回真实产物 | 通过；路由为 `workspace_coding`，`execution_performed=true`、`scratch_change_performed=true`，产物 `result.txt` 3 字节、SHA-256 为 `084c799cd551dd1d8d5c5f9a5d593b2e931f5e36122ee5c793c1d08a19839cc0`；原工作区未发生改动或审批提案 |
| Research 的真实用户交付链路 | QA 账号登录→提交两篇原文综述→Lead 三路派工→Worker→Writer→CitationAgent→Markdown/PDF 下载及哈希核验 | 通过；87 秒、3 个 Researcher、0 个 Coding 子任务、187 条事件；下载 `md`、`latex_pdf`（347516 字节）、`citation_review`、`lead_decisions`、`tool_calls` |
| 全套自动化回归 | 对独立 PostgreSQL 库运行测试，含真实 Docker 用例与 QA 数据库安全护栏 | 406 通过、5 跳过；10.51 秒 |

报告与原始 trace 均保存在本工作树的 `outputs/coding-agent-eval-*`、`outputs/coding-http-acceptance-*`、`outputs/acceptance_*`（不入 Git）。Coding HTTP 验收摘要：`outputs/coding-http-acceptance-4cc3e19c94/summary.json`；Research HTTP 验收结果：`outputs/acceptance_07b42fe8bc/result.json`。PDF 全 3 页已渲染目视核对：中文、公式、表格和引文可读，无此前那种散乱字符/重叠；第 3 页因篇幅较短而留白较多，但不是编译错误。

## 发现、修复与限制

第一次修复用例里，模型拼接 `python broken.py; echo EXIT=$?`，Python 报错但 shell 的最终退出码被 `echo` 覆盖成 0。执行工具改用 `sh -ec`，并在提示词说明不能用 `echo $?` 或 `|| true` 掩盖失败；真实 Docker 回归确认 `exit 17; echo EXIT=$?` 会返回 17。随后同一修复任务得到一次失败、一次成功的可信记录。此修复针对非故意掩盖退出码；shell 条件表达式仍可能改变命令语义，不能把容器退出码当作完整的测试覆盖率。

科研核心评测的功能链路完成且正文有两篇来源，但用户要求约 900 字，实际 5693 字符；HTTP/Worker 验收的同类任务报告也有 3880 字符，**篇幅控制未达目标**。后者完成了真实 API/Worker/PDF 交付路径并通过下载校验，证明新增 Coding 能力未破坏这条典型 Research 路线；这仍不等于所有科研任务回归通过。

目前尚未在 Windows 4060 上对叠加 Compose 与 Broker 跑同一组端到端验收，未运行官方 AstaBench，也未验证不可信第三方代码的强隔离、多人并发、GPU/出网依赖与云端执行。叠加 Compose 静态配置校验通过（使用样例环境与占位 token，不是实机启动）。下一步先在 Windows 镜像重新构建后运行 Broker/Worker/真实用户任务，并对同一科研任务再跑回归。保留这些边界，避免以本机通过代替 Windows 发布结论。
