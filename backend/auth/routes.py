"""Administrator-provisioned accounts and revocable Redis sessions."""
import logging
import asyncio
import hashlib
import hmac
import os

from fastapi import APIRouter, HTTPException, Depends, Request, Response

from backend.auth.db import get_pool
from backend.auth.email_service import generate_code, send_verification_code
from backend.auth.models import SendCodeRequest, VerifyCodeRequest, AuthResponse, CurrentUser, PasswordLogin, AccountCreate
from backend.auth.dependencies import get_current_user_email, require_admin
from backend.auth import lab

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

CODE_EXPIRE_MINUTES = 10


@router.get('/config')
async def config():
    return {'password_login': True, 'email_login': os.getenv('ASTERIA_EMAIL_LOGIN_ENABLED','0')=='1'}


async def auth_response(user, response):
    token = await lab.issue_session(user['email'], user['auth_epoch'])
    response.set_cookie(lab.COOKIE, token, max_age=lab.SESSION_SECONDS, httponly=True,
                        secure=os.getenv('ASTERIA_COOKIE_SECURE', '0') == '1', samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return AuthResponse(access_token=token, email=user['email'], is_new_user=False)


async def login_limits(email, request):
    ip = request.client.host if request.client else 'unknown'
    await lab.throttle('login-ip:' + ip, 60, 300)
    await lab.throttle('login-email:' + email, 10, 300)


@router.post('/login', response_model=AuthResponse)
async def password_login(req: PasswordLogin, request: Request, response: Response):
    await login_limits(req.email, request)
    pool = await get_pool()
    user = await pool.fetchrow('SELECT email,password_hash,disabled,auth_epoch FROM users WHERE email=$1', req.email)
    # Do equivalent work for nonexistent accounts, never reveal which emails exist.
    encoded = user['password_hash'] if user and user['password_hash'] else 'scrypt$' + '00'*16 + '$' + '00'*64
    valid = await asyncio.to_thread(lab.password_matches, req.password, encoded)
    if not valid or not user or user['disabled']:
        raise HTTPException(401, '邮箱或密码错误，或账号不可用')
    await pool.execute('UPDATE users SET last_login_at=now() WHERE email=$1', req.email)
    return await auth_response(user, response)


@router.post('/logout', status_code=204)
async def logout(request: Request, response: Response):
    authorization = request.headers.get('authorization', '')
    token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else request.cookies.get(lab.COOKIE)
    await lab.revoke_session(token)
    response.delete_cookie(lab.COOKIE, path='/')


@router.get('/accounts')
async def accounts(_admin=Depends(require_admin)):
    pool = await get_pool()
    return {'accounts': [dict(row) for row in await pool.fetch('SELECT email,display_name,disabled,last_login_at FROM users ORDER BY created_at')]}


@router.post('/accounts', status_code=201)
async def create_account(body: AccountCreate, _admin=Depends(require_admin)):
    # Existing account updates require the explicit reset endpoint.
    pool = await get_pool()
    encoded = await asyncio.to_thread(lab.password_hash, body.password)
    row = await pool.fetchrow('''INSERT INTO users(email,display_name,password_hash) VALUES($1,$2,$3)
        ON CONFLICT(email) DO NOTHING RETURNING email,display_name,disabled''', body.email,body.display_name,encoded)
    if not row:
        raise HTTPException(409, '账号已存在，请使用密码重置')
    return dict(row)


@router.post('/accounts/reset-password')
async def reset_password(body: AccountCreate, _admin=Depends(require_admin)):
    pool=await get_pool()
    if not await pool.fetchval('SELECT 1 FROM users WHERE email=$1',body.email):
        raise HTTPException(404,'账号不存在')
    return await lab.provision(body.email,body.password,body.display_name)


@router.post('/accounts/{email}/disable')
async def disable_account(email: str, admin=Depends(require_admin)):
    if email.casefold() == admin.casefold() or lab.admin_email(email):
        raise HTTPException(409, '管理员账号不能在此禁用')
    pool = await get_pool()
    row = await pool.fetchrow('UPDATE users SET disabled=TRUE,auth_epoch=auth_epoch+1 WHERE email=$1 RETURNING email,disabled',email.casefold())
    if not row:
        raise HTTPException(404,'账号不存在')
    return dict(row)


@router.post("/send-code")
async def send_code(req: SendCodeRequest, request: Request):
    if os.getenv('ASTERIA_EMAIL_LOGIN_ENABLED', '0') != '1':
        raise HTTPException(409, '当前使用管理员预置账号，请使用密码登录')
    await login_limits(req.email, request)
    await lab.throttle('mail:' + req.email, 1, 60)
    pool = await get_pool()
    if not await pool.fetchval('SELECT 1 FROM users WHERE email=$1 AND disabled=FALSE', req.email):
        return {'message':'若账号可用，验证码将发送到该邮箱'}
    code = generate_code()
    code_hash = hmac.new(os.environ['JWT_SECRET'].encode(), (req.email + ':' + code).encode(), hashlib.sha256).hexdigest()
    key = lab.namespace() + ':otp:' + lab.digest(req.email)
    async with lab.redis_connection() as r:
        await r.set(key, code_hash, ex=CODE_EXPIRE_MINUTES*60)
    try:
        await send_verification_code(req.email, code, CODE_EXPIRE_MINUTES)
    except Exception:
        async with lab.redis_connection() as r:
            await r.delete(key)
        logger.error('Verification email delivery failed')
        raise HTTPException(status_code=500, detail="邮件发送失败,请稍后重试")
    return {'message':'若账号可用，验证码将发送到该邮箱'}


@router.post("/verify-code", response_model=AuthResponse)
async def verify_code(req: VerifyCodeRequest, request: Request, response: Response):
    if os.getenv('ASTERIA_EMAIL_LOGIN_ENABLED', '0') != '1':
        raise HTTPException(409, '请使用密码登录')
    await login_limits(req.email, request)
    await lab.throttle('otp-attempt:' + req.email, 5, 600)
    code_hash = hmac.new(os.environ['JWT_SECRET'].encode(), (req.email + ':' + req.code).encode(), hashlib.sha256).hexdigest()
    async with lab.redis_connection() as r:
        consumed = await r.eval("if redis.call('GET',KEYS[1])==ARGV[1] then redis.call('DEL',KEYS[1]); return 1 end; return 0",
                                1,lab.namespace()+':otp:'+lab.digest(req.email),code_hash)
    if not consumed:
        raise HTTPException(400,'验证码错误或已过期')
    pool = await get_pool()
    user = await pool.fetchrow('UPDATE users SET last_login_at=now() WHERE email=$1 AND disabled=FALSE RETURNING email,auth_epoch',req.email)
    if not user:
        raise HTTPException(401,'账号不可用')
    return await auth_response(user,response)


@router.get("/me", response_model=CurrentUser)
async def me(email: str = Depends(get_current_user_email)):
    return CurrentUser(email=email, is_admin=lab.admin_email(email))
