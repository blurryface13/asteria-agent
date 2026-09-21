"""No host Shell or arbitrary paths. Approval is only exposed to HTTP users."""
import asyncio
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from backend.auth.db import get_pool
from backend.memory.service import root,key,locked

LIMIT=256*1024
SUFFIXES={'.md','.txt','.json','.csv','.py','.js','.ts','.tex'}


def directory(email):
    return root()/'users'/key(email)/'files'


def target(email,name):
    # A flat scratch workspace deliberately avoids arbitrary-directory attacks.
    if not re.fullmatch(r'[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff_. -]{0,119}',name) or '..' in name or Path(name).suffix.lower() not in SUFFIXES:
        raise HTTPException(422,'只允许专用目录中的文本文件名，例如 notes.md 或 analysis.py，不允许路径或隐藏文件')
    path=directory(email)/name
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise HTTPException(409,'不允许符号链接')
    return path


def read(email,name):
    path=target(email,name)
    if not path.exists():
        return {'name':name,'content':'','version':None,'exists':False}
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as file:
        info=os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise HTTPException(409,'只允许普通文本文件，不允许链接')
        raw=file.read(LIMIT+1)
    if len(raw)>LIMIT:
        raise HTTPException(413,'文件不得超过256KiB')
    try:
        text=raw.decode('utf-8')
    except UnicodeError:
        raise HTTPException(422,'文件必须为UTF-8文本')
    return {'name':name,'content':text,'version':hashlib.sha256(raw).hexdigest(),'exists':True}


def listing(email):
    base=directory(email)
    target(email,'boundary-check.txt')
    if not base.exists(): return []
    result=[]
    for path in sorted(base.iterdir()):
        if len(result)>=100: break
        try:
            item=read(email,path.name)
            result.append({k:item[k] for k in ('name','version','exists')})
        except HTTPException: continue
    return result


async def propose(email,name,content='',operation='write',expected_version=None):
    if operation not in {'write','delete'} or len(content.encode())>LIMIT:
        raise HTTPException(422,'变更类型或大小不合法')
    before=await asyncio.to_thread(read,email,name)
    if before['version']!=expected_version:
        raise HTTPException(409,'版本已变化，请先读取文件后重新提案')
    if operation=='delete' and not before['exists']:
        raise HTTPException(404,'文件不存在')
    pool=await get_pool()
    async with pool.acquire() as c,c.transaction():
        await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','file-proposals:'+email)
        count=await c.fetchval("SELECT count(*) FROM file_proposals WHERE user_email=$1 AND state='pending' AND created_at>now()-interval '1 day'",email)
        if count>=20: raise HTTPException(429,'待确认文件提案已达20个，请先处理')
        id=uuid4().hex
        await c.execute('''INSERT INTO file_proposals(id,user_email,path,operation,content,expected_version,before_content)
            VALUES($1,$2,$3,$4,$5,$6,$7)''',id,email,name,operation,content,expected_version,before['content'])
    return {'id':id,'path':name,'operation':operation,'status':'pending','instruction':'尚未修改文件；请用户打开工作台的文件提案页面确认。'}


def apply_file(email,row):
    base=directory(email)
    with locked(base):
        before=read(email,row['path'])
        if before['version']!=row['expected_version']:
            raise HTTPException(409,'文件已被修改，请重新提案，未覆盖现有内容')
        path=target(email,row['path'])
        if row['operation']=='delete':
            # Recoverable deletion. The backup stays inside the private workspace.
            trash=base/'.trash'
            if trash.is_symlink(): raise HTTPException(409,'回收目录不允许链接')
            trash.mkdir(mode=0o700,exist_ok=True)
            os.replace(path,trash/(row['id']+'-'+path.name))
        else:
            fd,tmp=tempfile.mkstemp(prefix='.write-',dir=base)
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as out:
                    out.write(row['content']);out.flush();os.fsync(out.fileno())
                target(email,row['path'])
                os.replace(tmp,path)
            finally:
                if Path(tmp).exists(): Path(tmp).unlink()


async def resolve(email,id,approve):
    pool=await get_pool()
    error=None
    async with pool.acquire() as c,c.transaction():
        row=await c.fetchrow('SELECT *,created_at>now()-interval \'1 day\' AS fresh FROM file_proposals WHERE id=$1 AND user_email=$2 FOR UPDATE',id,email)
        if not row: raise HTTPException(404,'提案不存在')
        if row['state']!='pending': return {'state':row['state']}
        if not row['fresh']: raise HTTPException(409,'提案已过期，请重新提交')
        state='rejected'
        if approve:
            try:
                work=asyncio.create_task(asyncio.to_thread(apply_file,email,dict(row)))
                try: await asyncio.shield(work)
                except asyncio.CancelledError:
                    await work  # Do not roll back DB while a write thread is still running.
                state='applied'
            except Exception as exc:
                state='failed';error=str(exc.detail) if isinstance(exc,HTTPException) else '文件变更失败，请检查状态后重新提案'
        await c.execute('UPDATE file_proposals SET state=$2,error=$3,resolved_at=now() WHERE id=$1',id,state,error)
    if error: raise HTTPException(409,error)
    return {'state':state}
