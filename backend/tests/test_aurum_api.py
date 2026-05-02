"""Phase 4 sub-phase 4.2 — /aurum/* endpoint tests."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api import aurum as aurum_module
from app.aurum.control import PAUSE_FLAG, STOP_FLAG
from app.config import get_settings
from app.core.security import create_access_token
from app.db.models import AuditLog, ControlAction, PaperEvent, User, UserRole


def _bearer(user) -> dict[str, str]:
    token, _ = create_access_token(user_id=user.id, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ---------- shared fixtures ----------


@pytest.fixture
async def viewer_user(db_session) -> User:
    u = User(
        email="aurum-viewer@example.com",
        display_name="Viewer",
        role=UserRole.VIEWER,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
def tmp_state(monkeypatch, tmp_path) -> Path:
    target = tmp_path / "current_state.json"
    monkeypatch.setattr(get_settings(), "AURUM_STATE_FILE", str(target))
    return target


@pytest.fixture
def tmp_control(monkeypatch, tmp_path) -> Path:
    target = tmp_path / "control"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "AURUM_CONTROL_DIR", str(target))
    return target


@pytest.fixture(autouse=True)
def reset_audit_dedup():
    aurum_module._AUDIT_SEEN.clear()
    yield
    aurum_module._AUDIT_SEEN.clear()


def _fresh_snapshot(extra: dict | None = None) -> dict:
    base = {
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
        "snapshot_seq": 7,
        "broker": {"equity": 10000.0, "peak_equity": 10000.0},
        "engine": {
            "EUR_USD": {"last_regime": "low", "model_ready": True},
            "USD_JPY": {"last_regime": "med", "model_ready": True},
        },
        "open_positions": [
            {"position_id": "p1", "symbol": "EUR_USD", "side": "BUY", "volume": 1000.0}
        ],
        "control_flags": {"paused": False, "stop_requested": False},
        "instruments": ["EUR_USD", "USD_JPY"],
    }
    if extra:
        base.update(extra)
    return base


def _write_state(path: Path, snapshot: dict) -> None:
    path.write_text(json.dumps(snapshot), encoding="utf-8")


async def _seed_equity_event(
    db_session, *, ts: datetime, equity: float, drawdown_pct: float = 0.0
) -> PaperEvent:
    row = PaperEvent(
        event_id=uuid.uuid4(),
        ts=ts,
        instrument=None,
        event_type="equity_snapshot",
        payload={
            "type": "equity_snapshot",
            "ts": ts.isoformat(),
            "equity": equity,
            "peak_equity": equity,
            "drawdown_pct": drawdown_pct,
        },
        source_file="journal_test.jsonl",
        source_line=1,
        event_id_synthetic=False,
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def _seed_closed_position(
    db_session,
    *,
    ts: datetime,
    instrument: str,
    pnl: float,
    side: str = "BUY",
) -> PaperEvent:
    row = PaperEvent(
        event_id=uuid.uuid4(),
        ts=ts,
        instrument=instrument,
        event_type="position_closed",
        payload={
            "type": "position_closed",
            "ts": ts.isoformat(),
            "instrument": instrument,
            "side": side,
            "pnl": pnl,
            "entry_price": 1.10,
            "exit_price": 1.11 if pnl > 0 else 1.09,
        },
        source_file="journal_test.jsonl",
        source_line=2,
        event_id_synthetic=False,
    )
    db_session.add(row)
    await db_session.commit()
    return row


# =======================================================
# Auth on every endpoint
# =======================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/aurum/status"),
        ("GET", "/aurum/equity"),
        ("GET", "/aurum/positions/open"),
        ("GET", "/aurum/positions/closed"),
        ("GET", "/aurum/regime"),
        ("GET", "/aurum/report/daily"),
        ("GET", "/aurum/control"),
        ("POST", "/aurum/pause"),
        ("POST", "/aurum/resume"),
        ("POST", "/aurum/stop"),
    ],
)
async def test_unauthenticated_returns_401(client, method, path) -> None:
    if method == "GET":
        r = await client.get(path)
    else:
        r = await client.post(path)
    assert r.status_code == 401, f"{method} {path}"


# =======================================================
# /aurum/status
# =======================================================


async def test_status_fresh_snapshot_returns_responsive(
    client, owner_user, tmp_state
) -> None:
    _write_state(tmp_state, _fresh_snapshot())
    r = await client.get("/aurum/status", headers=_bearer(owner_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_runner_responsive"] is True
    assert body["tick_age_seconds"] >= 0
    assert "engine" in body and "open_positions" in body


async def test_status_missing_snapshot_returns_404(
    client, owner_user, tmp_state
) -> None:
    # tmp_state is the path but file doesn't exist yet
    r = await client.get("/aurum/status", headers=_bearer(owner_user))
    assert r.status_code == 404


async def test_status_stale_snapshot_returns_200_with_unresponsive_flag(
    client, owner_user, tmp_state
) -> None:
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    snap = _fresh_snapshot()
    snap["snapshot_ts"] = old_ts
    _write_state(tmp_state, snap)

    r = await client.get("/aurum/status", headers=_bearer(owner_user))
    assert r.status_code == 200
    body = r.json()
    assert body["is_runner_responsive"] is False
    assert body["tick_age_seconds"] > 60


# =======================================================
# /aurum/positions/open + /aurum/regime
# =======================================================


async def test_open_positions_returns_snapshot_array(
    client, owner_user, tmp_state
) -> None:
    _write_state(tmp_state, _fresh_snapshot())
    r = await client.get("/aurum/positions/open", headers=_bearer(owner_user))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["symbol"] == "EUR_USD"


async def test_open_positions_returns_empty_when_snapshot_missing(
    client, owner_user, tmp_state
) -> None:
    r = await client.get("/aurum/positions/open", headers=_bearer(owner_user))
    assert r.status_code == 200
    assert r.json() == []


async def test_regime_returns_engine_block(client, owner_user, tmp_state) -> None:
    _write_state(tmp_state, _fresh_snapshot())
    r = await client.get("/aurum/regime", headers=_bearer(owner_user))
    assert r.status_code == 200
    body = r.json()
    assert "EUR_USD" in body and body["EUR_USD"]["last_regime"] == "low"


# =======================================================
# /aurum/equity
# =======================================================


async def test_equity_returns_one_minute_bars(client, owner_user, db_session) -> None:
    # Two distinct minute buckets, recent enough to be inside days=1.
    m1 = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=2)
    m2 = m1 + timedelta(minutes=1)

    # m1: single event
    await _seed_equity_event(db_session, ts=m1 + timedelta(seconds=10), equity=50.0)
    # m2: two events in the same minute → later one wins
    await _seed_equity_event(db_session, ts=m2 + timedelta(seconds=5), equity=100.0)
    await _seed_equity_event(db_session, ts=m2 + timedelta(seconds=30), equity=200.0)

    r = await client.get("/aurum/equity?days=1", headers=_bearer(owner_user))
    assert r.status_code == 200, r.text
    bars = r.json()
    assert len(bars) == 2
    assert bars[0]["equity"] == 50.0
    assert bars[-1]["equity"] == 200.0


async def test_equity_days_cap(client, owner_user) -> None:
    r = await client.get("/aurum/equity?days=31", headers=_bearer(owner_user))
    assert r.status_code == 422


@pytest.mark.parametrize("days", [1, 7, 30])
async def test_equity_accepts_valid_window(client, owner_user, days) -> None:
    r = await client.get(f"/aurum/equity?days={days}", headers=_bearer(owner_user))
    assert r.status_code == 200


# =======================================================
# /aurum/positions/closed
# =======================================================


async def test_closed_positions_pagination_via_before_cursor(
    client, owner_user, db_session
) -> None:
    base = datetime.now(timezone.utc).replace(microsecond=0)
    for i in range(5):
        await _seed_closed_position(
            db_session, ts=base - timedelta(minutes=i), instrument="EUR_USD", pnl=10.0 + i
        )

    # Page 1: limit 2 → newest 2 returned, plus next_before pointing at item 3
    r1 = await client.get(
        "/aurum/positions/closed?limit=2", headers=_bearer(owner_user)
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["next_before"] is not None

    # Page 2 using next_before
    r2 = await client.get(
        f"/aurum/positions/closed?limit=2&before={body1['next_before']}",
        headers=_bearer(owner_user),
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["items"]) == 2
    # No overlap between pages
    page1_ts = {it["ts"] for it in body1["items"]}
    page2_ts = {it["ts"] for it in body2["items"]}
    assert page1_ts.isdisjoint(page2_ts)


async def test_closed_positions_limit_cap(client, owner_user) -> None:
    r = await client.get(
        "/aurum/positions/closed?limit=500", headers=_bearer(owner_user)
    )
    assert r.status_code == 422


# =======================================================
# /aurum/report/daily
# =======================================================


async def test_daily_report_zeros_when_empty(client, owner_user) -> None:
    r = await client.get("/aurum/report/daily?date=2026-01-01", headers=_bearer(owner_user))
    assert r.status_code == 200
    body = r.json()
    assert body["n_trades"] == 0
    assert body["total_pnl"] == 0.0
    assert body["win_rate"] is None


async def test_daily_report_aggregates(client, owner_user, db_session) -> None:
    target = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    await _seed_closed_position(db_session, ts=target, instrument="EUR_USD", pnl=10.0)
    await _seed_closed_position(
        db_session, ts=target + timedelta(minutes=5), instrument="EUR_USD", pnl=-5.0
    )
    await _seed_closed_position(
        db_session, ts=target + timedelta(minutes=10), instrument="USD_JPY", pnl=15.0
    )

    r = await client.get(
        f"/aurum/report/daily?date={target.date().isoformat()}",
        headers=_bearer(owner_user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_trades"] == 3
    assert body["n_wins"] == 2
    assert body["n_losses"] == 1
    assert body["win_rate"] == pytest.approx(2 / 3)
    assert body["total_pnl"] == pytest.approx(20.0)
    assert "EUR_USD" in body["per_instrument"]
    assert body["per_instrument"]["EUR_USD"]["n_trades"] == 2


async def test_daily_report_invalid_date_format(client, owner_user) -> None:
    r = await client.get(
        "/aurum/report/daily?date=2026/01/01", headers=_bearer(owner_user)
    )
    assert r.status_code == 422


# =======================================================
# /aurum/control + pause/resume/stop
# =======================================================


async def test_control_state_no_flags(client, owner_user, tmp_control) -> None:
    r = await client.get("/aurum/control", headers=_bearer(owner_user))
    assert r.status_code == 200
    assert r.json() == {"paused": False, "stop_requested": False, "pause_meta": None}


async def test_pause_writes_flag_audit_and_control_actions(
    client, owner_user, tmp_control, db_session
) -> None:
    r = await client.post("/aurum/pause", headers=_bearer(owner_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["paused"] is True
    assert body["action"] == "pause"

    # Flag exists and is atomic (no .tmp leftovers)
    assert (tmp_control / PAUSE_FLAG).exists()
    leftovers = [p.name for p in tmp_control.iterdir() if ".tmp" in p.name]
    assert leftovers == []

    # audit_log + control_actions both have the same request_id
    audits = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "aurum.pause")
        )
    ).scalars().all()
    actions = (
        await db_session.execute(
            select(ControlAction).where(ControlAction.action == "aurum.pause")
        )
    ).scalars().all()
    assert len(audits) == 1 and len(actions) == 1
    assert audits[0].request_id == actions[0].request_id
    assert str(actions[0].request_id) == body["request_id"]


async def test_resume_removes_flag(client, owner_user, tmp_control, db_session) -> None:
    await client.post("/aurum/pause", headers=_bearer(owner_user))
    assert (tmp_control / PAUSE_FLAG).exists()

    r = await client.post("/aurum/resume", headers=_bearer(owner_user))
    assert r.status_code == 200
    assert r.json()["paused"] is False
    assert not (tmp_control / PAUSE_FLAG).exists()


async def test_pause_viewer_forbidden(client, viewer_user, tmp_control) -> None:
    r = await client.post("/aurum/pause", headers=_bearer(viewer_user))
    assert r.status_code == 403
    assert not (tmp_control / PAUSE_FLAG).exists()


async def test_resume_viewer_forbidden(client, viewer_user) -> None:
    r = await client.post("/aurum/resume", headers=_bearer(viewer_user))
    assert r.status_code == 403


async def test_stop_without_confirm_header_is_400(
    client, owner_user, tmp_control
) -> None:
    r = await client.post("/aurum/stop", headers=_bearer(owner_user))
    assert r.status_code == 400
    assert not (tmp_control / STOP_FLAG).exists()


async def test_stop_with_confirm_header_writes_flag(
    client, owner_user, tmp_control, db_session
) -> None:
    headers = {**_bearer(owner_user), "X-Confirm-Stop": "yes"}
    r = await client.post("/aurum/stop", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stop_requested"] is True
    assert (tmp_control / STOP_FLAG).exists()

    # control_actions row created
    actions = (
        await db_session.execute(
            select(ControlAction).where(ControlAction.action == "aurum.stop")
        )
    ).scalars().all()
    assert len(actions) == 1


async def test_stop_viewer_forbidden(client, viewer_user) -> None:
    headers = {**_bearer(viewer_user), "X-Confirm-Stop": "yes"}
    r = await client.post("/aurum/stop", headers=headers)
    assert r.status_code == 403


# =======================================================
# Audit dedup for high-frequency endpoints
# =======================================================


async def test_high_freq_audit_only_once_per_session(
    client, owner_user, tmp_state, db_session
) -> None:
    _write_state(tmp_state, _fresh_snapshot())
    # Hit /aurum/status five times
    for _ in range(5):
        r = await client.get("/aurum/status", headers=_bearer(owner_user))
        assert r.status_code == 200

    audits = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "aurum.read.status")
        )
    ).scalars().all()
    assert len(audits) == 1


async def test_low_freq_endpoints_audit_every_call(
    client, owner_user, db_session
) -> None:
    for _ in range(3):
        r = await client.get("/aurum/equity?days=1", headers=_bearer(owner_user))
        assert r.status_code == 200

    audits = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "aurum.read.equity")
        )
    ).scalars().all()
    assert len(audits) == 3


# =======================================================
# Rate limit enforcement (one polled endpoint)
# =======================================================


async def test_rate_limit_enforced_on_pause(
    app, client, owner_user, tmp_control
) -> None:
    """Pause is the lowest-budget endpoint at 5/min — easiest to trip."""
    app.state.limiter.enabled = True
    try:
        ok = 0
        rate_limited = 0
        for _ in range(10):
            r = await client.post("/aurum/pause", headers=_bearer(owner_user))
            if r.status_code == 200:
                ok += 1
            elif r.status_code == 429:
                rate_limited += 1
        assert ok >= 1, "expected at least one success before tripping"
        assert rate_limited >= 1, "expected at least one 429 after exceeding 5/min"
    finally:
        app.state.limiter.enabled = False
