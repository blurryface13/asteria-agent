"""Durable research adapters selected by AgentOrchestrator."""


def configured_model(config_path=None):
    from asteria_researcher.config.config import Config
    from asteria_researcher.utils.llm import create_chat_completion
    cfg = Config(config_path or None)
    import hashlib
    import json
    import os
    import asyncio
    from asteria_researcher.utils.usage_context import usage_stage
    embedding_instance = None
    selected_roles = None
    selection_lock = asyncio.Lock()
    async def intent_embeddings(texts):
        nonlocal embedding_instance
        import asyncio
        if embedding_instance is None:
            from asteria_researcher.memory.embeddings import Memory
            embedding_instance = await asyncio.to_thread(
                lambda: Memory(cfg.embedding_provider, cfg.embedding_model, **cfg.embedding_kwargs).get_embeddings())
        return await embedding_instance.aembed_documents(texts)

    async def model(system, user):
        import asyncio
        nonlocal selected_roles
        try:
            from backend.model_settings.service import snapshot
            # Auxiliary calls can be untagged and not every older stage has a
            # dedicated setting. The general role is the frontend-configured
            # fallback, so a fresh Docker install needs no provider key in .env.
            stage = usage_stage.get()
            async with selection_lock:
                if selected_roles is None:
                    selected_roles = await snapshot()
            selected_model, role_key = selected_roles.get(
                stage, selected_roles.get('general_chat', (cfg.smart_llm_model, None)))
            provider = 'deepseek' if selected_model in {'deepseek-chat', 'deepseek-reasoner'} else cfg.smart_llm_provider
            kwargs = dict(cfg.llm_kwargs)
            if role_key:
                kwargs['openai_api_key'] = role_key
            result = await asyncio.wait_for(create_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                model=selected_model, llm_provider=provider,
                temperature=0, max_tokens=int(os.getenv('ASTERIA_AGENT_MAX_OUTPUT_TOKENS', '12000')),
                llm_kwargs=kwargs), timeout=180)
            # Providers sometimes wrap valid structured JSON in a Markdown fence.
            # Remove only that transport wrapper; Pydantic still validates content.
            import re
            fenced = re.fullmatch(r"\s*```(?:json)?\s*\n([\s\S]*?)\n```\s*", result)
            return fenced[1] if fenced and "JSON" in system else result
        except Exception as error:
            cause = error
            while cause:
                if getattr(cause, "status_code", None) == 402:
                    raise RuntimeError("模型服务余额不足（HTTP 402），当前阶段已停止；已有草稿和证据保留，尚未完成最终交付。请充值或明确配置其他模型后重试。") from error
                cause = cause.__cause__
            raise
    # Only a hash is exposed to the process-local cache, not credentials/config values.
    model.routing_identity = hashlib.sha256(json.dumps({
        'provider':cfg.smart_llm_provider,'model':cfg.smart_llm_model,'kwargs':cfg.llm_kwargs,
        'embedding_provider':cfg.embedding_provider,'embedding_model':cfg.embedding_model,
        'embedding_kwargs':cfg.embedding_kwargs,
        'endpoints':{key:os.getenv(key) for key in ('OLLAMA_BASE_URL','OPENAI_BASE_URL','DEEPSEEK_BASE_URL')}
        },sort_keys=True,default=str).encode()).hexdigest()
    async def routing_identity():
        from backend.model_settings.service import revision
        current = await revision()
        return hashlib.sha256((model.routing_identity + ':' + current).encode()).hexdigest()
    model.routing_identity_hook = routing_identity
    model.intent_embeddings = intent_embeddings
    return model


async def run_agentic_task(query, capability, logs_handler, research_kwargs):
    if capability in {"literature_review", "experiment_design", "financial_research"}:
        return await run_autonomous_review(query, logs_handler, research_kwargs, capability=capability)
    if capability != "general_research":
        raise ValueError("Unknown research capability")
    # Ordinary web research shares the domain BaseAgent loop, not the historical
    # plan → sequential perspectives → periodic audit workflow.
    from pathlib import Path
    from backend.server.specialists import run_specialist
    from backend.server.specialists import search_public_sources
    from backend.finance.client import search as search_financial_sources
    from asteria_researcher.agentic.capabilities import Profile
    from asteria_researcher.agentic.latex import publish
    profile = Profile('general_research', '公开资料研究助手', '围绕请求自主检索公开资料、综合研究报告并标明来源限制',
                      '', ('search_public_sources',))
    # Never silently discard source restrictions from a durable research request.
    if research_kwargs.get('report_source') not in (None,'web') or research_kwargs.get('document_urls'):
        raise ValueError('公开资料角色仅支持网页研究；本地/指定文档请通过知识库问答入口处理')
    if research_kwargs.get('source_urls'):
        raise ValueError('公开资料角色尚不支持仅限指定网页的全文研究；请改用知识库或取消指定来源')
    domains = research_kwargs.get('query_domains') or []
    from urllib.parse import urlparse
    domains = [urlparse(d if '://' in d else 'https://' + d).hostname for d in domains]
    if any(not d for d in domains):
        raise ValueError('Invalid research domain restriction')
    async def scoped_search(query):
        suffix = ' (' + ' OR '.join('site:' + d for d in domains) + ')' if domains else ''
        rows = await search_public_sources(query + suffix)
        return [r for r in rows if not domains or any(
            (urlparse(r['url']).hostname or '') == d or (urlparse(r['url']).hostname or '').endswith('.'+d)
            for d in domains)]
    report, metadata = await run_specialist('general_research',query,[],
        configured_model(research_kwargs.get('config_path')),None,profile=profile,public_search=scoped_search,
        context={'tone':str(research_kwargs.get('tone','Objective')),'allowed_domains':domains})
    if not metadata.get('sources') or metadata.get('status') != 'answer':
        raise ValueError('未取得公开检索来源，不能将普通回答交付为已完成研究报告')
    await logs_handler.send_json({'type':'logs','content':'research_agent_result','output':metadata})
    logs_handler.artifact_paths = await publish(report,Path('outputs'),profile='academic')
    await logs_handler.send_json({'type':'report','output':report})
    return report




