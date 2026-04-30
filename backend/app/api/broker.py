"""Phase 2 broker endpoints — connect, list, read, test, deactivate, delete.

All routes require a JWT (Phase 1 auth). VIEWER role is rejected with 403 on
every broker action — only OWNER and MEMBER can manage broker accounts.

Audit policy: every endpoint writes audit_log on both success and failure.
Metadata never includes credential VALUES — only broker_type, server,
account_label, account_number.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, user_agent
from app.brokers.credential_store import (
    CredentialOwnershipError,
    create_broker_account,
    list_user_accounts,
    load_credentials,
    verify_stored_credentials,
)
from app.brokers.exceptions import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerError,
    BrokerValidationError,
)
from app.brokers.factory import get_adapter
from app.core.audit import write_audit
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.rate_limit import AUTH_LIMIT, USER_LIMIT, limiter
from app.db.models import BrokerAccount, User, UserRole
from app.db.session import get_session
from app.schemas.broker import (
    BrokerAccountDetailResponse,
    BrokerAccountResponse,
    BrokerConnectRequest,
    BrokerTestRequest,
    BrokerTestResponse,
    LiveAccountInfo,
)

router = APIRouter(prefix="/broker", tags=["broker"])
logger = logging.getLogger(__name__)


_CONNECT_LIMIT = "5/minute"


class _BrokerTestFailed(AppError):
    """422 — credentials shape was valid but the broker rejected them."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "broker_test_failed"


def _require_writer(user: User) -> None:
    if user.role == UserRole.VIEWER:
        raise ForbiddenError("VIEWER role cannot manage broker accounts")


def _audit_meta_safe(*, broker_type: str | None = None, **extra: Any) -> dict[str, Any]:
    """Build audit metadata that is guaranteed not to leak credentials.
    audit.write_audit also runs _scrub on top of this — belt + suspenders."""
    out: dict[str, Any] = {}
    if broker_type is not None:
        out["broker_type"] = broker_type
    for k, v in extra.items():
        if k in {"password", "api_token", "credentials", "secret"}:
            continue
        out[k] = v
    return out


def _to_account_response(row: BrokerAccount) -> BrokerAccountResponse:
    return BrokerAccountResponse.model_validate(row)


# ============================================================
# POST /broker/test
# ============================================================


