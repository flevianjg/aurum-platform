"""Control-flag writer — atomicity, OWNER role, audit + control_actions rows."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.aurum.control import (
    PAUSE_FLAG,
    STOP_FLAG,
    read_control_state,
    remove_pause_flag,
    write_pause_flag,
    write_stop_flag,
)
from app.config import get_settings
from app.core.errors import ForbiddenError
from app.db.models import AuditLog, ControlAction, User, UserRole


@pytest.fixture
def tmp_control(monkeypatch, tmp_path) -> Path:
    target = tmp_path / "control"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "AURUM_CONTROL_DIR", str(target))
    return target


@pytest.fixture
async def viewer_user(db_session) -> User:
    u = User(
        email="ctrl-viewer@example.com",
        display_name="Viewer",
        role=UserRole.VIEWER,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


# ---------- pause / resume ----------


async def test_pause_writes_flag_and_audit(tmp_control, db_session, owner_user) -> None:
    rid = uuid.uuid4()
    result = await write_pause_flag(db_session, user=owner_user, request_id=rid)
    await db_session.commit()

    assert result == {"request_id": str(rid), "paused": True}

    flag = tmp_control / PAUSE_FLAG
    assert flag.exists()
    payload = json.loads(flag.read_text(encoding="utf-8"))
    assert payload["request_id"] == str(rid)
    assert payload["requested_by_user_id"] == str(owner_user.id)

    # Atomic — no .tmp files left behind
    leftovers = [p.name for p in tmp_control.iterdir() if ".tmp" in p.name]
    assert leftovers == []

    # Audit + control_actions rows
    actions = (await db_session.execute(select(ControlAction))).scalars().all()
    assert len(actions) == 1
    assert actions[0].action == "aurum.pause"
    assert actions[0].request_id == rid

    audits = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "aurum.pause")
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].request_id == rid


async def test_resume_unlinks_flag_idempotently(
    tmp_control, db_session, owner_user
) -> None:
    await write_pause_flag(db_session, user=owner_user, request_id=uuid.uuid4())
    assert (tmp_control / PAUSE_FLAG).exists()

    await remove_pause_flag(db_session, user=owner_user, request_id=uuid.uuid4())
    assert not (tmp_control / PAUSE_FLAG).exists()

    # Second remove on already-removed flag is fine
    await remove_pause_flag(db_session, user=owner_user, request_id=uuid.uuid4())
    await db_session.commit()


async def test_pause_rejects_non_owner(tmp_control, db_session, viewer_user) -> None:
    with pytest.raises(ForbiddenError):
        await write_pause_flag(db_session, user=viewer_user, request_id=uuid.uuid4())
    assert not (tmp_control / PAUSE_FLAG).exists()


async def test_stop_writes_flag(tmp_control, db_session, owner_user) -> None:
    rid = uuid.uuid4()
    result = await write_stop_flag(db_session, user=owner_user, request_id=rid)
    await db_session.commit()
    assert result == {"request_id": str(rid), "stop_requested": True}
    assert (tmp_control / STOP_FLAG).exists()


async def test_read_control_state_reflects_files(tmp_control, db_session, owner_user) -> None:
    state = read_control_state()
    assert state == {"paused": False, "stop_requested": False, "pause_meta": None}

    await write_pause_flag(db_session, user=owner_user, request_id=uuid.uuid4())
    state = read_control_state()
    assert state["paused"] is True
    assert state["stop_requested"] is False
    assert state["pause_meta"] is not None
    assert state["pause_meta"]["requested_by_user_id"] == str(owner_user.id)
