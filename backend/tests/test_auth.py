"""Auth flow tests.

WebAuthn signature verification is mocked — exercising real authenticator
attestation/assertion needs hardware. We DO exercise: route wiring,
challenge cache lifecycle, user lookup, refresh rotation, refresh reuse
detection, JWT issuance, /me with the issued token.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.security import hash_refresh_token
from app.db.models import Passkey, RefreshToken, User, UserRole


# ---------- shared fakes ----------


@dataclass
class FakeRegistration:
    credential_id: bytes
    credential_public_key: bytes
    sign_count: int = 0


@dataclass
class FakeAuthentication:
    new_sign_count: int


def _fake_credential_envelope() -> dict:
    """Shape that the route handler expects from the browser."""
    return {
        "id": "ZmFrZS1jcmVkLWlk",  # base64url("fake-cred-id")
        "rawId": "ZmFrZS1jcmVkLWlk",
        "type": "public-key",
        "response": {
            "clientDataJSON": "fake",
            "attestationObject": "fake",
            "transports": ["internal"],
        },
    }


# ---------- registration ----------


async def test_register_begin_unknown_email_is_404(client) -> None:
    r = await client.post(
        "/auth/passkey/register/begin",
        json={"email": "nobody@example.com"},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


async def test_register_full_flow(client, owner_user, db_session) -> None:
    begin = await client.post(
        "/auth/passkey/register/begin",
        json={"email": owner_user.email, "nickname": "Test Phone"},
    )
    assert begin.status_code == 200
    challenge_id = begin.json()["challenge_id"]
    assert challenge_id

    cred_id = secrets.token_bytes(32)
    public_key = secrets.token_bytes(64)

    with patch(
        "app.api.auth.verify_registration_response",
        return_value=FakeRegistration(
            credential_id=cred_id, credential_public_key=public_key
        ),
    ):
        finish = await client.post(
            "/auth/passkey/register/finish",
            json={
                "challenge_id": challenge_id,
                "credential": _fake_credential_envelope(),
                "nickname": "Test Phone",
            },
        )

    assert finish.status_code == 200, finish.text
    passkey_id = finish.json()["passkey_id"]
    assert passkey_id

    rows = (await db_session.execute(select(Passkey))).scalars().all()
    assert len(rows) == 1
    assert rows[0].credential_id == cred_id
    assert rows[0].user_id == owner_user.id


async def test_register_finish_with_unknown_challenge_is_401(client) -> None:
    r = await client.post(
        "/auth/passkey/register/finish",
        json={
            "challenge_id": "totally-bogus",
            "credential": _fake_credential_envelope(),
        },
    )
    assert r.status_code == 401


# ---------- login ----------


async def _register_one(client, owner_user) -> bytes:
    """Helper: register a passkey, return its credential_id bytes."""
    begin = await client.post(
        "/auth/passkey/register/begin",
        json={"email": owner_user.email},
    )
    assert begin.status_code == 200
    challenge_id = begin.json()["challenge_id"]

    cred_id = secrets.token_bytes(32)
    public_key = secrets.token_bytes(64)

    with patch(
        "app.api.auth.verify_registration_response",
        return_value=FakeRegistration(
            credential_id=cred_id, credential_public_key=public_key
        ),
    ):
        r = await client.post(
            "/auth/passkey/register/finish",
            json={
                "challenge_id": challenge_id,
                "credential": _fake_credential_envelope(),
            },
        )
    assert r.status_code == 200
    return cred_id


def _envelope_for(cred_id: bytes) -> dict:
    import base64

    raw = base64.urlsafe_b64encode(cred_id).decode("ascii").rstrip("=")
    return {
        "id": raw,
        "rawId": raw,
        "type": "public-key",
        "response": {
            "clientDataJSON": "fake",
            "authenticatorData": "fake",
            "signature": "fake",
        },
    }


async def test_login_full_flow_issues_access_and_refresh(
    client, owner_user
) -> None:
    cred_id = await _register_one(client, owner_user)

    begin = await client.post(
        "/auth/passkey/login/begin", json={"email": owner_user.email}
    )
    assert begin.status_code == 200
    challenge_id = begin.json()["challenge_id"]

    with patch(
        "app.api.auth.verify_authentication_response",
        return_value=FakeAuthentication(new_sign_count=1),
    ):
        finish = await client.post(
            "/auth/passkey/login/finish",
            json={"challenge_id": challenge_id, "credential": _envelope_for(cred_id)},
        )

    assert finish.status_code == 200, finish.text
    body = finish.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    # Refresh cookie was set
    set_cookie = finish.headers.get("set-cookie", "")
    assert "aurum_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Strict" in set_cookie or "samesite=strict" in set_cookie.lower()


async def test_login_with_unknown_credential_is_401(client, owner_user) -> None:
    await _register_one(client, owner_user)

    begin = await client.post(
        "/auth/passkey/login/begin", json={"email": owner_user.email}
    )
    challenge_id = begin.json()["challenge_id"]

    other = secrets.token_bytes(32)
    finish = await client.post(
        "/auth/passkey/login/finish",
        json={"challenge_id": challenge_id, "credential": _envelope_for(other)},
    )
    assert finish.status_code == 401


# ---------- /me ----------


async def test_me_requires_token(client) -> None:
    r = await client.get("/me")
    assert r.status_code == 401


async def test_me_returns_current_user(client, owner_user) -> None:
    cred_id = await _register_one(client, owner_user)
    begin = await client.post(
        "/auth/passkey/login/begin", json={"email": owner_user.email}
    )
    with patch(
        "app.api.auth.verify_authentication_response",
        return_value=FakeAuthentication(new_sign_count=1),
    ):
        login = await client.post(
            "/auth/passkey/login/finish",
            json={
                "challenge_id": begin.json()["challenge_id"],
                "credential": _envelope_for(cred_id),
            },
        )
    access = login.json()["access_token"]

    r = await client.get("/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == owner_user.email
    assert body["role"] == UserRole.OWNER.value


# ---------- refresh + reuse detection ----------


async def _login_and_get_refresh_cookie(client, owner_user) -> str:
    cred_id = await _register_one(client, owner_user)
    begin = await client.post(
        "/auth/passkey/login/begin", json={"email": owner_user.email}
    )
    with patch(
        "app.api.auth.verify_authentication_response",
        return_value=FakeAuthentication(new_sign_count=1),
    ):
        login = await client.post(
            "/auth/passkey/login/finish",
            json={
                "challenge_id": begin.json()["challenge_id"],
                "credential": _envelope_for(cred_id),
            },
        )
    return login.cookies["aurum_refresh"]


async def test_refresh_rotates_token(client, owner_user, db_session) -> None:
    refresh_v1 = await _login_and_get_refresh_cookie(client, owner_user)

    r = await client.post("/auth/refresh", cookies={"aurum_refresh": refresh_v1})
    assert r.status_code == 200, r.text
    refresh_v2 = r.cookies["aurum_refresh"]
    assert refresh_v2 != refresh_v1

    # v1 must now be revoked in DB
    rows = (await db_session.execute(select(RefreshToken))).scalars().all()
    by_hash = {bytes(row.token_hash): row for row in rows}
    assert by_hash[hash_refresh_token(refresh_v1)].revoked_at is not None
    assert by_hash[hash_refresh_token(refresh_v2)].revoked_at is None


async def test_refresh_reuse_revokes_all_tokens(
    client, owner_user, db_session
) -> None:
    refresh_v1 = await _login_and_get_refresh_cookie(client, owner_user)

    # First use → success, v1 is now revoked
    ok = await client.post("/auth/refresh", cookies={"aurum_refresh": refresh_v1})
    assert ok.status_code == 200
    refresh_v2 = ok.cookies["aurum_refresh"]

    # Replay v1 → reuse detection triggers, ALL tokens for this user revoked
    replay = await client.post("/auth/refresh", cookies={"aurum_refresh": refresh_v1})
    assert replay.status_code == 401
    assert replay.json()["error"] == "unauthorized"

    rows = (await db_session.execute(select(RefreshToken))).scalars().all()
    assert len(rows) == 2
    assert all(r.revoked_at is not None for r in rows)

    # And v2, the previously-good one, is also dead now
    after = await client.post("/auth/refresh", cookies={"aurum_refresh": refresh_v2})
    assert after.status_code == 401


async def test_refresh_with_no_cookie_is_401(client) -> None:
    r = await client.post("/auth/refresh")
    assert r.status_code == 401


async def test_logout_revokes_refresh(client, owner_user, db_session) -> None:
    refresh = await _login_and_get_refresh_cookie(client, owner_user)
    r = await client.post("/auth/logout", cookies={"aurum_refresh": refresh})
    assert r.status_code == 200
    assert r.json()["revoked"] is True

    # Refresh now fails
    r2 = await client.post("/auth/refresh", cookies={"aurum_refresh": refresh})
    assert r2.status_code == 401
