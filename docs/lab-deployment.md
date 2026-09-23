# 实验室部署与登录排查

本页针对十余位实验室成员的小范围部署。默认采用管理员预置账号＋密码登录；邮件验证码不是首次运行的必需依赖。不要把示例配置中的空密钥或本机回环地址直接当成可供他人访问的服务。

## 克隆到正确的代码

先在 GitHub 仓库页面确认默认分支和最新提交；克隆后在仓库内运行：

```sh
git branch --show-current
git log -1 --oneline
git status --short
```

启动前核对提交是否包含 `backend/memory/vector_index.py`、`backend/auth/lab.py` 和 `frontend/nextjs/app/login/page.tsx`。若没有，克隆的是旧分支或旧提交。不要把本机未提交的功能视为 GitHub 已发布版本，也不要靠复制 `.env` 补偿旧代码。需要升级时先保存本地配置、数据库和工作区数据，再拉取目标分支并重新启动 API、worker 和前端。

## 环境与账号

1. 按项目现有 Python/Node 依赖安装方式准备 Python 环境、Node.js 22、PostgreSQL、Redis 和 Ollama；执行 `ollama pull bge-m3`。论文知识库还依赖独立的 modular-rag-engine 服务，若要验证 RAG 需按其文档另行启动。本仓库目前**没有可直接使用的完整 Docker Compose 部署包**。
2. 复制仓库根目录 `.env.example` 为 `.env`，填写实际 `DATABASE_URL`、32 字符以上的 `JWT_SECRET`、`ASTERIA_ADMIN_EMAILS`、Redis 地址及模型配置。建议使用独立的 `ASTERIA_WORKSPACES_ROOT` 持久化目录；Chroma 索引目录应可写且持久保存，勿提交到 Git。
3. 共享环境维持 `ASTERIA_SHARED_MODE=1`、`ASTERIA_DEV_AUTH_BYPASS=0`、`ASTERIA_EMAIL_LOGIN_ENABLED=0`。在 API 启动后运行 `python scripts/manage-lab.py account --email <管理员邮箱>`，在交互提示里设置密码；成员账号由管理员登录后在账号页面创建。勿把密码放进命令参数或文档。
4. API、独立 worker 分别使用 `python scripts/start-research-service.py api`、`python scripts/start-research-service.py worker` 启动；在 macOS/Linux 中用 `bash scripts/start-workspace-frontend.sh` 启动前端。前端脚本使用已安装的 Node.js 22，需先在 `frontend/nextjs` 安装 npm 依赖。Windows 可用 Node.js 22 在该目录执行 `npm run dev -- --hostname 127.0.0.1 --port 3023`，并在启动前设置同样的环境变量。Python 脚本从仓库根目录读取 `.env`，若存在本地 `.env.lab` 则其配置优先；该文件不会提交到 Git。

若在另一台电脑访问前端，`NEXT_PUBLIC_ASTERIA_API_URL` 必须指向**浏览器可访问的 API 地址**，不能仍填 `127.0.0.1`。远程共享时还需配置 HTTPS 反向代理或受限内网地址、相应的 `CORS_ALLOW_ORIGINS`，并确认 API/前端监听地址与防火墙。`ASTERIA_API_HOST` 和 `ASTERIA_FRONTEND_HOST` 默认为 `127.0.0.1`，仅适用于本机或反向代理；不建议将未设防的开发服务直接暴露公网。前端改动公开环境变量后需重启/重建。

## 先做的两项检查

```sh
curl -fsS http://127.0.0.1:8018/health
curl -fsS http://127.0.0.1:8018/api/auth/config
```

预期健康状态为 `ok`，配置里 `password_login=true`、`email_login=false`。再从浏览器登录一个管理员预置账号，确认可看到自己的项目，另一普通成员不可查看管理员私有项目。

旧版“点击发送验证码没反应”不能只靠按钮外观定位。打开浏览器开发者工具的 Network，查看 `POST /api/auth/send-code`：请求根本未发出，先查前端校验和 JavaScript 错误；请求发到了浏览器自身的 `127.0.0.1` 或错误端口，修正 API URL；返回 500，查后端日志、数据库和 SMTP 配置；返回 409，表示当前部署已切换密码登录且未开放邮箱验证码；返回 200 但没收到邮件，再查 SMTP 发件及垃圾箱。新账号模式不要求每个成员配置 SMTP。

## 测试前的边界

先完成两账号隔离、登录/注销、项目与会话归属、后台任务、记忆召回和公共知识库的功能验收，再对任务提交与进度查询做有限负载测试。真实模型的端到端评测与接口替身压测分开，避免把模型排队和 API 吞吐混算。现有单元/合同测试不等同于已验证十余人生产容量。
