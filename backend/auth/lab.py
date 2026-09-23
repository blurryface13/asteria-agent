"""Small-lab account policy. Redis sessions are not conversational memory."""
import asyncio
import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import HTTPException

from backend.auth.db import get_pool

COOKIE = 'asteria_session'
SESSION_SECONDS = 8 * 60 * 60


def shared_mode():
    return os.getenv('ASTERIA_SHARED_MODE', '0') == '1'


def admin_email(email):
    return email.casefold() in {s.strip().casefold() for s in os.getenv('ASTERIA_ADMIN_EMAILS', '').split(',') if s.strip()}


def namespace():
    return os.getenv('ASTERIA_REDIS_NAMESPACE', 'asteria:lab:v1')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@asynccontextmanager
async def redis_connection():
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
    client = Redis.from_url(os.getenv('ASTERIA_REDIS_URL', 'redis://127.0.0.1:6379/4'),
                           socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
    try:
        yield client
    except RedisError as exc:
        raise HTTPException(503, '登录状态服务暂不可用，请稍后重试') from exc
    finally:
        await client.aclose()


async def throttle(key, limit, seconds):
    # INCR and expiry are one atomic operation, including the first request.
    async with redis_connection() as r:
        count = await r.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                             1, namespace() + ':rate:' + digest(key), seconds)
    if count > limit:
        raise HTTPException(429, '操作过于频繁，请稍后重试', headers={'Retry-After': str(seconds)})


def password_hash(password):
    if not 12 <= len(password) <= 128:
        raise ValueError('密码须为12至128个字符')
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64*1024*1024)
    return 'scrypt$' + salt.hex() + '$' + key.hex()


def password_matches(password, encoded):
    try:
        scheme, salt, expected = encoded.split('$')
        if scheme != 'scrypt' or not 12 <= len(password) <= 128:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**15, r=8, p=1, maxmem=64*1024*1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError, AttributeError):
        return False


async def issue_session(email, epoch):
    import json
    token = secrets.token_urlsafe(32)
    async with redis_connection() as r:
        await r.set(namespace() + ':session:' + digest(token), json.dumps({'email': email, 'epoch': epoch}), ex=SESSION_SECONDS)
    return token


async def session_email(token):
    import json
    if not token or len(token) > 512:
        return None
    async with redis_connection() as r:
        raw = await r.get(namespace() + ':session:' + digest(token))
    if not raw:
        return None
    try:
        value = json.loads(raw)
        pool = await get_pool()
        valid = await pool.fetchval('SELECT 1 FROM users WHERE email=$1 AND disabled=FALSE AND auth_epoch=$2', value['email'], value['epoch'])
        return value['email'] if valid else None
    except (KeyError, ValueError, TypeError):
        return None


async def revoke_session(token):
    if token:
        async with redis_connection() as r:
            await r.delete(namespace() + ':session:' + digest(token))


async def provision(email, password, display_name=''):
    encoded = await asyncio.to_thread(password_hash, password)
    pool = await get_pool()
    # Password reset invalidates existing sessions through the persisted epoch.
    return dict(await pool.fetchrow('''INSERT INTO users(email,display_name,password_hash)
        VALUES($1,$2,$3) ON CONFLICT(email) DO UPDATE SET password_hash=$3,
        display_name=$2,disabled=FALSE,auth_epoch=users.auth_epoch+1
        RETURNING email,display_name,disabled''', email.strip().casefold(), display_name, encoded))


async def check_shared_config():
    if not shared_mode():
        return
    if os.getenv('ASTERIA_DEV_AUTH_BYPASS', '0').lower() in {'1','true','yes'}:
        raise RuntimeError('Shared mode cannot enable local authentication bypass')
    if len(os.getenv('JWT_SECRET', '')) < 32 or not os.getenv('ASTERIA_ADMIN_EMAILS'):
        raise RuntimeError('Shared mode requires JWT_SECRET (32+ characters) and ASTERIA_ADMIN_EMAILS')
    async with redis_connection() as r:
        await r.ping()
