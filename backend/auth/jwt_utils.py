"""
Minimal JWT issue/verify helpers built on python-jose.

Deliberately not using a full auth framework (fastapi-users etc) - the
requirement here is small (one login flow, one role), a hand-rolled JWT is
easier to reason about and matches the project's existing "no framework
magic" style (see asteria_researcher/llm_provider - plain if/elif dispatch,
no ABCs).
"""
import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

ALGORITHM = "HS256"


def create_access_token(email: str) -> str:
    secret = os.environ["JWT_SECRET"]
    expire_minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", "10080"))
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Returns the email (subject) if the token is valid, else None."""
    secret = os.environ["JWT_SECRET"]
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
