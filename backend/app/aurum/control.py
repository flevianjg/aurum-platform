"""Atomic control-flag writer for aurum_2.

Three actions: pause, resume, stop. All require OWNER role. All write a row
to audit_log AND control_actions, sharing the same request_id so a future
operator can grep across logs/journal/control_actions to reconstruct
exactly who triggered what.

Atomicity: write to <name>.flag.tmp.<uuid>, fsync, os.replace to final name.
On Linux this is guaranteed atomic by the kernel; on Windows os.replace is
also atomic since Python 3.3. The brain reads the flag with a single open()
so a half-written file is impossible.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import write_audit
from app.core.errors import ForbiddenError
from app.db.models import ControlAction, User, UserRole

logger = logging.getLogger(__name__)

PAUSE_FLAG = "pause.flag"
STOP_FLAG = "stop.flag"


def _control_dir() -> Path:
    return Path(get_settings().AURUM_CONTROL_DIR)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / f"{path.name}.tmp.{uuid.uuid4().hex[:8]}"
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with open(tmp, "wb") as fh:
        fh.write(body)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass  # Windows bind mounts may not support fsync; replace is still atomic
    os.replace(tmp, path)


def _require_owner(user: User) -> None:
    if user.role != UserRole.OWNER:
        raise ForbiddenError("only OWNER may control aurum_2")


def _meta(user: User, request_id: uuid.UUID, *, reason: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requested_by_user_id": str(user.id),
        "request_id": str(request_id),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if reason:
        payload["reason"] = reason
    return payload


async def _record(
    session: AsyncSession,
    *,
    user: User,
    action: str,
    request_id: uuid.UUID,
    metadata: dict[str, Any],
    audit_status: str = "success",
) -> None:
    """Emit one audit_log row + one control_actions row, sharing request_id."""
    await write_audit(
        session,
        action=action,
        status=audit_status,
        user_id=user.id,
        ip_address=metadata.get("ip_address"),
        user_agent=metadata.get("user_agent"),
        request_id=request_id,
        metadata=metadata,
    )
    session.add(
        ControlAction(
            user_id=user.id,
            action=action,
            request_id=request_id,
            control_metadata=metadata,
        )
    )
    await session.flush()


async def write_pause_flag(
    session: AsyncSession, *, user: User, request_id: uuid.UUID
) -> dict[str, Any]:
    _require_owner(user)
    payload = _meta(user, request_id, reason="pause requested by owner")
    _atomic_write_json(_control_dir() / PAUSE_FLAG, payload)
    await _record(
        session,
        user=user,
        action="aurum.pause",
        request_id=request_id,
        metadata=payload,
    )
    return {"request_id": str(request_id), "paused": True}


async def remove_pause_flag(
    session: AsyncSession, *, user: User, request_id: uuid.UUID
) -> dict[str, Any]:
    _require_owner(user)
    target = _control_dir() / PAUSE_FLAG
    try:
        target.unlink()
    except FileNotFoundError:
        # Already unpaused — idempotent
        pass
    payload = _meta(user, request_id, reason="resume requested by owner")
    await _record(
        session,
        user=user,
        action="aurum.resume",
        request_id=request_id,
        metadata=payload,
    )
    return {"request_id": str(request_id), "paused": False}


async def write_stop_flag(
    session: AsyncSession, *, user: User, request_id: uuid.UUID
) -> dict[str, Any]:
    _require_owner(user)
    payload = _meta(user, request_id, reason="stop requested by owner")
    logger.warning("aurum.stop requested by user %s (request_id=%s)", user.id, request_id)
    _atomic_write_json(_control_dir() / STOP_FLAG, payload)
    await _record(
        session,
        user=user,
        action="aurum.stop",
        request_id=request_id,
        metadata=payload,
    )
    return {"request_id": str(request_id), "stop_requested": True}


def read_control_state() -> dict[str, Any]:
    """Read both flag files (no auth — used internally and by /aurum/control)."""
    cdir = _control_dir()
    pause_path = cdir / PAUSE_FLAG
    stop_path = cdir / STOP_FLAG
    pause_meta: dict[str, Any] | None = None
    if pause_path.exists():
        try:
            pause_meta = json.loads(pause_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pause_meta = {"_unreadable": True}
    return {
        "paused": pause_path.exists(),
        "stop_requested": stop_path.exists(),
        "pause_meta": pause_meta,
    }
