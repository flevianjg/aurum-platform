"""Current-user endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, user_agent
from app.core.audit import write_audit
from app.db.models import User
from app.db.session import get_session
from app.schemas.user import UserOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
async def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    await write_audit(
        session,
        action="user.me.read",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
    )
    return user
