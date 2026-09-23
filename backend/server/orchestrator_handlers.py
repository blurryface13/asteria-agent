"""Authenticated application adapters; routing policy lives in AgentOrchestrator."""
import json
from backend.runs.routes import validate_request
from backend.runs.store import RunStore
from asteria_researcher.agentic.capabilities import PROFILES


def executors(model, config=None, progress=None):
    async def knowledge(req, intent):
        from backend.knowledge import managed
        allowed_ids = {k['id'] for k in req.knowledge_catalog}
        if not intent.knowledge_ids or not set(intent.knowledge_ids) <= allowed_ids:
            raise ValueError('AgentOrchestrator selected invalid library scope')
        query = intent.retrieval_query or req.message
        if req.knowledge_mode == 'selected' and req.history:
            query = await model(
                'Rewrite the latest question as a standalone retrieval query using conversation only for references. '
                'Do not answer. Return only the query.',
                json.dumps({'question':req.message,'history':req.history[-8:]},ensure_ascii=False))
        content, sources = await managed.answer(req.user_id,intent.knowledge_ids,query,model,req.history)
        lines = [f"[{s['index']}] {s['name']}" + (f" · 第{s['page']}页" if s['page'] else '') +
                 f" · 版本 {s['version_id'][:8]}" for s in sources]
        content = '\n'.join(line for line in content.splitlines() if line.strip() not in lines).rstrip()
        content += '\n\n' + '\n'.join(lines) if sources else ''
        return {'response':{'role':'assistant','content':content,'metadata':{
            'turn_id':req.request_id,'knowledge_ids':intent.knowledge_ids,'sources':sources,'retrieval_query':query}}}

    async def general(req, intent):
        from backend.server.specialists import run_general
        content, metadata = await run_general(req.message,req.history,model,req.report)
        return {'response':{'role':'assistant','content':content,'metadata':{**metadata,'turn_id':req.request_id}}}

    def specialist(role):
        async def invoke(req, intent):
            from backend.server.specialists import run_specialist
            content, metadata = await run_specialist(role,req.message,req.history,model,req.user_id,
                                                    req.knowledge_mode,progress=progress,
                                                    context={'orchestration':req.role_context})
            return {'response':{'role':'assistant','content':content,'metadata':{**metadata,'turn_id':req.request_id}}}
        return invoke

    async def research(req, intent):
        if req.research_request is None:
            return {}  # Compatible with clients requesting routing before submitting a durable run.
        request = {**req.research_request,'task':req.message,'coordinator_capability':intent.capability}
        run = await RunStore().submit(req.user_id,req.request_id,req.conv_id,validate_request(request))
        return {'run_id':run['id']}

    return {'general_chat':general, 'knowledge_chat':knowledge, 'research_lead':research, 'general_research':research,
            **{role:specialist(role) for role in PROFILES}}
