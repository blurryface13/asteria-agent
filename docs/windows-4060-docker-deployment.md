# Asteria 实验室 Docker 部署（Windows + RTX 4060）

本方案使用 Compose 启动 **API、独立 Worker、Next.js、PostgreSQL、Redis、Ollama**，首次自动拉取 `bge-m3` Embedding 模型。研究主模型 API Key 在管理员登录后由前端配置，无需写入镜像或首次启动配置。独立的 Modular RAG 代码在 Python 镜像内固定到 `f658c5a`，其 Chroma/BM25 索引、工作区、报告、数据库、Redis、Ollama 模型分别持久化。首次部署**不会**自动把 Mac 上的用户记录或 336 篇论文索引搬过去。

当前验证范围见本页末尾。**Windows 4060 GPU、模型调用和全量论文索引仍需在目标主机验收**；本页不是已经完成的 Windows 上线记录。

## 1. Windows 主机准备

1. 安装/更新 Windows 10/11、NVIDIA 驱动、WSL2、Docker Desktop（开启 WSL2 后端及 Linux 容器），在 WSL 发行版启用 Docker 集成。建议至少留出约 40 GB SSD 空间给首次镜像构建、TeX、Ollama 模型、缓存及数据卷，实际占用以后续 `docker system df` 为准。建议在 WSL Linux 文件系统中克隆仓库并构建，不要从 `/mnt/c` 运行。
2. 在 WSL 终端确认 `docker compose version`、`nvidia-smi` 可运行，并验证 Docker Desktop 已启用 GPU 容器支持。若暂时没有 GPU 支持，可以先不带 `--gpu` 以 CPU 模式启动，但 Embedding 会较慢。**无需在 Windows 另装 Ollama**；Compose 的 Ollama 只在内部网络开放 11434。
3. 从 GitHub 克隆包含 `compose.yaml` 的目标提交，运行 `git log -1 --oneline` 核对版本。构建中的分支不当作正式发布。

## 2. 私有配置与启动

在 WSL 仓库根目录执行（把地址换成管理员邮箱）：

```sh
git clone https://github.com/blurryface13/asteria-agent.git
cd asteria-agent
ASTERIA_ADMIN_EMAIL=you@example.com bash deploy/start.sh --gpu
```

脚本会在缺少 `deploy/.env` 时生成三份随机本地密钥，校验 Compose 配置并构建/启动全部服务；以后再次运行**不会覆盖**配置。无 GPU 时去掉 `--gpu`。手工部署也可以复制 `deploy/.env.example` 后填 `DB_PASSWORD`、`JWT_SECRET`、`ASTERIA_MODEL_SETTINGS_SECRET`、`ASTERIA_ADMIN_EMAILS`，执行 `docker compose --env-file deploy/.env up -d --build`。`DB_PASSWORD` 必须是 64 位十六进制。`deploy/.env` 不要提交或发到聊天中；稳定保存 `ASTERIA_MODEL_SETTINGS_SECRET`，否则已保存的分角色密钥无法解密。

首次构建可能较久，TeX/Python 依赖较大；`ollama-init` 会等待 Ollama 并下载 `bge-m3`，完成后 API 才启动。交互式首启脚本随后提示设置管理员密码。查看状态用 `docker compose --env-file deploy/.env ps` 和 `docker compose --env-file deploy/.env logs --tail=100 api worker web ollama-init`。默认仅绑定 `127.0.0.1:3023/8018`，打开 `http://127.0.0.1:3023/login`。如果首启被中断、跳过了密码提示，手工创建管理员账号：

```sh
docker compose --env-file deploy/.env exec -it api python scripts/manage-lab.py account --email <管理员邮箱>
```

密码在交互提示中输入，勿放在命令行参数。检查：

```sh
curl -fsS http://127.0.0.1:8018/health
curl -fsS http://127.0.0.1:8018/api/auth/config
docker compose --env-file deploy/.env exec api python scripts/check-research-deployment.py
```

`check-research-deployment.py` 不调用付费研究模型；会检查 DB、Redis、API、Ollama Embedding、XeLaTeX/CMap、两个 MCP，以及 `research_papers` 知识库是否有 chunk。**全新空索引时最后一项失败是预期现象**，不能因此声称旧 RAG 已迁移。

管理员登录后，在前端 **Agent → 模型** 输入 DeepSeek API Key，点“应用到全部角色”；它会覆盖每个角色现有的模型与密钥，之后可逐角色调整。前端只显示已设置与尾号，不回显完整密钥；服务端加密保存。`deploy/.env` 中 `DEEPSEEK_API_KEY` 可以留空。此设置管 Agent 角色的 DeepSeek 调用，不会自动给 Modular RAG 的 Qwen 问答、Reranker 或 RAGAS 评测配置 DashScope。Docker 版基础检索默认**关闭 Qwen Reranker**，无需 DashScope Key 即可先验证知识库检索；若要恢复与 Mac 同样的精排路线，需要手工填 `DASHSCOPE_API_KEY` 并将 `deploy/modular-rag-settings.yaml` 的 `rerank.enabled` 改为 `true` 后重新构建。切换精排前后指标不能直接混用。

