"""Pydantic schemas for authentication flows."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class AuthCallbackRequest(BaseModel):
    """Query params forwarded from Google's OAuth2 redirect."""

    code: str
    state: str | None = None
    error: str | None = None


class SessionResponse(BaseModel):
    """Returned after a successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    timezone: str
    created_at: datetime
