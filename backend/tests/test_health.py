from __future__ import annotations

import pytest


async def test_healthz_returns_ok(client) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    # Every response carries an X-Request-ID
    assert "x-request-id" in {k.lower() for k in r.headers.keys()}


async def test_readyz_returns_ready(client) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


async def test_readyz_fails_when_db_unreachable(client, monkeypatch) -> None:
    """Simulate DB outage — readyz should bubble up an error."""
    from app.db import session as session_mod

    async def boom():
        raise RuntimeError("db down")

    # Patch the session generator's underlying engine probe
    original = session_mod.SessionLocal

    class _BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _BrokenSession())
    try:
        r = await client.get("/readyz")
        assert r.status_code == 500
        assert r.json()["error"] == "internal_error"
    finally:
        monkeypatch.setattr(session_mod, "SessionLocal", original)
