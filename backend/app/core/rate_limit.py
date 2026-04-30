"""Rate limiting via slowapi (Redis-backed)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.REDIS_URL,
    default_limits=["200/minute"],
    headers_enabled=True,
)

# Named limit shortcuts (apply with @limiter.limit(AUTH_LIMIT) etc.)
AUTH_LIMIT = "10/minute"
USER_LIMIT = "100/minute"
GLOBAL_IP_LIMIT = "200/minute"
LOGIN_FAIL_LIMIT = "5/15minute"
