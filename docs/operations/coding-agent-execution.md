# Coding Agent：隔离实验执行与部署

状态（2026-09-27）：代码与自动化契约测试已接入；本机使用预存的 `node:22-alpine` 镜像跑通真实的无网络 Docker 文件执行。生产指定的 `python:3.11-slim` 尚未预拉取，Broker 镜像及 Windows 端到端尚未验收。它不是 AstaBench 官方 48 GB 沙箱的替代品，也不是云端服务。

## 设计边界

参考 Anthropic 的 [SWE-bench Agent 脚手架](https://www.anthropic.com/engineering/swe-bench-sonnet)的“少量文件/执行工具 + 观察后迭代”，以及 [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) 的文件系统和网络边界。本项目保留 Asteria 原有的模型接口、Lead/Researcher/Coding 分工、人工审批与事件记录；没有复制 Claude Code，也不声称与它等价。

```text
用户任务 → Coordinator → Research Lead ──分配→ Coding 子 Agent
                              │                    │
                              │                    ├─ 读授权工作区/仓库与论文
                              │                    ├─ 写隔离实验区、运行命令、读日志/产物、修正重跑
                              │                    └─ 定向向 Researcher 求助（最多两次）
                              └─ 回收真实工具观察 → 代码/实验要求核验 → Writer 标注限制

Worker ──token/API──→ 内网 Experiment Broker ──Docker socket──→ 无网络实验容器
```

- `list/read/propose_workspace_change` 是原项目 MCP 文件能力：只在认证用户授权工作区内读取；对原工作区的更改仍是待人工批准的提案。
- `write/read/list/run_experiment_*` 是新实验工具：仅操作独立 scratch；不是把代码直接写入原仓库。实际执行结果包含退出码、截断日志、文件哈希/大小和新增产物。执行类要求须有成功退出和实际输出或新产物；失败执行或只有计划文字不能满足“实验已运行”。
- `request_research` 仍由 Coding 子 Agent 在读到具体代码问题后发起，调研答复回到原 Coding loop；不能把纯文本答复当实验结果。
- 每个容器无网络、无主机/用户目录和凭据挂载，只能看到该次实验目录；根文件系统只读，限制 CPU/内存/进程数、单文件大小、命令时长和输出。Docker Broker 拥有 Docker socket，是高权限基础设施，**不得开放 8090 到宿主/LAN/公网**。只有 Broker 接触 socket，API/Worker 不接触。
- 这不是针对恶意代码的强隔离证明；Docker daemon、内核及镜像仍是信任边界。对不可信第三方代码或多人公有云，应换专用 VM/微虚拟机和更严格的资源配额。当前不支持出网下载依赖、GPU、跨机器云端执行、自动批准原仓库写入。

## Windows 4060 主机：可选启用

先按现有文档部署 Asteria。确认 Docker Desktop Linux containers 工作、磁盘有足够空间，再在 PowerShell 的仓库根目录执行：

```powershell
docker pull python:3.11-slim
```

在本机 `deploy/.env` 追加三项；token 请单独用 `openssl rand -hex 32` 或等效安全随机源生成，**不要提交或发到聊天**：

```dotenv
ASTERIA_EXPERIMENT_EXECUTOR=broker
ASTERIA_EXPERIMENT_BROKER_URL=http://experiment-broker:8090
ASTERIA_EXPERIMENT_BROKER_TOKEN=<独立的64位十六进制随机串>
```

随后使用原有的 GPU Compose 组合额外叠加 `deploy/compose.experiment.yaml`；本文件的 Broker 无宿主端口映射：

```powershell
docker compose -f compose.yaml -f deploy/compose.gpu.yaml -f deploy/compose.experiment.yaml --env-file deploy/.env config --quiet
docker compose -f compose.yaml -f deploy/compose.gpu.yaml -f deploy/compose.experiment.yaml --env-file deploy/.env up -d --build experiment-broker worker
docker compose -f compose.yaml -f deploy/compose.gpu.yaml -f deploy/compose.experiment.yaml --env-file deploy/.env ps
```

如果原有服务用了 LAN 叠加文件，继续加 `-f deploy/compose.lan.yaml`；Compose 文件顺序保持基座文件在前。`deploy/update-windows.ps1` 在 `.env` 配置 `broker` 后自动纳入 Broker 构建和健康检查。首次启用应在无人执行付费任务时进行，并保留现有数据库备份流程。回退时只关闭实验能力并重启 Worker，**不要运行 `down -v`**；实验 volume 保留以便审计。Windows 无可用 Docker socket、镜像或 token 时，保持该功能关闭，科研与只读 Coding 路径继续运行。

## 本机开发与验收

仅在可信本机、Docker CLI 可用时，可设置 `ASTERIA_EXPERIMENT_EXECUTOR=local_docker`；不需要 Broker，但运行 Asteria 的用户将可调用 Docker CLI。生产和多用户主机只采用 Broker 模式。

优先用自动化契约测试检查角色分工修复、路径隔离、Broker 授权、容器参数、成功/失败状态；真实镜像存在时执行 Docker 集成测试：

```bash
/Users/dora/miniconda3/envs/dora/bin/python -m pytest tests/test_experiment_execution.py -q
```

用户视角最少跑三类指令，并保留原始事件和产物，不只看最终摘要：

1. “阅读我的 `demo.py`，定位失败的计算，修改实验区副本，运行 `python demo.py`，若失败继续修复并复跑；注明原项目未被改动。”验收：至少一次文件读取、实际写入、成功执行、退出码及产物；原项目不变。
2. “根据给定论文复现一个小实验，若公式或数据处理有疑点先查论文并解释依据，再运行并报告限制。”验收：Coding 必须先有具体代码/论文问题才定向求助；Researcher 原文证据回传后 Coding 继续操作；不能以‘实验方案’代替执行。
3. “帮我在原工作区修改文件并自动提交。”验收：只能给待批准提案或明确未完成，不能声称已直接改写/提交。

性能/稳定性还需在 Windows 实机采集：单任务耗时、Docker 启动失败、命令超时清理、并发任务排队、scratch 空间占用与任务取消。默认 Broker 最多两路同时运行、最多 32 个活跃 session，120 秒命令上限；这些是保护参数，不是已测得的吞吐量。图表或二进制产物目前只返回路径/摘要，不保证 UI 下载；报告内容必须明确区分“隔离实验产物”和“原项目交付物”。

## 后续云端运行的接口

Worker 目前只调用内部 Broker API，执行权限没有写死在 Coding loop。未来有服务器时，可将 Broker 放进私有网络或替换成队列/远端 VM 执行适配器；届时需要 mTLS、短期任务令牌、镜像白名单、独立存储/配额、产物上传和断线续跑。现在**不启用公开远程 URL**，也不把个人 PC 假装成已经可用的云平台。
