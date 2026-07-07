"""
FastAPI dependency for extracting/validating the current user from a Bearer
token. This is the one place in the whole app that uses `Depends()` - see
the Notion write-up for why (request-scoped auth state is the textbook DI
use case, unlike the rest of the app's module-level singletons).
"""
from fastapi import Header, HTTPException
from backend.auth.jwt_utils import decode_access_token


async def get_current_user_email(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    email = decode_access_token(token)
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return email


async def get_current_user_email_from_query(token: str | None = None) -> str | None:
    """WebSocket variant - browsers can't set custom headers on a WS handshake,
    so the token travels as a query param (?token=...) instead. Returns None
    (rather than raising) so the caller can decide how to react inside the
    websocket lifecycle instead of during the HTTP upgrade."""
    if not token:
        return None
    return decode_access_token(token)
