"""Broker API endpoint tests.

Strategy:
* JWT minted directly via app.core.security.create_access_token (faster than
  going through the WebAuthn flow). The /me path is exercised in test_auth.py.
* OANDA endpoints stub the adapter via dependency injection or via the same
  httpx MockTransport pattern. MT5 endpoints rely on TEST_MODE.
* Every endpoint asserts the audit log received a row AND that no plaintext
  credential value (password, api_token) leaks into any audited or returned
  payload.
"""

from __future__ import annotations

import json
import re
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models import AuditLog, BrokerAccount, BrokerHealthCheck, User, UserRole


# ----------- shared fixtures -----------


def _bearer(user) -> dict[str, str]:
    token, _ = create_access_token(user_id=user.id, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def viewer_user(db_session) -> User:
    u = User(
        email="viewer@example.com",
        display_name="Viewer",
        role=UserRole.VIEWER,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def member_user(db_session) -> User:
    u = User(
        email="member2@example.com",
        display_name="Member2",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
def patch_httpx(monkeypatch):
    def _apply(handler):
        original_init = httpx.AsyncClient.__init__

        def patched(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)
    return _apply


def _mt5_creds() -> dict:
    return {
        "broker_type": "MT5",
        "credentials": {
            "account": 12345678,
            "password": "supersecret-pw",
            "server": "Exness-MT5Trial11",
        },
    }


def _oanda_creds() -> dict:
    return {
        "broker_type": "OANDA",
        "credentials": {
            "account_id": "001-001-7654321-001",
            "api_token": "tok-do-not-leak-xyz",
            "environment": "practice",
        },
    }


def _assert_no_creds_in(text: str) -> None:
    """Hard assertion: plaintext credentials never appear in any payload."""
    assert "supersecret-pw" not in text
    assert "tok-do-not-leak-xyz" not in text


# =======================================================
# POST /broker/test
# =======================================================


async def test_test_without_auth_is_401(client) -> None:
    r = await client.post("/broker/test", json=_mt5_creds())
    assert r.status_code == 401


async def test_test_viewer_role_forbidden(client, viewer_user) -> None:
    r = await client.post("/broker/test", json=_mt5_creds(), headers=_bearer(viewer_user))
    assert r.status_code == 403


async def test_test_mt5_happy_path(client, owner_user) -> None:
    r = await client.post("/broker/test", json=_mt5_creds(), headers=_bearer(owner_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["account_number"] == "12345678"
    _assert_no_creds_in(r.text)


async def test_test_oanda_happy_path(client, owner_user, patch_httpx) -> None:
    def handler(request):
        return httpx.Response(
            200,
            json={
                "account": {
                    "id": "001-001-7654321-001",
                    "currency": "USD",
                    "balance": "1000.00",
                    "NAV": "1010.00",
                }
            },
        )

    patch_httpx(handler)
    r = await client.post(
        "/broker/test", json=_oanda_creds(), headers=_bearer(owner_user)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    _assert_no_creds_in(r.text)


async def test_test_oanda_bad_creds_returns_failure_payload(
    client, owner_user, patch_httpx
) -> None:
    def handler(request):
        return httpx.Response(401, json={"errorMessage": "bad token"})

    patch_httpx(handler)
    r = await client.post(
        "/broker/test", json=_oanda_creds(), headers=_bearer(owner_user)
    )
    assert r.status_code == 200  # endpoint returns 200, body has success=false
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "401"
    _assert_no_creds_in(r.text)


async def test_test_request_validation_400_when_creds_dont_match_broker_type(
    client, owner_user
) -> None:
    payload = {
        "broker_type": "OANDA",
        "credentials": {"account": 1, "password": "x", "server": "S"},  # MT5 shape
    }
    r = await client.post("/broker/test", json=payload, headers=_bearer(owner_user))
    assert r.status_code == 422


# =======================================================
# POST /broker (connect)
# =======================================================


async def test_connect_persists_and_returns_id(client, owner_user, db_session) -> None:
    payload = {**_mt5_creds(), "account_label": "Owner Demo MT5"}
    r = await client.post("/broker", json=payload, headers=_bearer(owner_user))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["account_label"] == "Owner Demo MT5"
    assert body["broker_type"] == "MT5"
    assert "id" in body
    _assert_no_creds_in(r.text)

    # Persisted row exists, plaintext password not in ciphertext
    rows = (await db_session.execute(select(BrokerAccount))).scalars().all()
    assert len(rows) == 1
    assert b"supersecret-pw" not in rows[0].encrypted_credentials


async def test_connect_with_failing_creds_does_not_persist(
    client, owner_user, db_session, patch_httpx
) -> None:
    def handler(request):
        return httpx.Response(401)

    patch_httpx(handler)
    payload = {**_oanda_creds(), "account_label": "BadLabel"}
    r = await client.post("/broker", json=payload, headers=_bearer(owner_user))
    assert r.status_code == 422

    rows = (await db_session.execute(select(BrokerAccount))).scalars().all()
    assert len(rows) == 0


async def test_connect_viewer_forbidden(client, viewer_user) -> None:
    payload = {**_mt5_creds(), "account_label": "Nope"}
    r = await client.post("/broker", json=payload, headers=_bearer(viewer_user))
    assert r.status_code == 403


# =======================================================
# GET /broker (list)
# =======================================================


async def test_list_returns_only_users_own_accounts(
    client, owner_user, member_user
) -> None:
    p = {**_mt5_creds(), "account_label": "Owner Acct"}
    await client.post("/broker", json=p, headers=_bearer(owner_user))

    p2 = {**_mt5_creds(), "account_label": "Member Acct"}
    p2["credentials"] = {**p2["credentials"], "account": 99999999}
    await client.post("/broker", json=p2, headers=_bearer(member_user))

    r_owner = await client.get("/broker", headers=_bearer(owner_user))
    assert r_owner.status_code == 200
    labels_owner = {a["account_label"] for a in r_owner.json()}
    assert labels_owner == {"Owner Acct"}

    r_member = await client.get("/broker", headers=_bearer(member_user))
    labels_member = {a["account_label"] for a in r_member.json()}
    assert labels_member == {"Member Acct"}


# =======================================================
# GET /broker/{id}
# =======================================================


async def test_read_other_users_account_returns_404(
    client, owner_user, member_user
) -> None:
    p = {**_mt5_creds(), "account_label": "Mine"}
    created = (
        await client.post("/broker", json=p, headers=_bearer(owner_user))
    ).json()
    r = await client.get(f"/broker/{created['id']}", headers=_bearer(member_user))
    assert r.status_code == 404


async def test_read_returns_live_info(client, owner_user) -> None:
    p = {**_mt5_creds(), "account_label": "Live"}
    created = (
        await client.post("/broker", json=p, headers=_bearer(owner_user))
    ).json()
    r = await client.get(f"/broker/{created['id']}", headers=_bearer(owner_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_account_info"] is not None
    assert body["live_account_info"]["currency"] == "USD"
    _assert_no_creds_in(r.text)


# =======================================================
# POST /broker/{id}/test (re-test stored)
# =======================================================


async def test_test_stored_updates_last_tested_and_writes_health(
    client, owner_user, db_session
) -> None:
    p = {**_mt5_creds(), "account_label": "ReTest"}
    created = (
        await client.post("/broker", json=p, headers=_bearer(owner_user))
    ).json()
    r = await client.post(
        f"/broker/{created['id']}/test", headers=_bearer(owner_user)
    )
    assert r.status_code == 200
    assert r.json()["success"] is True

    health = (
        await db_session.execute(select(BrokerHealthCheck))
    ).scalars().all()
    # connect already wrote one... actually create_broker_account writes the
    # broker_accounts row but does NOT write a health check; only test_stored
    # writes one. So we expect exactly 1 here.
    assert len(health) == 1
    assert health[0].status == "success"


# =======================================================
# PATCH /broker/{id}/deactivate + reactivate
# =======================================================


async def test_deactivate_sets_flag(client, owner_user) -> None:
    created = (
        await client.post(
            "/broker", json={**_mt5_creds(), "account_label": "Toggle"},
            headers=_bearer(owner_user),
        )
    ).json()
    r = await client.patch(
        f"/broker/{created['id']}/deactivate", headers=_bearer(owner_user)
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r2 = await client.patch(
        f"/broker/{created['id']}/reactivate", headers=_bearer(owner_user)
    )
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


# =======================================================
# DELETE /broker/{id}
# =======================================================


async def test_delete_cascades_health_checks(client, owner_user, db_session) -> None:
    created = (
        await client.post(
            "/broker",
            json={**_mt5_creds(), "account_label": "Doomed"},
            headers=_bearer(owner_user),
        )
    ).json()
    bid = created["id"]
    # Generate a health check via re-test
    await client.post(f"/broker/{bid}/test", headers=_bearer(owner_user))
    pre = (await db_session.execute(select(BrokerHealthCheck))).scalars().all()
    assert len(pre) >= 1

    r = await client.delete(f"/broker/{bid}", headers=_bearer(owner_user))
    assert r.status_code == 204

    # broker row is gone
    after_acct = (
        await db_session.execute(
            select(BrokerAccount).where(BrokerAccount.id == uuid.UUID(bid))
        )
    ).scalars().all()
    assert after_acct == []
    # health checks for that account cascaded
    after_health = (
        await db_session.execute(
            select(BrokerHealthCheck).where(
                BrokerHealthCheck.broker_account_id == uuid.UUID(bid)
            )
        )
    ).scalars().all()
    assert after_health == []


# =======================================================
# Audit log + secret hygiene
# =======================================================


async def test_endpoints_write_audit_with_no_credential_leakage(
    client, owner_user, db_session
) -> None:
    # exercise: test, connect, list, read, retest, deactivate, reactivate, delete
    await client.post("/broker/test", json=_mt5_creds(), headers=_bearer(owner_user))
    created = (
        await client.post(
            "/broker",
            json={**_mt5_creds(), "account_label": "AuditCheck"},
            headers=_bearer(owner_user),
        )
    ).json()
    await client.get("/broker", headers=_bearer(owner_user))
    await client.get(f"/broker/{created['id']}", headers=_bearer(owner_user))
    await client.post(f"/broker/{created['id']}/test", headers=_bearer(owner_user))
    await client.patch(
        f"/broker/{created['id']}/deactivate", headers=_bearer(owner_user)
    )
    await client.patch(
        f"/broker/{created['id']}/reactivate", headers=_bearer(owner_user)
    )
    await client.delete(f"/broker/{created['id']}", headers=_bearer(owner_user))

    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    actions = {r.action for r in rows}
    expected = {
        "broker.test",
        "broker.connect",
        "broker.list",
        "broker.read",
        "broker.test_stored",
        "broker.deactivate",
        "broker.reactivate",
        "broker.delete",
    }
    assert expected.issubset(actions), f"missing audit actions: {expected - actions}"

    # No plaintext credentials in any audit metadata
    for row in rows:
        if row.audit_metadata is None:
            continue
        flat = json.dumps(row.audit_metadata)
        assert "supersecret-pw" not in flat
        assert "tok-do-not-leak-xyz" not in flat
        # The metadata-redaction in audit.write_audit also catches forbidden keys
        assert not re.search(r'"password"\s*:\s*"[^"]*pw', flat)
