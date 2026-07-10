"""HTTP API for the document-editing agent.

Flow: upload -> revise (runs the ReAct loop, returns proposed edits + trace) ->
apply (user-confirmed, writes a copy). Same JWT auth as every other route.
"""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user_email
from .tools import DocSession, apply_edit
from .react_agent import run_react

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/doc-agent", tags=["doc-agent"])

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "outputs" / "doc_agent"
_SESSIONS: dict[str, DocSession] = {}
_ALLOWED = {".tex", ".txt", ".md", ".docx"}


class ReviseRequest(BaseModel):
    session_id: str
    file: str
    instruction: str = Field(min_length=3, max_length=2000)


class ApplyRequest(BaseModel):
    session_id: str
    edit_id: str


def _get_session(session_id: str) -> DocSession:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("/upload")
async def upload_document(file: UploadFile = File(...),
                          _email: str = Depends(get_current_user_email)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"unsupported type {suffix}; allowed: {sorted(_ALLOWED)}")
    session_id = uuid.uuid4().hex[:12]
    workspace = WORKSPACE_ROOT / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "document").name
    dest = workspace / safe_name
    dest.write_bytes(await file.read())
    _SESSIONS[session_id] = DocSession(session_id=session_id, workspace=workspace)
    return {"session_id": session_id, "file": safe_name}


@router.post("/revise")
async def revise_document(req: ReviseRequest, _email: str = Depends(get_current_user_email)):
    session = _get_session(req.session_id)
    session.trace = []
    try:
        result = await run_react(session, instruction=req.instruction, file_path=req.file)
    except Exception as e:
        logger.error(f"doc-agent revise failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    return result


@router.post("/apply")
async def apply_document_edit(req: ApplyRequest, _email: str = Depends(get_current_user_email)):
    session = _get_session(req.session_id)
    try:
        return await apply_edit(session, req.edit_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="edit not found")
    except Exception as e:
        logger.error(f"doc-agent apply failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
