"""Disposable, user-scoped recent context cache. PostgreSQL remains authoritative."""
import json
import logging
from backend.auth.lab import redis_connection, namespace, digest

logger=logging.getLogger(__name__)


async def recent(pool,email,conversation_id):
    # Validate ownership and revision before any cache read, including after delete.
    revision=await pool.fetchrow('''SELECT c.updated_at,(SELECT coalesce(max(sequence_no),0)
        FROM workspace_messages m WHERE m.conversation_id=c.id) AS seq
        FROM workspace_conversations c WHERE c.id=$1 AND c.user_email=$2''',conversation_id,email)
    if not revision:
        from fastapi import HTTPException
        raise HTTPException(404,'Conversation not found')
    key=namespace()+':working:'+digest(email+':'+conversation_id)
    version=str(revision['seq'])+':'+revision['updated_at'].isoformat()
    try:
        async with redis_connection() as r:
            raw=await r.get(key)
        value=json.loads(raw) if raw else None
        if value and value['version']==version:
            from datetime import datetime
            return [dict(m,created_at=datetime.fromisoformat(m['created_at'])) for m in value['messages']]
    except Exception:
        logger.warning('Working context cache unavailable; reading PostgreSQL')
    rows=[dict(m) for m in await pool.fetch('''SELECT * FROM (SELECT role,content,created_at,sequence_no
        FROM workspace_messages WHERE conversation_id=$1 ORDER BY sequence_no DESC LIMIT 60) recent ORDER BY sequence_no''',conversation_id)]
    try:
        async with redis_connection() as r:
            await r.set(key,json.dumps({'version':version,'messages':rows},default=str),ex=86400)
    except Exception:
        logger.warning('Working context cache write skipped; PostgreSQL unaffected')
    return rows
