# 🐰 Asteria Agent

> 本地优先的 AI 调研助手:输入一个问题,它会自动拆解子查询、联网检索、阅读来源,产出一份带真实引用的调研报告——生成后还可以继续与报告对话。

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-core-1C3C3C?logo=langchain&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-FF6F61)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-storage-4169E1?logo=postgresql&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-bge--m3-white?logo=ollama&logoColor=black)

## ✨ 功能特性

| | 特性 | 实现方式 |
|---|---|---|
| 🔍 | **可溯源联网调研** | LLM 生成子查询 → 多引擎检索 → 全文抓取 → embedding 相关性过滤 → 带引用写作;引用列表来自独立维护的 `visited_urls` 真实访问记录,而非 LLM 输出,杜绝编造链接 |
| 🤖 | **多智能体模式** | LangGraph `StateGraph` 编排 planner / researcher / writer / fact-checker 角色,支持大纲人工审核(human-in-the-loop)与章节级并行深挖 |
| 🔐 | **免密码登录** | 邮箱验证码 → JWT(HS256)→ FastAPI `Depends()` 路由守卫;WebSocket 经 query 参数鉴权,4401 关闭码正确传递到浏览器 |
| 🗄️ | **按用户隔离的持久化** | 调研历史存 PostgreSQL,行级归属过滤,用户只能看到自己的数据 |
| 📡 | **实时进度推送** | WebSocket 将每个调研步骤(检索中、抓取中、写作中)实时流式推送到前端 |
| 💬 | **与报告对话** | 对任意已生成的报告继续追问 |
| 🖥️ | **本地优先、低成本** | 生成用 DeepSeek,embedding 用本地 Ollama `bge-m3`(免费、离线、中英双语),检索用 DuckDuckGo(无需 API key) |
| 📄 | **多格式导出** | 每份报告同时产出 Markdown + Word + PDF |

## 📸 界面预览

<!-- TODO: screenshots
![Home](assets/readme/home.png)
![Research in progress](assets/readme/research-live.png)
![Multi-agent workflow](assets/readme/multi-agent.png)
-->

*截图即将补充。*

## 🏗️ 架构

```mermaid
flowchart LR
    UI["Next.js UI"] -->|"REST + WebSocket"| API["FastAPI Backend"]
    API --> Auth["邮箱验证码 + JWT"]
    API --> Store[("PostgreSQL<br/>reports / users")]
    API --> Runtime["调研引擎<br/>(asteria_researcher)"]
    Runtime --> Retrieval["Retrievers<br/>DuckDuckGo / MCP / 本地文档"]
    Runtime --> Embed["Ollama bge-m3<br/>相关性过滤"]
    Runtime --> LLM["DeepSeek<br/>(任意 LangChain provider)"]
    UI --> Graph["LangGraph Service"]
    Graph --> Agents["planner / researcher<br/>writer / fact-checker"]
    Agents --> Runtime
```

代码库沿一条清晰的边界拆分:

- **`asteria_researcher/`** — 自包含的调研引擎(检索、抓取、prompt、LLM 抽象、报告写作),完全不感知 Web 层,可作为纯 Python 库独立使用
- **`backend/`** — 包在引擎外面的 FastAPI 服务层:路由、鉴权、WebSocket 推送、PostgreSQL 持久化
- **`frontend/nextjs/`** — Web 界面:调研控制台、实时日志、报告阅读、对话
- **`multi_agents/`** — LangGraph 多智能体工作流(planner → 人工审核 → 并行 researcher → writer → fact-checker)

## 🗺️ Roadmap

- [ ] **实验室知识库(RAG)** — 基于 pgvector 对内部文献与笔记做混合检索(BM25 + dense + RRF 融合),cross-encoder 重排序,封装为 MCP server 供本应用与其他 agent 共同调用
- [ ] 检索评估集与指标对比(hybrid vs. dense-only)
- [ ] 生产部署(Docker、`next build`、云主机)
- [ ] 成本看板(单次调研的 token / 费用明细)

## 🙏 致谢

基于优秀的开源项目 [GPT Researcher](https://github.com/assafelovic/gpt-researcher) 的思路与实现模式构建,并围绕本地优先工作流、按用户持久化与不同的鉴权/存储架构进行了重塑。
