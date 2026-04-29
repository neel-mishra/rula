"""
Auth router.

- JWT session identity (`/auth/me`)
- Email/password register/login/logout endpoints for multi-tenant auth.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.user import User
from core.security.auth import (
    create_session_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter()


class CurrentUserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class SessionResponse(BaseModel):
    session_token: str
    user: CurrentUserResponse


class LogoutResponse(BaseModel):
    logged_out: bool


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    """Return the authenticated user's profile + role."""
    return CurrentUserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        is_active=user.is_active,
    )


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    display_name = payload.display_name
    if not display_name:
        display_name = payload.email.split("@")[0]

    user = User(
        id=uuid.uuid4(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=display_name,
        is_active=True,
        email_verified_at=datetime.now(tz=timezone.utc),
    )
    db.add(user)
    await db.flush()

    token = create_session_token(user_id=user.id, email=user.email)
    return SessionResponse(
        session_token=token,
        user=CurrentUserResponse(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            role=user.role.value,
            is_active=user.is_active,
        ),
    )


@router.post("/login", response_model=SessionResponse)
async def login_user(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    token = create_session_token(user_id=user.id, email=user.email)
    return SessionResponse(
        session_token=token,
        user=CurrentUserResponse(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            role=user.role.value,
            is_active=user.is_active,
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout_user(_: User = Depends(get_current_user)) -> LogoutResponse:
    return LogoutResponse(logged_out=True)
