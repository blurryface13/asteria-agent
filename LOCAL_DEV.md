# 本地开发与服务维护

## 当前运行基线

本机仓库位于 `/Users/dora/Developer/asteria-agent`，不再从 Documents 中启动。Python 使用已有的 `dora` 环境，前端使用 Node 22 和仓库 lockfile。不要为日常启动重新安装依赖或创建另一套虚拟环境。

| 服务 | 地址 / 入口 | 本机 launchd label |
| --- | --- | --- |
| Next.js 工作台 | http://127.0.0.1:3023 | `com.asteria.frontend3023` |
| API | http://127.0.0.1:8018 | `com.asteria.backend8018` |
| 研究 worker | `scripts/start-research-service.py worker` | `com.asteria.research-worker` |

三项服务由 `~/Library/LaunchAgents/` 中同名 plist 管理，登录后启动，终端关闭不影响运行。plist 是本机配置，不含在仓库中；解释器、工作目录和脚本路径均指向新位置。旧的 `start-local.sh` / 3000、8000 示例不是这套已部署工作台的运行方式。

## 先检查，不重复启动

```bash
launchctl print gui/$(id -u)/com.asteria.frontend3023
launchctl print gui/$(id -u)/com.asteria.backend8018
launchctl print gui/$(id -u)/com.asteria.research-worker
curl --noproxy '*' -f http://127.0.0.1:3023/ -o /dev/null
curl --noproxy '*' -f http://127.0.0.1:8018/api/workspace/skills -o /dev/null
```

HTTP 200 只证明页面/API 可读。完整启动检查还应确认 worker 日志出现 ready、浏览器能恢复历史对话、历史 PDF 可打开；涉及模型或检索修改时，另做对应真实调用。不要把端口监听等同于研究任务可执行。

日志：`/tmp/asteria-frontend.stdout`、`/tmp/asteria-frontend.stderr`、`/tmp/asteria-backend-8018.log`、`/tmp/asteria-research-worker.log`。这些日志可能保留旧错误，应按进程启动时间判断新故障。

## 必要时重载

文档修改不重启；前端普通源码更新交给开发服务器。后端代码需要重载时，先确认没有 active research Run 或 Coordinator turn，只重载受影响服务，不用广泛的 `pkill`。

```bash
# 仅在确认没有活动任务且需要加载 API 修改时执行
launchctl kickstart -k gui/$(id -u)/com.asteria.backend8018
```

修改 plist 时先 bootout 对应 job，确认 label 消失且端口释放，再 bootstrap 同一 plist。紧接 bootout 的 bootstrap 可能因旧 job 尚未移除返回 I/O error；先检查状态，不能据此改端口或以 root 再启动一份。维护后检查 HTTP 和进程实际工作目录。

## 手动调试入口

仅在对应托管服务已停止时使用，防止重复占用端口或并行启动未知 worker：

```bash
cd /Users/dora/Developer/asteria-agent
/Users/dora/miniconda3/envs/dora/bin/python scripts/start-research-service.py api
# 独立终端：
/Users/dora/miniconda3/envs/dora/bin/python scripts/start-research-service.py worker
# 独立终端：
bash scripts/start-workspace-frontend.sh
```

模型、数据库等配置来自本地 `.env`，前端配置来自 `.env.local`。手动启动还需保持与本机 plist 相同的鉴权配置；脚本本身不自动关闭鉴权。本机现有免登录模式只允许 loopback 开发使用，不用于共享部署。不要把密钥、数据库连接串或完整环境变量写入日志、文档和提交。

## 文件读取与云同步

2026-09-13 已证实旧 Documents 工作区的 `.next`、`node_modules`、`.env` 和 Git 对象出现 `dataless`，导致 Node 读取错误和 HTTP 500。关闭轮询或一次重新下载依赖无法阻止后续云端卸载。

- macOS 启动入口拒绝从 Documents、Desktop、`Library/Mobile Documents` 下运行，且解析真实路径以避免软链接绕回旧目录。这是项目的保守目录约束，不是自动检测系统是否开启 iCloud。
- 仓库、配置、依赖、构建目录与产物统一存于本地 Developer 目录；不要只移动 node_modules，却继续从云目录读取源码或 `.env`。
- `ls -lO <文件>` 可检查 dataless 标记；`scripts/check-frontend-files.cjs` 实际导入 Next/SWC 与 SSR 消毒依赖，启动前限制检查时间。
- 不在运行中清 `.next`，不并行执行覆盖相同 `.next` 的 build，不关闭 HTML 消毒。只有停下准确的前端进程后，才考虑隔离故障构建目录并重建。
- 依赖缺失按 lockfile 恢复，保持 Node 22；不升级 Next、不迁移 dora 来掩盖文件读取问题。
- Ollama、PostgreSQL 和外部模型网络分别诊断；文件可读并不代表这些依赖健康。Git 保持证书验证，本机仓库使用 dora CA，不修改全局代理和信任配置。

旧目录 `/Users/dora/Documents/项目/code/reference-repos/asteria-agent` 暂留作迁移备份，不再编辑或启动。迁移保留全部历史 outputs，并逐文件比对；数据库未迁移或重建。需要回退业务版本时在新目录操作 Git，不能回到已发生云端卸载的旧运行位置。迁移过程与验证边界见 `DEVELOPMENT_LOG.md`、`spec.md` §22.8。

## 知识库与外部 RAG 依赖

当前外部引擎根目录是 `/Users/dora/Developer/modular-rag-engine`，可用 `MODULAR_RAG_MCP_ROOT` 显式覆盖。上游为 `jerry-ai-dev/MODULAR-RAG-MCP-SERVER`，本机固定提交 `f658c5a4011c8b826707a65a3b11ce9301b0626f`。源码、settings和data必须一并留在本地可读位置；只迁移Asteria仓库不能解决外部引擎仍被iCloud卸载的问题。

2026-09-13从旧引擎复制约1.4GB原data（含Chroma、稀疏索引），按大小/mtime复核无差异，旧目录保留。旧索引环境使用Chroma1.5.9，已在dora安装同版并锁定项目依赖，补齐jieba0.42.1；`pip check`通过。不要直接安装另一Chroma版本打开原库，不为修复导入问题新建空库冒充恢复。新资料库与旧research_papers分collection，均依赖当前bge-m3和精排配置。

维护前除活动研究Run和Coordinator turn，还需检查 `knowledge_versions` 的queued/indexing状态。API索引消费者使用数据库锁，不额外启动另一个索引脚本；正常关闭会等待当前索引线程，强制退出则在下次启动标记中断，用户重传。已发布版本不因此撤销。向量清理由 `knowledge_vector_gc` 持久化重试，查询始终受数据库active_version约束。

故障定位顺序：源文件可读 → dora导入chromadb/jieba → PostgreSQL资料状态 → Ollama真实embedding → 配置的精排服务 → 主Chat问答。`ModuleNotFoundError: jieba`不能归因于模型余额或Agent规划；前端历史备份的`QuotaExceededError`也不是SSR文件读取错误，不应为此重装Next或清理运行中的.next。
