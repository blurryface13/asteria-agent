#!/bin/bash
# 本机启动 asteria-agent 前后端(不用 Docker)
# 用法: ./start-local.sh
set -e
cd "$(dirname "$0")"

# Keep loopback traffic out of Clash; external model/research traffic still
# follows the user's normal proxy configuration.
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

# Use the verified shared dora environment for every Python-side check and
# service. Do this before the Ollama preflight so startup never mixes Python
# runtimes.
PYTHON_ENV_DIR="/Users/dora/miniconda3/envs/dora"
if [ ! -x "$PYTHON_ENV_DIR/bin/python3" ]; then
  echo "未找到 dora Python 环境: $PYTHON_ENV_DIR" >&2
  exit 1
fi
export PATH="$PYTHON_ENV_DIR/bin:$PATH"

# Ollama(bge-m3 embedding,上下文压缩必需)——没跑就起,否则 research 会卡在 AGENT WORK 空转
if ! command -v ollama >/dev/null 2>&1; then
  echo "未找到 ollama 命令：请先安装 Ollama，并确保 ollama 在 PATH 中。" >&2
  exit 1
fi
if ! curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "启动 Ollama (bge-m3 embedding, :11434)..."
  OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 nohup ollama serve > /tmp/ollama.log 2>&1 &
  sleep 3
fi

# The web retriever can succeed while the later dense-compression stage is
# broken, which previously made a task appear to hang. Probe the exact model
# used by this project before starting the API so a bad Ollama runtime is
# reported at startup instead of halfway through a research run.
ollama_model="$(sed -n 's/^EMBEDDING=ollama://p' .env 2>/dev/null | head -n 1)"
ollama_model="${ollama_model:-bge-m3}"
ollama_version="$(ollama --version 2>/dev/null | awk '{print $NF}' | sed 's/^v//')"
ollama_major="${ollama_version%%.*}"
ollama_rest="${ollama_version#*.}"
ollama_minor="${ollama_rest%%.*}"
ollama_patch="${ollama_rest#*.}"
if [ "$ollama_major" = "0" ] && [ "$ollama_minor" = "23" ] && [ "${ollama_patch:-0}" -lt 3 ]; then
  echo "Ollama $ollama_version 过旧：macOS 26 需要至少 0.23.3，请先更新 Ollama。" >&2
  exit 1
fi

embedding_probe="$(curl --noproxy '*' -sS --max-time 30 -X POST http://127.0.0.1:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$ollama_model\",\"input\":[\"asteria embedding health check\"]}" 2>&1 || true)"
if ! printf '%s' "$embedding_probe" | grep -q '"embeddings"'; then
  echo "Ollama embedding 自检失败 (model=$ollama_model, version=${ollama_version:-unknown})。" >&2
  echo "$embedding_probe" | head -c 1200 >&2
  echo "请检查 /tmp/ollama.log，并在 macOS 26 上更新 Ollama 后重新启动。" >&2
  exit 1
fi
echo "Ollama embedding 自检通过 (model=$ollama_model, version=${ollama_version:-unknown})"

echo "启动后端 (uvicorn, :8000)..."
# weasyprint(PDF生成)需要 homebrew 的 pango 等原生库
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
export PYDANTIC_DISABLE_PLUGINS=1
# Local-only development mode: keep the real login flow available, but allow
# this machine's smoke tests to exercise the research path without email OTP.
# Do not enable this flag in a shared or production environment.
export ASTERIA_DEV_AUTH_BYPASS=1
export ASTERIA_DEV_AUTH_EMAIL="local@asteria.dev"
# Bound provider retries so a broken external route reports a task error
# instead of keeping the WebSocket in a loading state for several minutes.
export ASTERIA_LLM_MAX_ATTEMPTS=3
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
export NEXT_PUBLIC_ASTERIA_DEV_AUTH_BYPASS=1
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
