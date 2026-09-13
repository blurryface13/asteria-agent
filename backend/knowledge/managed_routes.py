"""Authenticated, user-facing knowledge library management."""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, Field, field_validator
from backend.auth.dependencies import get_current_user_email
from backend.auth.db import get_pool
from backend.knowledge import managed

router = APIRouter(prefix='/api/knowledge/libraries', tags=['knowledge libraries'])


class LibraryRequest(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    description: str = Field(default='',max_length=1200)

    @field_validator('name')
    @classmethod
    def name_required(cls, value):
        if not value.strip():
            raise ValueError('知识库名称不能为空')
        return value.strip()


@router.get('')
async def list_libraries(email=Depends(get_current_user_email)):
    return {'libraries': await managed.libraries(email)}


@router.post('',status_code=201)
async def create_library(body: LibraryRequest, email=Depends(get_current_user_email)):
    pool = await get_pool()
    return dict(await pool.fetchrow('INSERT INTO knowledge_bases(id,owner,name,description) VALUES($1,$2,$3,$4) RETURNING *',str(uuid4()), email, body.name, body.description))


@router.patch('/{kb_id}')
async def edit_library(kb_id: str, body: LibraryRequest, email=Depends(get_current_user_email)):
    await managed.get_library(email,kb_id)
    pool = await get_pool()
    return dict(await pool.fetchrow('UPDATE knowledge_bases SET name=$2,description=$3,updated_at=now() WHERE id=$1 RETURNING *',kb_id,body.name,body.description))


@router.get('/{kb_id}/documents')
async def list_documents(kb_id: str,email=Depends(get_current_user_email)):
    return {'documents': await managed.documents(email,kb_id)}


@router.post('/{kb_id}/documents',status_code=202)
async def upload_document(kb_id: str,file: UploadFile=File(...),email=Depends(get_current_user_email)):
    await managed.get_library(email,kb_id)
    try:
        payload=await file.read(64*1024*1024+1)
        return await managed.upload(email,kb_id,file.filename or '',payload)
    finally:
        await file.close()


@router.get('/{kb_id}/documents/{document_id}/source')
async def source(kb_id: str,document_id: str,email=Depends(get_current_user_email)):
    await managed.get_library(email,kb_id)
    pool=await get_pool()
    row=await pool.fetchrow('''SELECT v.payload,v.filename FROM knowledge_documents d
        JOIN knowledge_versions v ON v.id=d.active_version WHERE d.id=$1 AND d.kb_id=$2''',document_id,kb_id)
    if not row:
        raise HTTPException(404,'可用文档不存在')
    from urllib.parse import quote
    return Response(bytes(row['payload']),media_type='application/pdf' if row['filename'].lower().endswith('.pdf') else 'text/plain; charset=utf-8',
                    headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['filename'])})


@router.delete('/{kb_id}/documents/{document_id}',status_code=204)
async def delete_document(kb_id: str,document_id: str,email=Depends(get_current_user_email)):
    await managed.get_library(email,kb_id)
    pool=await get_pool()
    async with pool.acquire() as c,c.transaction():
        await c.execute('SELECT id FROM knowledge_bases WHERE id=$1 FOR UPDATE',kb_id)
        if not await c.fetchval('SELECT id FROM knowledge_documents WHERE id=$1 AND kb_id=$2 FOR UPDATE',document_id,kb_id):
            raise HTTPException(404,'文档不存在')
        if await c.fetchval("SELECT 1 FROM knowledge_versions WHERE document_id=$1 AND status IN ('queued','indexing')",document_id):
            raise HTTPException(409,'索引处理中，请完成后再删除')
        # Unpublish immediately and persist physical cleanup in the same transaction.
        await c.execute('''INSERT INTO knowledge_vector_gc(version_id,kb_id)
            SELECT id,$2 FROM knowledge_versions WHERE document_id=$1 ON CONFLICT DO NOTHING''', document_id,kb_id)
        await c.execute('DELETE FROM knowledge_documents WHERE id=$1',document_id)
        await c.execute('UPDATE knowledge_bases SET updated_at=now() WHERE id=$1',kb_id)


class ReportImport(BaseModel):
    conversation_id: str


@router.post('/{kb_id}/report',status_code=202)
async def import_report(kb_id: str,body: ReportImport,email=Depends(get_current_user_email)):
    await managed.get_library(email,kb_id)
    pool=await get_pool()
    report=await pool.fetchrow('SELECT id,answer FROM reports WHERE id=$1 AND user_email=$2',body.conversation_id,email)
    if not report:
        raise HTTPException(404,'报告不存在')
    return await managed.upload(email,kb_id,'report-'+report['id']+'.md',report['answer'].encode())
