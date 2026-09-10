#!/bin/bash
# 本机启动 asteria-agent 前后端(不用 Docker)
# 用法: ./start-local.sh
set -e
cd "$(dirname "$0")"

# Keep loopback traffic out of Clash; external model/research traffic still
# follows the user's normal proxy configuration.
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

# Ollama(bge-m3 embedding,上下文压缩必需)——没跑就起,否则 research 会卡在 AGENT WORK 空转
if ! curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "启动 Ollama (bge-m3 embedding, :11434)..."
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  sleep 3
fi

echo "启动后端 (uvicorn, :8000)..."
# Use the verified shared dora environment instead of selecting a local
# virtualenv by directory presence.
PYTHON_ENV_DIR="/Users/dora/miniconda3/envs/dora"
if [ ! -x "$PYTHON_ENV_DIR/bin/python3" ]; then
  echo "未找到 dora Python 环境: $PYTHON_ENV_DIR" >&2
  exit 1
fi
export PATH="$PYTHON_ENV_DIR/bin:$PATH"
# weasyprint(PDF生成)需要 homebrew 的 pango 等原生库
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
export PYDANTIC_DISABLE_PLUGINS=1
# 不用 --reload:它默认监听整个项目目录,前端 .next 编译产物持续变化会把后端
# 拖进无限重载导致 :8000 不可用。本地用不需要热重载;改后端代码后重跑本脚本即可。
nohup "$PYTHON_ENV_DIR/bin/python3" -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/asteria-backend.log 2>&1 &
echo "  backend PID: $!  日志: /tmp/asteria-backend.log"

echo "启动多智能体服务 (langgraph dev, :2024,可选,只有要用 Multi Agents Report 才需要)..."
cd "$(dirname "$0")"
if [ -x "$PYTHON_ENV_DIR/bin/langgraph" ]; then
  nohup "$PYTHON_ENV_DIR/bin/langgraph" dev --port 2024 --config langgraph-multiagent.json --no-browser --no-reload --allow-blocking > /tmp/asteria-langgraph.log 2>&1 &
  echo "  langgraph PID: $!  日志: /tmp/asteria-langgraph.log"
else
  echo "  未启动 LangGraph: dora 环境缺少 langgraph CLI (需要 Multi Agents Report 时再安装 langgraph-cli)"
fi

echo "启动前端 (next dev, :3000)..."
cd frontend/nextjs
# 系统全局 node 是 v24,与 Next.js 14 不兼容(dev server 卡在 ESM 求值死锁)。
# 用 keg-only 的 node@22 启动,不影响全局 node。显式绑 127.0.0.1 避免 IPv6 监听导致连不上。
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
export NEXT_TELEMETRY_DISABLED=1
export WATCHPACK_POLLING=true
export WATCHPACK_POLL_INTERVAL=1000
nohup ./node_modules/.bin/next dev -H 127.0.0.1 -p 3000 > /tmp/asteria-frontend.log 2>&1 &
echo "  frontend PID: $!  日志: /tmp/asteria-frontend.log  (node $(node -v))"

# Next dev 会先监听端口，再生成 middleware-manifest 并编译首个页面。
# 在此之前访问会得到 Server Error；等待真实页面返回 200 后再报告启动完成。
echo "等待前端完成首次编译..."
frontend_ready=0
for attempt in $(seq 1 600); do
  if curl --noproxy '*' -sS --max-time 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/login | grep -q '^200$'; then
    frontend_ready=1
    break
  fi
  sleep 1
done

if [ "$frontend_ready" -ne 1 ]; then
  echo "前端在 600 秒内未完成首次编译,请查看 /tmp/asteria-frontend.log"
  exit 1
fi

echo ""
echo "前端: http://127.0.0.1:3000 (已完成首次页面编译)"
echo "后端: http://127.0.0.1:8000"
echo "多智能体服务: http://127.0.0.1:2024 (选 Multi Agents Report 前,先去 Preferences 里把这个地址填进 LangGraph Host URL)"
echo "停止: lsof -ti:8000,3000,2024 | xargs kill -9   (按端口杀,能一并清掉 next 的 worker 子进程)"
