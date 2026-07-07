"""
Auth routes: passwordless email-verification-code login.

Flow: POST /api/auth/send-code -> user receives a 6-digit code by email
      POST /api/auth/verify-code -> code checked against DB, JWT issued
      (first successful verify for a new email auto-creates the user row)
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends

from backend.auth.db import get_pool
from backend.auth.email_service import generate_code, send_verification_code
from backend.auth.jwt_utils import create_access_token
from backend.auth.models import SendCodeRequest, VerifyCodeRequest, AuthResponse, CurrentUser
from backend.auth.dependencies import get_current_user_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

CODE_EXPIRE_MINUTES = 10


@router.post("/send-code")
async def send_code(req: SendCodeRequest):
    pool = await get_pool()
    code = generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRE_MINUTES)

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO email_verification_codes (email, code, expires_at) VALUES ($1, $2, $3)",
            req.email, code, expires_at,
        )

    try:
        await send_verification_code(req.email, code, CODE_EXPIRE_MINUTES)
    except Exception as e:
        logger.error(f"Failed to send verification email to {req.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="邮件发送失败,请稍后重试")

    return {"message": f"验证码已发送到 {req.email},{CODE_EXPIRE_MINUTES} 分钟内有效"}


@router.post("/verify-code", response_model=AuthResponse)
async def verify_code(req: VerifyCodeRequest):
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM email_verification_codes
            WHERE email = $1 AND code = $2 AND used = FALSE AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
            """,
            req.email, req.code,
        )
        if row is None:
            raise HTTPException(status_code=400, detail="验证码错误或已过期")

        await conn.execute("UPDATE email_verification_codes SET used = TRUE WHERE id = $1", row["id"])

        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", req.email)
        is_new_user = user is None
        if is_new_user:
            await conn.execute(
                "INSERT INTO users (email, last_login_at) VALUES ($1, NOW())", req.email
            )
        else:
            await conn.execute(
                "UPDATE users SET last_login_at = NOW() WHERE email = $1", req.email
            )

    token = create_access_token(req.email)
    return AuthResponse(access_token=token, email=req.email, is_new_user=is_new_user)


@router.get("/me", response_model=CurrentUser)
async def me(email: str = Depends(get_current_user_email)):
    return CurrentUser(email=email)
