"""Encrypted credential persistence + ownership-aware access.

Public functions:
    create_broker_account(...)  — validate + test + encrypt + persist
    load_credentials(...)       — decrypt, ownership-checked
    test_stored_account(...)    — test stored creds, update broker_accounts
                                  + insert broker_health_checks row
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_credentials, encrypt_credentials
from app.db.models import BrokerAccount, BrokerHealthCheck, BrokerType

from .base import TestConnectionResult
from .exceptions import BrokerError, BrokerValidationError
from .factory import get_adapter

logger = logging.getLogger(__name__)


class CredentialOwnershipError(PermissionError):
    """Raised when load_credentials is called by a non-owning user."""


def _coerce_creds_for_storage(credentials: dict[str, Any]) -> dict[str, Any]:
    """Strip the broker_type discriminator before encrypting — it lives in the
    DB column, not in the encrypted blob. SecretStr values are unwrapped via
    .get_secret_value() before serialization so they round-trip as plain str."""
    out: dict[str, Any] = {}
    for k, v in credentials.items():
        if k == "broker_type":
            continue
        if hasattr(v, "get_secret_value"):
            out[k] = v.get_secret_value()
        else:
            out[k] = v
    return out


async def _persist(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    broker_type: BrokerType,
    account_label: str,
    encrypted: bytes,
    nonce: bytes,
    test_result: TestConnectionResult,
) -> BrokerAccount:
    now = datetime.now(timezone.utc)
    row = BrokerAccount(
        user_id=user_id,
        broker_type=broker_type,
        account_label=account_label,
        encrypted_credentials=encrypted,
        credential_nonce=nonce,
        is_active=True,
        last_tested_at=now,
        last_test_status="success",
        last_test_error=None,
        account_currency=test_result.account_currency,
        server=test_result.server,
        account_number=test_result.account_number,
    )
    session.add(row)
    await session.flush()
    return row


async def create_broker_account(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    broker_type: str,
    account_label: str,
    credentials: dict[str, Any],
) -> tuple[BrokerAccount, TestConnectionResult]:
    """Validate, test, encrypt, persist. Returns (orm_row, test_result).

    Raises BrokerValidationError on missing fields. If test_connection fails,
    the result has success=False and NO row is persisted.
    """
    adapter = get_adapter(broker_type)
    storable = _coerce_creds_for_storage(credentials)

    for field in adapter.required_credential_fields():
        if field not in storable:
            raise BrokerValidationError(f"missing credential field: {field}")

    test_result = await adapter.test_connection(storable)
    if not test_result.success:
        # Don't persist creds that don't work
        raise BrokerError(
            test_result.error_message or "broker test failed",
            error_code=test_result.error_code,
        )

    encrypted, nonce = encrypt_credentials(storable)
    row = await _persist(
        session,
        user_id=user_id,
        broker_type=BrokerType(broker_type),
        account_label=account_label,
        encrypted=encrypted,
        nonce=nonce,
        test_result=test_result,
    )
    logger.info(
        "broker_account.created broker=%s label=%s account=%s",
        broker_type,
        account_label,
        test_result.account_number,
    )
    return row, test_result


async def _load_owned_row(
    session: AsyncSession,
    *,
    broker_account_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BrokerAccount | None:
    row = await session.get(BrokerAccount, broker_account_id)
    if row is None:
        return None
    if row.user_id != user_id:
        raise CredentialOwnershipError(
            "broker_account does not belong to this user"
        )
    return row


async def load_credentials(
    session: AsyncSession,
    *,
    broker_account_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    row = await _load_owned_row(
        session, broker_account_id=broker_account_id, user_id=user_id
    )
    if row is None:
        raise LookupError("broker_account not found")
    return decrypt_credentials(
        bytes(row.encrypted_credentials), bytes(row.credential_nonce)
    )


async def verify_stored_credentials(
    session: AsyncSession,
    *,
    broker_account_id: uuid.UUID,
    user_id: uuid.UUID,
) -> TestConnectionResult:
    """Re-test stored credentials. Renamed from test_stored_account because
    the test_ prefix triggers pytest auto-collection when imported into a
    test module."""
    row = await _load_owned_row(
        session, broker_account_id=broker_account_id, user_id=user_id
    )
    if row is None:
        raise LookupError("broker_account not found")

    creds = decrypt_credentials(
        bytes(row.encrypted_credentials), bytes(row.credential_nonce)
    )
    adapter = get_adapter(row.broker_type.value)

    started = time.monotonic()
    result = await adapter.test_connection(creds)
    latency_ms = int((time.monotonic() - started) * 1000)

    now = datetime.now(timezone.utc)
    row.last_tested_at = now
    if result.success:
        row.last_test_status = "success"
        row.last_test_error = None
        if result.account_currency:
            row.account_currency = result.account_currency
        if result.server:
            row.server = result.server
        if result.account_number:
            row.account_number = result.account_number
    else:
        row.last_test_status = (
            "auth_failed"
            if result.error_code in {"401", "403", "AUTH_FAILED", "broker_auth_failed"}
            else "connection_error"
        )
        row.last_test_error = result.error_message

    session.add(
        BrokerHealthCheck(
            broker_account_id=row.id,
            status=row.last_test_status or "unknown",
            latency_ms=latency_ms,
            error_code=result.error_code if not result.success else None,
        )
    )
    await session.flush()
    return result


async def list_user_accounts(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[BrokerAccount]:
    rows = (
        await session.execute(
            select(BrokerAccount)
            .where(BrokerAccount.user_id == user_id)
            .order_by(BrokerAccount.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
