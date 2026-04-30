"""Append-only audit logging.

The DB enforces append-only via triggers; this module is the only sanctioned
write path from app code. Never log credential material here.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


# Sentinel keys we will scrub from metadata before insertion
_FORBIDDEN_KEYS = frozenset(
    {
        "password",
        "jwt",
        "access_token",
        "refresh_token",
        "token",
        "authorization",
        "cookie",
        "set-cookie",
        "credential",
        "credentials",
        "secret",
        "private_key",
    }
)


def _scrub(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return metadata
    cleaned: dict[str, Any] = {}
    for k, v in metadata.items():
        if k.lower() in _FORBIDDEN_KEYS:
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = _scrub(v)  # type: ignore[assignment]
        else:
            cleaned[k] = v
    return cleaned


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    status: str,
    user_id: uuid.UUID | None = None,
    resource: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert one audit_log row. Caller is responsible for commit."""
    row = AuditLog(
        action=action,
        status=status,
        user_id=user_id,
        resource=resource,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        audit_metadata=_scrub(metadata),
    )
    session.add(row)
    await session.flush()
