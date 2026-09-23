import asyncio
from fastapi import APIRouter,Depends
from pydantic import BaseModel
from backend.auth.dependencies import get_current_user_email
from backend.auth.db import get_pool
from backend.files import service

router=APIRouter(prefix='/api/workspace-files',tags=['workspace files'])
class Decision(BaseModel):
    approve:bool

@router.get('')
async def files(email=Depends(get_current_user_email)):
    pool=await get_pool()
    rows=await pool.fetch('''SELECT id,path,operation,content,before_content,state,error,created_at,
        created_at>now()-interval '1 day' AS fresh FROM file_proposals WHERE user_email=$1 ORDER BY created_at DESC LIMIT 40''',email)
    return {'files':await asyncio.to_thread(service.listing,email),'proposals':[dict(r) for r in rows]}

@router.get('/content')
async def content(name:str,email=Depends(get_current_user_email)):
    return await asyncio.to_thread(service.read,email,name)

@router.post('/proposals/{id}')
async def decide(id:str,body:Decision,email=Depends(get_current_user_email)):
    return await service.resolve(email,id,body.approve)