## 3. 论文知识库与既有数据

Modular RAG 的索引来自原机器 `/Users/dora/Developer/modular-rag-engine/data`，包括 `db/chroma` 和 `db/bm25`；仅复制 Git 仓库无法恢复 336 篇论文语料。在服务停止、源索引没有写入时，将该 `data` 目录完整复制到 Windows WSL 仓库旁的 `rag-data` 目录，然后导入命名卷：

```sh
docker compose --env-file deploy/.env stop api worker web
docker compose --env-file deploy/.env run --rm --no-deps \
  -v "$PWD/rag-data:/source:ro" --entrypoint sh api \
  -c 'cp -a /source/. /opt/modular-rag-engine/data/'
docker compose --env-file deploy/.env up -d
docker compose --env-file deploy/.env exec api python scripts/check-research-deployment.py
```

传输前后核对文件数、大小及 Chroma collection/chunk 数；不把论文数据、账户数据库或报告输出打进 Docker 镜像。若还要迁移 Mac 上的账号与历史任务，需要另做 PostgreSQL `pg_dump`/恢复，并同步 `workspaces`、`outputs` 与模型设置密钥；**不要把新空库与旧工作区混用**。首次实验室验证可从全新账号开始，后续再经备份演练迁移历史数据。

## 4. 实验室 LAN 访问与验收

本地全链路通过后，才把 `deploy/.env` 里的 `ASTERIA_BIND_HOST` 改为 `0.0.0.0`，将 `CORS_ALLOW_ORIGINS` 增加准确的 `http://<Windows主机内网IP>:3023`，然后 `docker compose --env-file deploy/.env up -d`。浏览器按实际主机名访问 `:3023`，API 自动使用同一主机的 `:8018`；Next 服务端路由则访问容器内 `http://api:8018`。Windows 防火墙仅允许可信实验室网段/VPN 访问 3023 与 8018。**这套 HTTP LAN 配置不用于公网**；公网或不可信网络应另加 TLS、受控反向代理并启用 `ASTERIA_COOKIE_SECURE=1`，还需检查双端口 API 的 HTTPS 路由。

验收按顺序进行：

1. 管理员登录并从前端配置 API Key，创建第二个账号；两个账号的项目/会话/报告互不可见。
2. 新建研究任务，刷新页面后仍可看到任务，Worker 完成后能够下载 Markdown/PDF；重启服务后状态与文件仍在。
3. 查询已迁移的 `research_papers`，确认混合检索返回真实 chunk 与来源；执行一条带引用的真实研究任务时才会消耗模型费用。
4. 用另一台电脑访问内网地址，检查登录、进度推送、文件下载、引用链接，不只看首页能否加载。

`docker compose down` 保留命名卷；**不要执行 `docker compose down -v`**，它会删除数据库和索引。更新前先确认无正在运行/待审批任务，备份数据库与卷，再构建新镜像并运行同一套验收。回滚旧镜像不等于自动回滚数据库 schema。

## 5. 当前边界

- Compose 内置 Ollama 与 `bge-m3`；GPU 加速取决于目标机 NVIDIA 驱动、Docker Desktop/WSL2 的容器 GPU 支持，尚未在目标主机验证。容器不会把 `11434` 暴露给实验室成员。
- Modular RAG 代码随镜像固定，Chroma/BM25 在 `rag_data` 卷；空卷启动时系统可运行，但论文知识库不可算通过。
- 三个部署密钥与可选 DashScope Key 存于目标机 gitignored `deploy/.env`，Agent API Key 由管理员在前端配置并加密存于数据库；均适合受控实验室试运行，不是面向公网的秘密管理方案。正式对外部署应迁移到专用密钥服务。
- Compose 只解决可复现部署，不代表 10 人并发已经验收。后续应把认证接口负载、研究任务排队、模型费用与 RAG 延迟分开测。
- 本轮在 Mac 验证了 Compose CPU/GPU 配置解析、前端生产构建与容器 `/login` 响应、相关 Python 测试；Mac 可用磁盘不足以安全构建含完整 TeX/RAG 依赖的后端镜像。Windows 主机上的后端镜像构建、GPU Ollama、首次账号创建、模型密钥配置和真实研究报告仍须按第 2–4 节现场验收，不能提前宣称通过。
