"""Current-user + passkey-management endpoints."""

import uuid

from fastapi import APIRouter, Body, Depends, Path, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, user_agent
from app.core.audit import write_audit
from app.core.errors import ConflictError, NotFoundError
from app.core.rate_limit import USER_LIMIT, limiter
from app.db.models import Passkey, User
from app.db.session import get_session
from app.schemas.passkey import PasskeyOut, PasskeyRenameRequest
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


@router.get("/me/passkeys", response_model=list[PasskeyOut])
@limiter.limit(USER_LIMIT)
async def list_passkeys(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Passkey]:
    rows = (
        await session.execute(
            select(Passkey)
            .where(Passkey.user_id == user.id)
            .order_by(Passkey.created_at.desc())
        )
    ).scalars().all()
    await write_audit(
        session,
        action="user.passkeys.list",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata={"count": len(rows)},
    )
    return list(rows)


async def _load_owned_passkey(
    session: AsyncSession, *, passkey_id: uuid.UUID, user_id: uuid.UUID
) -> Passkey:
    row = await session.get(Passkey, passkey_id)
    # Treat "doesn't exist" and "owned by another user" both as 404 (don't leak).
    if row is None or row.user_id != user_id:
        raise NotFoundError("passkey not found")
    return row


@router.patch("/me/passkeys/{passkey_id}", response_model=PasskeyOut)
@limiter.limit(USER_LIMIT)
async def rename_passkey(
    request: Request,
    response: Response,
    passkey_id: uuid.UUID = Path(...),
    body: PasskeyRenameRequest = Body(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Passkey:
    row = await _load_owned_passkey(session, passkey_id=passkey_id, user_id=user.id)
    row.nickname = body.nickname
    await session.flush()
    await write_audit(
        session,
        action="user.passkeys.rename",
        status="success",
        user_id=user.id,
        resource=f"passkey:{row.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
    )
    return row


@router.delete(
    "/me/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT
)
@limiter.limit(USER_LIMIT)
async def remove_passkey(
    request: Request,
    response: Response,
    passkey_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await _load_owned_passkey(session, passkey_id=passkey_id, user_id=user.id)
    total = (
        await session.execute(
            select(func.count()).select_from(Passkey).where(Passkey.user_id == user.id)
        )
    ).scalar_one()
    if total <= 1:
        await write_audit(
            session,
            action="user.passkeys.remove",
            status="failure",
            user_id=user.id,
            resource=f"passkey:{row.id}",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=getattr(request.state, "request_id", None),
            metadata={"reason": "would_leave_zero_passkeys"},
        )
        raise ConflictError(
            "cannot remove last passkey — register another device first"
        )
    await session.delete(row)
    await session.flush()
    await write_audit(
        session,
        action="user.passkeys.remove",
        status="success",
        user_id=user.id,
        resource=f"passkey:{passkey_id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
