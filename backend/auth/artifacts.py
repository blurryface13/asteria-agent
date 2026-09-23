"""Authenticated artifact access; clients cannot create ownership by saving a URL."""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from backend.auth.dependencies import get_current_user_email, _local_auth_bypass_enabled
from backend.auth.db import get_pool

router = APIRouter()


def output_path(relative):
    root = Path('outputs').absolute()
    path = root / relative
    if not relative or '\\' in relative or '..' in Path(relative).parts or Path(relative).is_absolute():
        raise HTTPException(404, '文件不存在')
    if any(p.is_symlink() for p in [path, *path.parents]) or not path.resolve().is_relative_to(root.resolve()):
        raise HTTPException(404, '文件不存在')
    if not path.is_file():
        raise HTTPException(404, '文件不存在')
    return path


@router.get('/outputs/{relative:path}')
async def output(relative: str, email=Depends(get_current_user_email)):
    path = output_path(relative)
    stored_path = 'outputs/' + str(Path(relative))
    if not _local_auth_bypass_enabled():
        pool = await get_pool()
        owned = await pool.fetchval('''SELECT 1 FROM research_artifacts a JOIN research_runs r ON r.id=a.run_id
            WHERE r.user_email=$1 AND a.path=$2 UNION ALL
            SELECT 1 FROM legacy_artifact_owners WHERE user_email=$1 AND path=$2 LIMIT 1''',email,stored_path)
        if not owned:
            raise HTTPException(404,'文件不存在或无访问权限')
    # Untrusted generated text must not execute as same-origin HTML.
    media = 'application/pdf' if path.suffix.lower()=='.pdf' else 'text/plain; charset=utf-8'
    if path.suffix.lower()=='.docx':
        media='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return FileResponse(path,media_type=media,headers={'Cache-Control':'private, no-store',
        'X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'"})