@router.post("/test", response_model=BrokerTestResponse)
@limiter.limit(AUTH_LIMIT)
async def broker_test(
    request: Request,
    response: Response,
    body: BrokerTestRequest = Body(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrokerTestResponse:
    _require_writer(user)
    adapter = get_adapter(body.broker_type)

    creds_dict = body.credentials.model_dump()
    # Unwrap SecretStr fields
    for field in ("password", "api_token"):
        secret = getattr(body.credentials, field, None)
        if secret is not None and hasattr(secret, "get_secret_value"):
            creds_dict[field] = secret.get_secret_value()
    creds_dict.pop("broker_type", None)

    result = await adapter.test_connection(creds_dict)

    await write_audit(
        session,
        action="broker.test",
        status="success" if result.success else "failure",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(
            broker_type=body.broker_type,
            server=result.server,
            account_number=result.account_number,
            success=result.success,
            error_code=result.error_code,
        ),
    )

    return BrokerTestResponse(
        success=result.success,
        account_number=result.account_number,
        account_currency=result.account_currency,
        server=result.server,
        balance=result.balance,
        equity=result.equity,
        error_code=result.error_code,
        error_message=result.error_message,
    )


# ============================================================
# POST /broker/connect
# ============================================================


@router.post(
    "",
    response_model=BrokerAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(_CONNECT_LIMIT)
async def broker_connect(
    request: Request,
    response: Response,
    body: BrokerConnectRequest = Body(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrokerAccountResponse:
    _require_writer(user)

    creds_dict = body.credentials.model_dump()
    for field in ("password", "api_token"):
        secret = getattr(body.credentials, field, None)
        if secret is not None and hasattr(secret, "get_secret_value"):
            creds_dict[field] = secret.get_secret_value()

    try:
        row, test_result = await create_broker_account(
            session,
            user_id=user.id,
            broker_type=body.broker_type,
            account_label=body.account_label,
            credentials=creds_dict,
        )
    except BrokerValidationError as exc:
        await write_audit(
            session,
            action="broker.connect",
            status="failure",
            user_id=user.id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=getattr(request.state, "request_id", None),
            metadata=_audit_meta_safe(
                broker_type=body.broker_type,
                account_label=body.account_label,
                reason="validation_error",
                detail=exc.message,
            ),
        )
        raise _BrokerTestFailed(exc.message) from exc
    except BrokerError as exc:
        await write_audit(
            session,
            action="broker.connect",
            status="failure",
            user_id=user.id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=getattr(request.state, "request_id", None),
            metadata=_audit_meta_safe(
                broker_type=body.broker_type,
                account_label=body.account_label,
                reason=exc.code,
                error_code=exc.error_code,
            ),
        )
        raise _BrokerTestFailed(exc.message) from exc

    await write_audit(
        session,
        action="broker.connect",
        status="success",
        user_id=user.id,
        resource=f"broker_account:{row.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(
            broker_type=body.broker_type,
            account_label=body.account_label,
            server=row.server,
            account_number=row.account_number,
        ),
    )

    return _to_account_response(row)


# ============================================================
# GET /broker
# ============================================================


@router.get("", response_model=list[BrokerAccountResponse])
@limiter.limit(USER_LIMIT)
async def broker_list(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BrokerAccountResponse]:
    rows = await list_user_accounts(session, user_id=user.id)
    await write_audit(
        session,
        action="broker.list",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata={"count": len(rows)},
    )
    return [_to_account_response(r) for r in rows]


# ============================================================
# GET /broker/{id}
# ============================================================


async def _load_owned_or_404(
    session: AsyncSession, *, broker_account_id: uuid.UUID, user_id: uuid.UUID
) -> BrokerAccount:
    row = await session.get(BrokerAccount, broker_account_id)
    # Treat both "doesn't exist" and "belongs to someone else" as 404 — don't
    # leak existence of accounts owned by other users.
    if row is None or row.user_id != user_id:
        raise NotFoundError("broker_account not found")
    return row


@router.get("/{broker_account_id}", response_model=BrokerAccountDetailResponse)
@limiter.limit(USER_LIMIT)
async def broker_read(
    request: Request,
    response: Response,
    broker_account_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrokerAccountDetailResponse:
    row = await _load_owned_or_404(
        session, broker_account_id=broker_account_id, user_id=user.id
    )

    live: LiveAccountInfo | None = None
    fetch_status = "skipped"
    error_msg: str | None = None
    if row.is_active:
        try:
            creds = await load_credentials(
                session, broker_account_id=row.id, user_id=user.id
            )
            adapter = get_adapter(row.broker_type.value)
            info = await adapter.get_account_info(creds)
            live = LiveAccountInfo(
                account_number=info.account_number,
                currency=info.currency,
                balance=info.balance,
                equity=info.equity,
                margin=info.margin,
                free_margin=info.free_margin,
                margin_level=info.margin_level,
                server=info.server,
            )
            fetch_status = "success"
        except (BrokerError, BrokerAuthError, BrokerConnectionError) as exc:
            fetch_status = "failure"
            error_msg = exc.message

    await write_audit(
        session,
        action="broker.read",
        status="success",
        user_id=user.id,
        resource=f"broker_account:{row.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(
            broker_type=row.broker_type.value,
            live_fetch=fetch_status,
        ),
    )

    base = _to_account_response(row).model_dump()
    return BrokerAccountDetailResponse(
        **base,
        last_test_error=error_msg or row.last_test_error,
        live_account_info=live,
    )


# ============================================================
# POST /broker/{id}/test
# ============================================================


@router.post(
    "/{broker_account_id}/test",
    response_model=BrokerTestResponse,
)
@limiter.limit(AUTH_LIMIT)
async def broker_test_stored(
    request: Request,
    response: Response,
    broker_account_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrokerTestResponse:
    _require_writer(user)
    # 404 first if not owned
    await _load_owned_or_404(
        session, broker_account_id=broker_account_id, user_id=user.id
    )
    try:
        result = await verify_stored_credentials(
            session, broker_account_id=broker_account_id, user_id=user.id
        )
    except CredentialOwnershipError:
        # Should not happen — we just verified ownership — but re-map to 404 if it does.
        raise NotFoundError("broker_account not found")

    await write_audit(
        session,
        action="broker.test_stored",
        status="success" if result.success else "failure",
        user_id=user.id,
        resource=f"broker_account:{broker_account_id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(
            success=result.success,
            error_code=result.error_code,
        ),
    )
    return BrokerTestResponse(
        success=result.success,
        account_number=result.account_number,
        account_currency=result.account_currency,
        server=result.server,
        balance=result.balance,
        equity=result.equity,
        error_code=result.error_code,
        error_message=result.error_message,
    )


# ============================================================
# PATCH /broker/{id}/deactivate, /reactivate
# ============================================================


@router.patch(
    "/{broker_account_id}/deactivate", response_model=BrokerAccountResponse
)
@limiter.limit(USER_LIMIT)
async def broker_deactivate(
    request: Request,
    response: Response,
    broker_account_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrokerAccountResponse:
    _require_writer(user)
    row = await _load_owned_or_404(
        session, broker_account_id=broker_account_id, user_id=user.id
    )
    row.is_active = False
    row.deactivated_at = datetime.now(timezone.utc)
    await session.flush()

    await write_audit(
        session,
        action="broker.deactivate",
        status="success",
        user_id=user.id,
        resource=f"broker_account:{row.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(broker_type=row.broker_type.value),
    )
    return _to_account_response(row)


@router.patch(
    "/{broker_account_id}/reactivate", response_model=BrokerAccountResponse
)
@limiter.limit(USER_LIMIT)
async def broker_reactivate(
    request: Request,
    response: Response,
    broker_account_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrokerAccountResponse:
    _require_writer(user)
    row = await _load_owned_or_404(
        session, broker_account_id=broker_account_id, user_id=user.id
    )
    row.is_active = True
    row.deactivated_at = None
    await session.flush()

    await write_audit(
        session,
        action="broker.reactivate",
        status="success",
        user_id=user.id,
        resource=f"broker_account:{row.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(broker_type=row.broker_type.value),
    )
    return _to_account_response(row)


# ============================================================
# DELETE /broker/{id}
# ============================================================


@router.delete(
    "/{broker_account_id}", status_code=status.HTTP_204_NO_CONTENT
)
@limiter.limit(USER_LIMIT)
async def broker_delete(
    request: Request,
    response: Response,
    broker_account_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_writer(user)
    row = await _load_owned_or_404(
        session, broker_account_id=broker_account_id, user_id=user.id
    )

    broker_type_value = row.broker_type.value
    await session.delete(row)
    await session.flush()

    await write_audit(
        session,
        action="broker.delete",
        status="success",
        user_id=user.id,
        resource=f"broker_account:{broker_account_id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=_audit_meta_safe(broker_type=broker_type_value),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
