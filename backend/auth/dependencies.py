"""
FastAPI dependency for extracting/validating the current user from a Bearer
token. This is the one place in the whole app that uses `Depends()` - see
the Notion write-up for why (request-scoped auth state is the textbook DI
use case, unlike the rest of the app's module-level singletons).
"""
import os

from fastapi import Depends, Header, HTTPException, Request
from backend.auth.lab import COOKIE, admin_email, session_email, shared_mode


def _local_auth_bypass_enabled() -> bool:
    """Enable auth-free local smoke tests only when explicitly configured."""
    return not shared_mode() and os.environ.get("ASTERIA_DEV_AUTH_BYPASS", "0").lower() in {"1", "true", "yes"}


def _local_auth_email() -> str:
    return os.environ.get("ASTERIA_DEV_AUTH_EMAIL", "local@asteria.dev")


async def get_current_user_email(authorization: str | None = Header(default=None), request: Request = None) -> str:
    if _local_auth_bypass_enabled():
        return _local_auth_email()

    cookie = request.cookies.get(COOKIE) if request else None
    if not authorization and cookie:
        authorization = 'Bearer ' + cookie
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    from backend.auth.jwt_utils import decode_access_token

    # Old JWTs are only accepted in non-shared development for compatibility.
    email = decode_access_token(token) if token.count('.') == 2 and not shared_mode() else await session_email(token)
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return email


async def get_current_user_email_from_query(token: str | None = None) -> str | None:
    """WebSocket variant - browsers can't set custom headers on a WS handshake,
    so the token travels as a query param (?token=...) instead. Returns None
    (rather than raising) so the caller can decide how to react inside the
    websocket lifecycle instead of during the HTTP upgrade."""
    if _local_auth_bypass_enabled():
        return _local_auth_email()
    if not token:
        return None
    from backend.auth.jwt_utils import decode_access_token

    return decode_access_token(token) if token.count('.') == 2 and not shared_mode() else await session_email(token)


async def require_admin(email: str = Depends(get_current_user_email)):
    if not admin_email(email) and not _local_auth_bypass_enabled():
        raise HTTPException(403, '此操作仅限实验室管理员')
    return email
