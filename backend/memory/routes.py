from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from backend.auth.dependencies import get_current_user_email
from backend.memory import service

router = APIRouter(prefix='/api/memory', tags=['workspace memory'])


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=90)
    content: str = Field(max_length=32768)
    version: str | None = Field(..., max_length=64)


class Delete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=90)
    version: str = Field(min_length=64, max_length=64)


@router.get('')
async def read(project_id: str | None = None, email=Depends(get_current_user_email)):
    return await service.list_files(email, project_id)


@router.put('')
async def save(body: Edit, email=Depends(get_current_user_email)):
    return await service.save(email, body.project_id, body.name, body.content, body.version)


@router.delete('')
async def delete(body: Delete, email=Depends(get_current_user_email)):
    return await service.remove(email, body.project_id, body.name, body.version)
