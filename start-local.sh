#!/bin/bash
# 本机启动 gpt-researcher 前后端(不用 Docker)
# 用法: ./start-local.sh
set -e
cd "$(dirname "$0")"

echo "启动后端 (uvicorn --reload, :8000)..."
source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > /tmp/gptr-backend.log 2>&1 &
echo "  backend PID: $!  日志: /tmp/gptr-backend.log"

echo "启动多智能体服务 (langgraph dev, :2024,可选,只有要用 Multi Agents Report 才需要)..."
cd "$(dirname "$0")"
source .venv/bin/activate
nohup langgraph dev --port 2024 --config langgraph-multiagent.json --no-browser --no-reload --allow-blocking > /tmp/gptr-langgraph.log 2>&1 &
echo "  langgraph PID: $!  日志: /tmp/gptr-langgraph.log"

echo "启动前端 (next dev, :3000)..."
cd frontend/nextjs
nohup npm run dev > /tmp/gptr-frontend.log 2>&1 &
echo "  frontend PID: $!  日志: /tmp/gptr-frontend.log"

echo ""
echo "前端: http://localhost:3000"
echo "后端: http://localhost:8000"
echo "多智能体服务: http://localhost:2024 (选 Multi Agents Report 前,先去 Preferences 里把这个地址填进 LangGraph Host URL)"
echo "停止: pkill -f 'uvicorn main:app' ; pkill -f 'next dev' ; pkill -f 'langgraph dev'"
