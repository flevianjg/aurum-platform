"""Phase 3 sub-phase 4 — passkey CRUD + logout-all endpoints."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models import Passkey, RefreshToken, User, UserRole


def _bearer(user) -> dict[str, str]:
    token, _ = create_access_token(user_id=user.id, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def member_user(db_session) -> User:
    u = User(
        email="member-pk@example.com",
        display_name="Member PK",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _create_passkey(db_session, user: User, *, nickname: str | None = None) -> Passkey:
    p = Passkey(
        user_id=user.id,
        credential_id=secrets.token_bytes(32),
        public_key=secrets.token_bytes(64),
        sign_count=0,
        nickname=nickname,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


# ---------- GET /me/passkeys ----------


async def test_list_passkeys_returns_only_callers(client, owner_user, member_user, db_session) -> None:
    await _create_passkey(db_session, owner_user, nickname="Owner iPhone")
    await _create_passkey(db_session, owner_user, nickname="Owner Yubikey")
    await _create_passkey(db_session, member_user, nickname="Member Phone")

    r = await client.get("/me/passkeys", headers=_bearer(owner_user))
    assert r.status_code == 200
    body = r.json()
    nicknames = {p["nickname"] for p in body}
    assert nicknames == {"Owner iPhone", "Owner Yubikey"}
    # No credential_id / public_key bytes leak
    for p in body:
        assert "credential_id" not in p
        assert "public_key" not in p


async def test_list_passkeys_requires_auth(client) -> None:
    r = await client.get("/me/passkeys")
    assert r.status_code == 401


# ---------- PATCH /me/passkeys/{id} ----------


async def test_rename_passkey_succeeds(client, owner_user, db_session) -> None:
    p = await _create_passkey(db_session, owner_user, nickname="old name")
    r = await client.patch(
        f"/me/passkeys/{p.id}",
        json={"nickname": "Flevian iPhone 15"},
        headers=_bearer(owner_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["nickname"] == "Flevian iPhone 15"

    await db_session.refresh(p)
    assert p.nickname == "Flevian iPhone 15"


async def test_rename_other_users_passkey_returns_404(
    client, owner_user, member_user, db_session
) -> None:
    p = await _create_passkey(db_session, owner_user, nickname="Owner")
    r = await client.patch(
        f"/me/passkeys/{p.id}",
        json={"nickname": "Pwned"},
        headers=_bearer(member_user),
    )
    assert r.status_code == 404


async def test_rename_validates_nickname_length(client, owner_user, db_session) -> None:
    p = await _create_passkey(db_session, owner_user)
    r = await client.patch(
        f"/me/passkeys/{p.id}", json={"nickname": ""}, headers=_bearer(owner_user)
    )
    assert r.status_code == 422


# ---------- DELETE /me/passkeys/{id} ----------


async def test_remove_passkey_succeeds_when_more_than_one(
    client, owner_user, db_session
) -> None:
    keep = await _create_passkey(db_session, owner_user, nickname="keep")
    drop = await _create_passkey(db_session, owner_user, nickname="drop")
    r = await client.delete(f"/me/passkeys/{drop.id}", headers=_bearer(owner_user))
    assert r.status_code == 204

    rows = (await db_session.execute(select(Passkey).where(Passkey.user_id == owner_user.id))).scalars().all()
    assert {row.id for row in rows} == {keep.id}


async def test_remove_last_passkey_is_409(client, owner_user, db_session) -> None:
    p = await _create_passkey(db_session, owner_user, nickname="only")
    r = await client.delete(f"/me/passkeys/{p.id}", headers=_bearer(owner_user))
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "conflict"

    # Row still exists
    still = await db_session.get(Passkey, p.id)
    assert still is not None


async def test_remove_other_users_passkey_returns_404(
    client, owner_user, member_user, db_session
) -> None:
    p = await _create_passkey(db_session, owner_user, nickname="Owner sole")
    # member_user has no passkey of their own
    r = await client.delete(f"/me/passkeys/{p.id}", headers=_bearer(member_user))
    assert r.status_code == 404


# ---------- POST /auth/logout-all ----------


async def test_logout_all_revokes_every_session(client, owner_user, db_session) -> None:
    from datetime import datetime, timedelta, timezone

    from app.core.security import generate_refresh_token

    # Seed three live refresh tokens for owner_user
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    for _ in range(3):
        _, digest, _ = generate_refresh_token()
        db_session.add(
            RefreshToken(user_id=owner_user.id, token_hash=digest, expires_at=expires)
        )
    await db_session.commit()

    r = await client.post("/auth/logout-all", headers=_bearer(owner_user))
    assert r.status_code == 204

    rows = (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == owner_user.id))).scalars().all()
    assert len(rows) == 3
    assert all(row.revoked_at is not None for row in rows)


async def test_logout_all_requires_auth(client) -> None:
    r = await client.post("/auth/logout-all")
    assert r.status_code == 401
