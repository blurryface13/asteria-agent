from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from backend.auth.dependencies import get_current_user_email
from backend.runs.store import RunStore

router = APIRouter(prefix='/api/workspace/runs', tags=['research runs'])
store = RunStore()


class Submission(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    request: dict[str, Any]


def validate_request(request):
    from asteria_researcher.agentic.skill_catalog import SkillOptions
    if not isinstance(request.get('task'), str) or not request['task'].strip():
        raise HTTPException(422, 'task is required')
    if len(request['task']) > 50000 or not isinstance(request.get('report_type'), str):
        raise HTTPException(422, 'invalid research request')
    if type(request.get('online_rag', True)) is not bool:
        raise HTTPException(422, 'online_rag must be boolean')
    try:
        SkillOptions(skill_ids=request.get('skill_ids', []), format_profile=request.get('format_profile'))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Requests must not persist provider keys, bearer headers or MCP secrets.
    # Such credentials belong in server configuration, never in job payloads.
    headers = request.get('headers', {})
    if not isinstance(headers, dict) or not isinstance(headers.get('retrievers', ''), str):
        raise HTTPException(422, 'headers.retrievers must be a string')
    if set(headers) - {'retrievers'} or request.get('mcp_configs'):
        raise HTTPException(422, '后台任务凭据须在服务端配置；暂不接受自定义 headers/MCP 配置持久化')
    for key in ('source_urls', 'document_urls', 'query_domains'):
        values = request.get(key, [])
        if not isinstance(values, list) or len(values) > 200 or any(not isinstance(v, str) for v in values):
            raise HTTPException(422, f'{key} must be a list of strings (at most 200)')
    allowed = {'task','report_type','report_source','tone','headers','search_strategy','online_rag','skill_ids','format_profile','query_domains','mcp_enabled','mcp_strategy','mcp_configs','source_urls','document_urls','max_search_results'}
    if set(request) - allowed:
        raise HTTPException(422, 'unknown research request fields')
    return request


@router.post('')
async def submit(body: Submission, email=Depends(get_current_user_email)):
    return await store.submit(email, body.request_id, body.conversation_id, validate_request(body.request))


@router.get('/latest')
async def latest(conversation_id: str, email=Depends(get_current_user_email)):
    return {'run': await store.latest(email, conversation_id)}


@router.get('/{run_id}')
async def get(run_id: str, email=Depends(get_current_user_email)):
    return await store.get(email, run_id)


@router.get('/{run_id}/events')
async def events(run_id: str, after: int = Query(0, ge=0), email=Depends(get_current_user_email)):
    return {'events': await store.events(email, run_id, after)}


@router.post('/{run_id}/cancel')
async def cancel(run_id: str, email=Depends(get_current_user_email)):
    await store.cancel(email, run_id)
    return await store.get(email, run_id)


class Feedback(BaseModel):
    content: str | None = Field(default=None, max_length=10000)


@router.post('/{run_id}/approvals/{approval_id}')
async def feedback(run_id: str, approval_id: str, body: Feedback, email=Depends(get_current_user_email)):
    await store.answer(email, run_id, approval_id, body.content)
    return {'saved': True}
