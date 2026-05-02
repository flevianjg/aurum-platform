"""Schemas for passkey management endpoints (Phase 3 sub-phase 4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PasskeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nickname: str | None
    transports: list[str] | None
    created_at: datetime
    last_used_at: datetime | None


class PasskeyRenameRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)
