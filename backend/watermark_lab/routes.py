"""HTTP API for the watermark experiment agent (AI4Science).

POST /api/watermark-lab/run: give an experiment instruction in natural
language; a ReAct agent orchestrates real embed/distort/extract runs on the
watermarking model and returns the trace, run metrics and a Markdown report.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user_email
from .tools import new_session
from .react_agent import run_experiment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watermark-lab", tags=["watermark-lab"])


class RunRequest(BaseModel):
    instruction: str = Field(min_length=5, max_length=2000)
    protocol: str | None = Field(default=None, max_length=100,
                                 description="declarative experiment protocol name, e.g. screen_robustness")


@router.post("/run")
async def run_lab_experiment(req: RunRequest, _email: str = Depends(get_current_user_email)):
    session = new_session()
    try:
        return await run_experiment(session, instruction=req.instruction, protocol=req.protocol)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"watermark lab run failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))
