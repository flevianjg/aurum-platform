"""Credential store: ownership, encryption persistence, test_stored side effects."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.brokers.credential_store import (
    CredentialOwnershipError,
    create_broker_account,
    list_user_accounts,
    load_credentials,
    verify_stored_credentials,
)
from app.db.models import BrokerAccount, BrokerHealthCheck, User, UserRole


@pytest.fixture
async def second_user(db_session) -> User:
    u = User(
        email="member@example.com",
        display_name="Member",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _create_oanda(db_session, owner_user) -> BrokerAccount:
    """Helper that uses the OANDA credential shape and MT5 broker_type so we
    don't have to hit the OANDA API. We use MT5 with TEST_MODE for the
    actual happy path."""
    creds = {"account": 12345678, "password": "pw", "server": "Exness-Trial"}
    row, _ = await create_broker_account(
        db_session,
        user_id=owner_user.id,
        broker_type="MT5",
        account_label="OwnerMT5",
        credentials=creds,
    )
    await db_session.commit()
    return row


async def test_create_encrypts_and_persists(db_session, owner_user) -> None:
    row = await _create_oanda(db_session, owner_user)
    assert row.id is not None
    assert row.encrypted_credentials != b""
    assert len(row.credential_nonce) == 24
    # plaintext password must not appear in stored ciphertext
    assert b"pw" not in row.encrypted_credentials
    assert row.last_test_status == "success"
    assert row.account_number == "12345678"  # MT5 TEST_MODE echoes the account input


async def test_load_credentials_round_trip(db_session, owner_user) -> None:
    row = await _create_oanda(db_session, owner_user)
    creds = await load_credentials(
        db_session, broker_account_id=row.id, user_id=owner_user.id
    )
    assert creds["password"] == "pw"
    assert creds["server"] == "Exness-Trial"
    assert int(creds["account"]) == 12345678
    # The discriminator must NOT be in the stored blob
    assert "broker_type" not in creds


async def test_load_credentials_by_other_user_raises(
    db_session, owner_user, second_user
) -> None:
    row = await _create_oanda(db_session, owner_user)
    with pytest.raises(CredentialOwnershipError):
        await load_credentials(
            db_session, broker_account_id=row.id, user_id=second_user.id
        )


async def test_load_credentials_nonexistent_raises(db_session, owner_user) -> None:
    with pytest.raises(LookupError):
        await load_credentials(
            db_session, broker_account_id=uuid.uuid4(), user_id=owner_user.id
        )


async def test_test_stored_updates_metadata_and_writes_health_row(
    db_session, owner_user
) -> None:
    row = await _create_oanda(db_session, owner_user)
    before_count = (
        await db_session.execute(select(BrokerHealthCheck))
    ).scalars().all()
    assert before_count == []

    result = await verify_stored_credentials(
        db_session, broker_account_id=row.id, user_id=owner_user.id
    )
    await db_session.commit()
    assert result.success is True

    await db_session.refresh(row)
    assert row.last_test_status == "success"
    assert row.last_tested_at is not None

    after = (await db_session.execute(select(BrokerHealthCheck))).scalars().all()
    assert len(after) == 1
    assert after[0].broker_account_id == row.id
    assert after[0].status == "success"
    assert after[0].latency_ms is not None and after[0].latency_ms >= 0


async def test_list_user_accounts_isolates_by_owner(
    db_session, owner_user, second_user
) -> None:
    await _create_oanda(db_session, owner_user)

    other_creds = {"account": 99999999, "password": "z", "server": "Exness-Other"}
    await create_broker_account(
        db_session,
        user_id=second_user.id,
        broker_type="MT5",
        account_label="MemberMT5",
        credentials=other_creds,
    )
    await db_session.commit()

    owner_rows = await list_user_accounts(db_session, user_id=owner_user.id)
    member_rows = await list_user_accounts(db_session, user_id=second_user.id)
    assert {r.account_label for r in owner_rows} == {"OwnerMT5"}
    assert {r.account_label for r in member_rows} == {"MemberMT5"}
