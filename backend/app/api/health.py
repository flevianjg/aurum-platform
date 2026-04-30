"""Liveness + readiness probes."""

from __future__ import annotations

import redis.asyncio as redis_asyncio
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness — dependencies (Postgres + Redis) are reachable."""
    settings = get_settings()

    await session.execute(text("SELECT 1"))

    client = redis_asyncio.from_url(settings.REDIS_URL)
    try:
        pong = await client.ping()
        if not pong:
            raise RuntimeError("redis did not respond to PING")
    finally:
        await client.aclose()

    return {"status": "ready"}
