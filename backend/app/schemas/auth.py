"""Auth-flow schemas (passkey register/login + token responses)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# ---------- Registration ----------


class PasskeyRegisterBeginRequest(BaseModel):
    email: EmailStr
    nickname: str | None = Field(default=None, max_length=64)


class PasskeyRegisterBeginResponse(BaseModel):
    challenge_id: str
    publicKey: dict[str, Any]


class PasskeyRegisterFinishRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]
    nickname: str | None = Field(default=None, max_length=64)


class PasskeyRegisterFinishResponse(BaseModel):
    passkey_id: str


# ---------- Login ----------


class PasskeyLoginBeginRequest(BaseModel):
    email: EmailStr | None = None  # optional → discoverable credentials


class PasskeyLoginBeginResponse(BaseModel):
    challenge_id: str
    publicKey: dict[str, Any]


class PasskeyLoginFinishRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class LogoutResponse(BaseModel):
    revoked: bool
