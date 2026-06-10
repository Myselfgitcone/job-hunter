"""
Auth helpers — JWT + bcrypt for multi-user job-hunter.
"""
from datetime import datetime, timedelta
from typing import Optional
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt

_DEV_SECRET = "dev-secret-key-change-in-production-please"
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

# Prod detection: Railway sets RAILWAY_ENVIRONMENT; a Postgres DATABASE_URL is
# the other tell (local dev uses SQLite). In prod a missing/blank SECRET_KEY
# would sign tokens with a publicly-known string → anyone could forge a token
# for any user. Refuse to start rather than run forgeable.
_IS_PROD = bool(
    os.getenv("RAILWAY_ENVIRONMENT")
    or os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql"))
)
if not SECRET_KEY:
    if _IS_PROD:
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production. "
            "Refusing to start: without it, JWTs are signed with a known dev key "
            "and any user's token can be forged. Set SECRET_KEY in Railway."
        )
    import sys
    print(
        "\n" + "!" * 70 + "\n"
        "  WARNING: SECRET_KEY unset — using the dev fallback (local only).\n"
        "  Set SECRET_KEY in the environment before deploying.\n"
        + "!" * 70 + "\n",
        file=sys.stderr,
    )
    SECRET_KEY = _DEV_SECRET

ALGORITHM = "HS256"
# 14 days (was 90): a leaked/revoked token now dies in two weeks instead of
# three months. There is no server-side revocation list, so this window is the
# main containment for a stolen token.
TOKEN_EXPIRE_DAYS = 14

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """FastAPI dependency — extracts user_id from Bearer token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


def get_optional_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> Optional[str]:
    """Same but returns None instead of raising — for optional auth endpoints."""
    if not credentials:
        return None
    return decode_token(credentials.credentials)
