# 后台研究任务与断线恢复

2026-09-12 · Codex

## 职责

桌面研究入口提交后台 Run，浏览器仅观察；主 Agent、并行研究员、Skill 注入、证据审查和出版代码保持不变。移动端按屏幕宽度选择接口的既有行为、外部 LangGraph 入口及旧 `/ws` 兼容路径不在这次迁移范围。

- API：鉴权、提交、幂等检查、事件补拉、审批和取消。
- Worker：独立 dora 进程，领取任务并调用现有研究运行时。API 重启和浏览器关闭不取消研究。
- PostgreSQL：Run、Job、Event、Approval、Artifact。项目归属经 conversation 外键关联，用户操作检查所有权；服务端记录报告，不依赖浏览器保存。
- 文件：论文、报告与执行产物保持文件存储，数据库记录路径、大小和 SHA-256。

Run 是用户请求，Job 是后台执行记录；本轮尚无实验 Attempt，等实验执行接入后增加。单 worker 串行领取不同 Run，单 Run 内现有研究子 Agent 仍并行。不承诺当前同步工具都支持立即抢占。

## 状态与一致性

`queued → running ↔ waiting_approval → completed / failed`

显式取消经过 `cancel_requested → cancelled`；执行进程失联为 `interrupted`。刷新或观察端退出不是取消。审批保存到数据库，可在刷新后确认；确认幂等且绑定具体 approval_id，不能误确认下一轮计划。

同一用户 request_id 和内容只创建一次任务；相同键不同内容返回 409，同一会话不同时创建两个活动 Run。领取使用行锁与 SKIP LOCKED，执行事件在 Run 锁下递增序号，补拉采用游标并分页；客户端重连不重新提交。

Job 使用 45 秒租约和心跳；写事件、审批、完成时校验 worker 所有权与租约。过期执行只标中断，不重新领取。当前 Agent 循环尚无逐动作恢复 checkpoint，外部工具未必幂等；未知执行结果不能通过自动重跑制造重复动作和费用。这与未来远程实验按 job_id 恢复观察是两个层次。

Worker 正常 TERM/INT 停止领取新任务并等待当前任务结束；强制退出后由后续 worker 回收过期租约。等待人工审批的任务须由用户明确取消或完成审批后才能正常排空。

## 接口

- `POST /api/workspace/runs`：conversation_id、request_id、研究 request。
- `GET /api/workspace/runs/latest?conversation_id=...`：会话最近一次运行。
- `GET /api/workspace/runs/{id}`：状态、当前审批、产物、用量与时间。
- `GET /api/workspace/runs/{id}/events?after=...`：按序最多 200 条。
- `POST /api/workspace/runs/{id}/cancel`：明确取消。
- `POST /api/workspace/runs/{id}/approvals/{approval_id}`：保存意见，content=null 表示确认。

客户端通过现有 Next workspace 代理访问，不引入第二套鉴权。后台请求不保存自定义凭据 headers 和任意 MCP 配置；凭据引用及 MCP 配置的服务端管理需要后续单独接入，遇到此类请求明确拒绝，不静默忽略。

## Usage 与时间

ContextVar 将并行模型调用的 provider usage 写入当前 Run，保留每次尝试、模型及缺失状态；不记录密钥，不把字符数当 token。总量同时给出有 usage 的调用数；费用未具备版本化计价规则时为 null。现有 embedding 用量尚未并入该汇总。

排队、执行墙钟、人工审批等待分别记录。执行墙钟包含出版时间，研究/编译细分后续依据阶段事件完善；本轮不冒称已有独立出版计时指标。

## 启动与验证

API 保持 dora / 8018，前端保持 Node 22 / 3023。从仓库根目录额外启动：

```sh
/Users/dora/miniconda3/envs/dora/bin/python scripts/start-research-service.py api
# 在另一个受管理进程中启动：
/Users/dora/miniconda3/envs/dora/bin/python scripts/start-research-service.py worker
```

Worker 读取仓库 `.env`，使用与研究 API 一致的模型、Embedding 和网络环境。常驻时采用用户级进程管理，固定 cwd，不清理 `.next`、不升级依赖、不挪端口。启动时建表，旧报告和对话不删除。

统一 Python 入口固定工作目录，将当前 Python、现有 Homebrew/TeX 安装目录补入进程 PATH，不修改系统环境，不安装依赖。worker 启动前检查 `xelatex`，缺失时不领取收费任务。API 与 worker 的建表使用数据库事务级锁，允许两个进程同时启动。鉴权仍由原环境配置决定，启动脚本不自行开启免登录。

本机用户级服务标签为 `com.asteria.backend8018`、`com.asteria.research-worker`、`com.asteria.frontend3023`。更新后端时先确认任务状态：worker 正常退出会排空当前任务，API 可单独重启。移除标签后必须确认旧标签已退出，再提交同名服务；不要把 remove/submit 紧接执行后直接视为重启成功。日志分别为 `/tmp/asteria-backend-8018.log`、`/tmp/asteria-research-worker.log`、`/tmp/asteria-frontend-3023.log`。

前端 SSR 出现 `Unknown system error -11, read` 时先定位读取路径，并用 `ls -lO` 检查 dataless 标记。本机实际遇到的是云端占位依赖，不能据此删除构建缓存。前台运行 `node ../../scripts/check-frontend-files.cjs`（cwd 为 frontend/nextjs）检查消毒器依赖图，检查子进程超时 30 秒。必要时恢复本地内容，或校验 package-lock integrity 后修复准确版本的单个包；必须保留嵌套 node_modules。启动脚本与本机 launchctl 已接入该检查。不得关闭 DOMPurify 消毒或关闭 TLS 校验来绕过。文件仍可能再次被系统卸载，长期保持下载或迁移依赖目录需单独规划。

浏览器从 URL 的 conversation 恢复运行；首次加载遇到临时服务错误与后续事件断线都只重试读取。401/403/404 明确提示不能查看，不无限重试。未完成的独立对话也显示在任务侧栏；已完成任务读取保存的报告及后续问答，不用原始 Run 事件覆盖问答。删除运行中对话返回 409；用户明确删除已结束对话时，在一个事务中删除其数据库运行记录与报告，产物文件保留。

数据库合同测试在随机独立 schema 内运行并清理自身数据，不碰业务表：

```sh
ASTERIA_RUNS_DB_TESTS=1 /Users/dora/miniconda3/envs/dora/bin/python -m pytest tests/test_durable_runs.py -q
```

真实服务联调结果记录于 DEVELOPMENT_LOG.md。实现与合同测试通过不等同于真实调研成功。
