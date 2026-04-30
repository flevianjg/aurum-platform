"""Audit log invariants:
* every Phase 1 endpoint that mutates or authenticates writes at least one row
* the DB enforces append-only (UPDATE / DELETE on audit_log raise)
* the writer scrubs forbidden keys from metadata
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.core.audit import _scrub, write_audit
from app.db.models import AuditLog


@dataclass
class FakeRegistration:
    credential_id: bytes
    credential_public_key: bytes
    sign_count: int = 0


async def _count(db_session) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(AuditLog))
    ).scalar_one()


async def test_register_begin_writes_audit_row(client, owner_user, db_session) -> None:
    before = await _count(db_session)
    r = await client.post(
        "/auth/passkey/register/begin", json={"email": owner_user.email}
    )
    assert r.status_code == 200
    after = await _count(db_session)
    assert after == before + 1

    last = (
        await db_session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(1)
        )
    ).scalar_one()
    assert last.action == "auth.register.begin"
    assert last.status == "success"
    assert last.user_id == owner_user.id


async def test_register_begin_failure_is_audited(client, db_session) -> None:
    before = await _count(db_session)
    r = await client.post(
        "/auth/passkey/register/begin", json={"email": "ghost@example.com"}
    )
    assert r.status_code == 404
    after = await _count(db_session)
    assert after == before + 1

    last = (
        await db_session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(1)
        )
    ).scalar_one()
    assert last.action == "auth.register.begin"
    assert last.status == "failure"


async def test_me_writes_audit_row(client, owner_user, db_session) -> None:
    # Register + login
    begin = await client.post(
        "/auth/passkey/register/begin", json={"email": owner_user.email}
    )
    cred_id = secrets.token_bytes(32)

    with patch(
        "app.api.auth.verify_registration_response",
        return_value=FakeRegistration(
            credential_id=cred_id, credential_public_key=secrets.token_bytes(64)
        ),
    ):
        await client.post(
            "/auth/passkey/register/finish",
            json={
                "challenge_id": begin.json()["challenge_id"],
                "credential": {
                    "id": "x",
                    "rawId": "x",
                    "type": "public-key",
                    "response": {"transports": ["internal"]},
                },
            },
        )

    # Forge an access token directly to skip the assertion mock dance
    from app.core.security import create_access_token

    token, _ = create_access_token(user_id=owner_user.id, role=owner_user.role.value)

    before = await _count(db_session)
    r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    after = await _count(db_session)
    assert after == before + 1

    last = (
        await db_session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(1)
        )
    ).scalar_one()
    assert last.action == "user.me.read"
    assert last.user_id == owner_user.id


async def test_audit_log_is_append_only_no_update(db_session, owner_user) -> None:
    await write_audit(
        db_session,
        action="test.write",
        status="success",
        user_id=owner_user.id,
    )
    await db_session.commit()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            update(AuditLog).where(AuditLog.action == "test.write").values(status="x")
        )
        await db_session.commit()
    await db_session.rollback()


async def test_audit_log_is_append_only_no_delete(db_session, owner_user) -> None:
    await write_audit(
        db_session,
        action="test.write.delete",
        status="success",
        user_id=owner_user.id,
    )
    await db_session.commit()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM audit_log WHERE action = 'test.write.delete'")
        )
        await db_session.commit()
    await db_session.rollback()


def test_scrub_redacts_forbidden_keys() -> None:
    cleaned = _scrub(
        {
            "user": "alice",
            "password": "hunter2",
            "Authorization": "Bearer xyz",
            "nested": {"refresh_token": "abc", "ok": 1},
        }
    )
    assert cleaned["user"] == "alice"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["Authorization"] == "[REDACTED]"
    assert cleaned["nested"]["refresh_token"] == "[REDACTED]"
    assert cleaned["nested"]["ok"] == 1
