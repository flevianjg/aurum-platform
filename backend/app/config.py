"""Centralized application settings.

All values come from environment variables (loaded by docker-compose
from the .env file at the repo root). pydantic-settings validates
types and raises on missing required values at startup.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Owner / bootstrap
    OWNER_EMAIL: EmailStr
    OWNER_DISPLAY_NAME: str = "Owner"

    # Public origin / WebAuthn
    PUBLIC_ORIGIN: str = Field(default="https://anvisutra.com")
    RP_ID: str = Field(default="anvisutra.com")
    RP_NAME: str = Field(default="Aurum Platform")

    # Database
    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # JWT
    JWT_SECRET: str
    JWT_ACCESS_TTL_SECONDS: int = 900
    JWT_REFRESH_TTL_SECONDS: int = 30 * 24 * 3600

    # Master encryption key (base64-encoded 32 bytes)
    MASTER_KEY: str

    # CORS
    CORS_ALLOWED_ORIGINS: str = "https://anvisutra.com"

    # Environment / logging
    APP_ENV: str = "production"
    LOG_LEVEL: str = "INFO"

    @field_validator("MASTER_KEY")
    @classmethod
    def _validate_master_key(cls, v: str) -> str:
        try:
            raw = base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError("MASTER_KEY must be base64-encoded") from exc
        if len(raw) != 32:
            raise ValueError("MASTER_KEY must decode to exactly 32 bytes")
        return v

    @field_validator("JWT_SECRET")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def master_key_bytes(self) -> bytes:
        return base64.b64decode(self.MASTER_KEY)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
