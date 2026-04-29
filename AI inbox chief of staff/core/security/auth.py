"""
Session/auth module — JWT-based user identity for API endpoints.

Issues a session JWT after OAuth login. All protected endpoints use
`get_current_user` dependency to extract user_id from the token.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db
from core.models.user import User, UserRole

_ALGORITHM = "HS256"
_TOKEN_EXPIRY_HOURS = 72
_ISSUER = "inbox-chief-of-staff"

_bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_session_token(user_id: uuid.UUID, email: str) -> str:
    """Create a signed JWT containing user identity."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + timedelta(hours=_TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict:
    """Decode and validate a session JWT. Raises on invalid/expired."""
    try:
        return jwt.decode(
            token,
            settings.app_secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency — extracts authenticated User from Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_session_token(credentials.credentials)
    user_id = uuid.UUID(claims["sub"])
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def get_current_user_id(
    user: Annotated[User, Depends(get_current_user)],
) -> uuid.UUID:
    """Convenience dependency — returns just the user_id UUID."""
    return user.id


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """FastAPI dependency that rejects non-admin users with 403."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user
