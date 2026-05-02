"""snapshot.read_current_state — happy path, missing file, stale state."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.aurum.snapshot import read_current_state
from app.config import get_settings


@pytest.fixture
def tmp_state(monkeypatch, tmp_path) -> Path:
    target = tmp_path / "current_state.json"
    monkeypatch.setattr(get_settings(), "AURUM_STATE_FILE", str(target))
    return target


def _state(snapshot_ts: datetime) -> dict:
    return {
        "snapshot_ts": snapshot_ts.isoformat(),
        "snapshot_seq": 1,
        "broker": {"equity": 10000.0},
        "engine": {},
        "open_positions": [],
        "control_flags": {"paused": False, "stop_requested": False},
        "instruments": ["EUR_USD"],
    }


def test_returns_none_when_file_missing(tmp_state) -> None:
    assert read_current_state() is None


def test_returns_none_on_invalid_json(tmp_state) -> None:
    tmp_state.write_text("not json", encoding="utf-8")
    assert read_current_state() is None


def test_fresh_snapshot_marks_responsive(tmp_state) -> None:
    now = datetime.now(timezone.utc)
    tmp_state.write_text(json.dumps(_state(now)), encoding="utf-8")
    data = read_current_state()
    assert data is not None
    assert data["is_runner_responsive"] is True
    assert 0.0 <= data["tick_age_seconds"] < 5.0


def test_stale_snapshot_marks_unresponsive(tmp_state) -> None:
    old = datetime.now(timezone.utc) - timedelta(seconds=300)
    tmp_state.write_text(json.dumps(_state(old)), encoding="utf-8")
    data = read_current_state()
    assert data is not None
    assert data["is_runner_responsive"] is False
    assert data["tick_age_seconds"] >= 290


def test_str_format_ts_parses(tmp_state) -> None:
    """aurum_2 emits both 'T' and ' ' separators in ts. We tolerate both."""
    payload = _state(datetime.now(timezone.utc))
    payload["snapshot_ts"] = payload["snapshot_ts"].replace("T", " ")
    tmp_state.write_text(json.dumps(payload), encoding="utf-8")
    data = read_current_state()
    assert data is not None
    assert data["is_runner_responsive"] is True