async def run_autonomous_review(query, logs_handler, research_kwargs, *, capability='literature_review'):
    from pathlib import Path
    from asteria_researcher.agentic.autonomous import AutonomousReview
    from asteria_researcher.agentic.latex import publish
    from asteria_researcher.config.config import Config
    from asteria_researcher.memory.embeddings import Memory
    cfg = Config(research_kwargs.get("config_path") or None)
    online_rag = getattr(logs_handler, "online_rag", True)
    async def emit(kind, payload):
        await logs_handler.send_json({"type": "logs", "content": kind, "output": payload})
    from backend.server.coding_tools import build_coding_tools
    from backend.server.research_tools import build_knowledge_search
    from backend.server.specialists import search_public_sources
    # Identity belongs to the durable server Run, never research_kwargs/model arguments.
    server_run = getattr(getattr(logs_handler, "websocket", None), "run", {})
    owner = server_run.get("user_email") if isinstance(server_run, dict) else None
    run_request = server_run.get("request", {}) if isinstance(server_run, dict) else {}
    knowledge_ids = run_request.get("knowledge_ids", []) if isinstance(run_request, dict) else []
    runtime = AutonomousReview(configured_model(research_kwargs.get("config_path")),
        Memory(cfg.embedding_provider, cfg.embedding_model, **cfg.embedding_kwargs).get_embeddings() if online_rag else None,
        emit, logs_handler.request_feedback, online_rag=online_rag,
        skill_options=getattr(logs_handler, "skill_options", None), coding_tools=build_coding_tools(owner),
        public_search=search_financial_sources if capability == 'financial_research' else search_public_sources,
        knowledge_search=build_knowledge_search(owner, knowledge_ids),
        capability=capability)
    from asteria_researcher.agentic.delivery_state import record_delivery
    runtime.folder.mkdir(parents=True, exist_ok=True)
    record_delivery(runtime.folder, 'pending')
    try:
        report = await runtime.run(query)
    except BaseException as error:
        import asyncio
        record_delivery(runtime.folder, 'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed',
                        error_type=type(error).__name__, failed_stage='research_or_citation')
        # Retain inspectable evidence even when research cannot be completed.
        diagnostics = {"diagnostic_" + p.stem.replace("-", "_"): str(p)
                       for p in runtime.folder.iterdir() if p.is_file() and p.suffix in {".json", ".jsonl", ".md"}}
        await logs_handler.send_json({"type": "diagnostic_paths", "output": diagnostics})
        raise
    await runtime.event("lead", "publish", "started", "编译 LaTeX 与 PDF")
    record_delivery(runtime.folder, 'publishing')
    try:
        artifacts = await publish(report, Path("outputs"), profile=runtime.format_profile, assets=runtime.figure_assets)
    except BaseException as error:
        import asyncio
        path = record_delivery(runtime.folder, 'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed',
                               error_type=type(error).__name__)
        await logs_handler.send_json({'type': 'diagnostic_paths', 'output': {
            'diagnostic_delivery': str(path), 'diagnostic_run': str(runtime.folder/'run.json'),
            'diagnostic_draft': str(runtime.folder/'report-with-citations.md')}})
        raise
    artifacts['delivery_state'] = str(record_delivery(runtime.folder, 'ready'))
    for key, path in runtime.figure_assets.items():
        artifacts['chart_' + path.stem] = str(path)
    artifacts["writing_selection"] = str(runtime.folder / "writing.json")
    artifacts.update({"citation_graph": str(runtime.folder / "citations.json"),
                      "events": str(runtime.folder / "events.jsonl"),
                      "evidence": str(runtime.folder / "evidence.json"),
                      "run_metadata": str(runtime.folder / "run.json"),
                      "review_plan": str(runtime.folder / "plan.json"),
                      "lead_decisions": str(runtime.folder / "lead-decisions.json"),
                      "working_memory": str(runtime.folder / "working-memory.json"),
                      "citation_review": str(runtime.folder / "citation-review.json"),
                      "citation_history": str(runtime.folder / "citation-history.json")})
    for key, filename in (("delegations", "delegations.json"), ("coding_results", "coding-results.json"),
                          ("research_requests", "research-requests.json"), ("implementation_review", "implementation-review.json"),
                          ("knowledge_sources", "knowledge-sources.json"),
                          ("data_analysis", "analysis.json"), ("tool_calls", "tool-calls.jsonl")):
        if (runtime.folder / filename).is_file():
            artifacts[key] = str(runtime.folder / filename)
    for artifact in sorted(runtime.folder.glob("subagent-*.json")):
        artifacts[artifact.stem.replace("-", "_")] = str(artifact)
    logs_handler.artifact_paths = artifacts
    await runtime.event("lead", "publish", "completed", "源码、PDF、引用图与研究轨迹已保存")
    await logs_handler.send_json({"type": "report", "output": report})
    return report
