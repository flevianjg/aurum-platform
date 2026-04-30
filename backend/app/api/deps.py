"""Common FastAPI dependencies: current user, request context."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_session


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise AuthError(str(exc)) from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthError("malformed token subject") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("user not found or disabled")

    request.state.user_id = user.id
    return user


def client_ip(request: Request) -> str | None:
    """Caddy sets X-Forwarded-For; we trust it because Caddy is the only
    upstream the backend listens to within the compose network."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
