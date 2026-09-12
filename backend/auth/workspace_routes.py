from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth.dependencies import get_current_user_email
from backend.auth.workspace_models import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    MessageCreateRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
)
from backend.auth.workspace_store_pg import WorkspaceNotFound, workspace_store

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


def _not_found(exc: WorkspaceNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/skills")
async def list_skills(_email: str = Depends(get_current_user_email)):
    from asteria_researcher.agentic.skill_catalog import catalog
    from asteria_researcher.agentic.latex import format_profiles
    return {"skills": [{k: v for k, v in e.items() if k != "files"} for e in catalog()],
            "format_profiles": format_profiles()}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, _email: str = Depends(get_current_user_email)):
    from asteria_researcher.agentic.skill_catalog import skill_detail
    try:
        return skill_detail(skill_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Skill not found") from error


@router.get("/projects")
async def list_projects(_email: str = Depends(get_current_user_email)):
    return {"projects": await workspace_store.list_projects(_email)}


@router.post("/projects", status_code=201)
async def create_project(
    request: ProjectCreateRequest,
    _email: str = Depends(get_current_user_email),
):
    return await workspace_store.create_project(
        _email, request.name, request.workspace_path, request.settings
    )


@router.get("/projects/{project_id}")
async def get_project(project_id: str, _email: str = Depends(get_current_user_email)):
    try:
        return await workspace_store.get_project(project_id, _email)
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    _email: str = Depends(get_current_user_email),
):
    try:
        return await workspace_store.update_project(
            project_id,
            _email,
            request.name,
            request.workspace_path,
            request.settings,
        )
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, _email: str = Depends(get_current_user_email)):
    try:
        await workspace_store.delete_project(project_id, _email)
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.get("/conversations")
async def list_conversations(
    project_id: str | None = Query(default=None),
    _email: str = Depends(get_current_user_email),
):
    return {
        "conversations": await workspace_store.list_conversations(_email, project_id)
    }


@router.post("/conversations", status_code=201)
async def create_conversation(
    request: ConversationCreateRequest,
    project_id: str | None = Query(default=None),
    _email: str = Depends(get_current_user_email),
):
    try:
        return await workspace_store.create_conversation(
            _email,
            request.title,
            request.mode,
            request.metadata,
            project_id,
            request.id,
        )
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str, _email: str = Depends(get_current_user_email)
):
    try:
        return await workspace_store.get_conversation(conversation_id, _email)
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
    _email: str = Depends(get_current_user_email),
):
    try:
        return await workspace_store.rename_conversation(
            conversation_id, _email, request.title
        )
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str, _email: str = Depends(get_current_user_email)
):
    try:
        await workspace_store.delete_conversation(conversation_id, _email)
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str, _email: str = Depends(get_current_user_email)
):
    try:
        return {
            "messages": await workspace_store.list_messages(conversation_id, _email)
        }
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def append_message(
    conversation_id: str,
    request: MessageCreateRequest,
    _email: str = Depends(get_current_user_email),
):
    try:
        return await workspace_store.append_message(
            conversation_id,
            _email,
            request.role,
            request.content,
            request.metadata,
        )
    except WorkspaceNotFound as exc:
        raise _not_found(exc) from exc
