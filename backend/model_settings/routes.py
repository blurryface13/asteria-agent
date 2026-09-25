from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.dependencies import require_admin
from .service import ROLES, MODELS, listing, save

router = APIRouter(prefix='/api/admin/agent-models', tags=['agent models'])


class Setting(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    api_key: str | None = Field(default=None, max_length=512)
    clear_key: bool = False


@router.get('')
async def list_settings(response: Response, _admin=Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    return {'roles': await listing(), 'models': MODELS}


@router.put('/{role}')
async def put_setting(role: str, body: Setting, response: Response, _admin=Depends(require_admin)):
    if role not in ROLES or body.model not in MODELS:
        raise HTTPException(422, '不支持该角色或模型')
    if body.api_key and body.clear_key:
        raise HTTPException(422, '不能同时设置和清除密钥')
    try:
        await save(role, body.model, body.api_key, body.clear_key)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    response.headers['Cache-Control'] = 'no-store'
    return {'roles': await listing(), 'models': MODELS}
