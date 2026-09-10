# 本机启动方式(不用 Docker)

## 一键启动
```bash
./start-local.sh
```

## 手动启动(推荐调试时用,分两个终端窗口)

**终端 1 —— 后端**
```bash
cd /path/to/asteria-agent
source /Users/dora/miniconda3/bin/activate dora
uvicorn main:app --host 0.0.0.0 --port 8000
```

**终端 2 —— 前端**
```bash
cd /path/to/asteria-agent/frontend/nextjs
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
export WATCHPACK_POLLING=true
export WATCHPACK_POLL_INTERVAL=1000
npm run dev -- --hostname 127.0.0.1 --port 3000
```

**终端 3 —— 多智能体服务(可选,只有要用 Preferences 里的 "Multi Agents Report" 才需要起)**
```bash
cd /path/to/asteria-agent
source /Users/dora/miniconda3/bin/activate dora
langgraph dev --port 2024 --config langgraph-multiagent.json --no-browser --no-reload --allow-blocking
```
起来之后,去前端 Preferences 面板,把 Report Type 选成 "Multi Agents Report",下面会冒出一个 "LangGraph Host URL" 输入框(这个字段是我们自己补的,上游项目本身没做完整),填 `http://localhost:2024`,保存后就能用了。

## 访问地址
- 前端(Next.js,主要用这个):http://localhost:3000
- 后端 API + 内置经典 UI:http://localhost:8000
- 多智能体服务(LangGraph):http://localhost:2024

启动检查以 `/login`、`/docs` 和 `/openapi.json` 的实际 HTTP 返回为准；只看到端口被占用，不代表服务已经完成首次编译或可以访问。

## 停止服务
```bash
pkill -f "uvicorn main:app"
pkill -f "next dev"
pkill -f "langgraph dev"
```

## 说明
- 后端本地启动固定使用 dora 环境；改 Python 代码后重新运行启动命令
- 前端固定使用 Node 22；`WATCHPACK_POLLING=true` 用于规避 macOS 低 watcher 配额导致的 `EMFILE` 启动异常，改 `.ts`/`.tsx` 仍会自动热更新
- `.env` 放本地模型、搜索源、邮箱和鉴权配置；不要提交真实密钥
- `node_modules` 装过一次后长期保留,重启电脑后直接跑上面命令即可,不用重新安装依赖
- 多智能体服务用了单独一份配置 `langgraph-multiagent.json`(根目录下,不是 `multi_agents/langgraph.json`),因为 `multi_agents/agent.py` 用绝对导入(`from multi_agents.agents import ...`),必须从仓库根目录起、且 `--config` 里的路径要相对根目录写,两者对不上默认配置,所以单独建了一份改好路径的
- `langgraph dev` 必须加 `--no-reload`(默认的热重载会把 dora 里几万个文件也当源码监视,一直触发重启打断任务)和 `--allow-blocking`(默认会拦截一切同步 IO,第三方库 `fake_useragent` 读本地文件是同步的,不加这个参数会直接报错)
- 当前 dora 环境若没有 `langgraph` 可执行文件,普通科研主流程仍可启动；使用 `Multi Agents Report` 前需额外安装 LangGraph CLI
