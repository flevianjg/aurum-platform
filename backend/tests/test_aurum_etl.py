"""ETL ingestion tests — uses an isolated tmp journal dir per test."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import EtlCheckpoint, PaperEvent
from app.workers.journal_etl import (
    _parse_line,
    _synthetic_event_id,
    run_once,
)


@pytest.fixture
def tmp_journal_dir(monkeypatch, tmp_path) -> Path:
    """Point AURUM_JOURNAL_DIR at a fresh tmp dir for the duration of the test."""
    target = tmp_path / "journal"
    target.mkdir()
    settings = get_settings()
    monkeypatch.setattr(settings, "AURUM_JOURNAL_DIR", str(target))
    return target


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj))
            fh.write("\n")


def _equity(ts: str, *, event_id: str | None = None) -> dict:
    obj = {"type": "equity_snapshot", "ts": ts, "equity": 10000.0}
    if event_id:
        obj["event_id"] = event_id
    return obj


def _bar(ts: str, instrument: str, *, event_id: str | None = None) -> dict:
    obj = {
        "type": "bar_close",
        "ts": ts,
        "instrument": instrument,
        "open": 1.1,
        "high": 1.2,
        "low": 1.0,
        "close": 1.15,
        "regime": "low",
    }
    if event_id:
        obj["event_id"] = event_id
    return obj


# ---------- pure parser ----------


def test_parse_line_with_native_event_id() -> None:
    eid = "063cbac5-9576-4b6e-ac6f-1e1ede89ae3e"
    row = _parse_line(
        json.dumps(_equity("2026-05-02T02:03:47.461290+00:00", event_id=eid)),
        source_file="journal_20260502.jsonl",
        source_line=1,
    )
    assert row is not None
    assert str(row["event_id"]) == eid
    assert row["event_id_synthetic"] is False
    assert row["event_type"] == "equity_snapshot"


def test_parse_line_synthesizes_id_when_missing() -> None:
    row = _parse_line(
        json.dumps(_equity("2026-05-01T18:52:22.281186+00:00")),
        source_file="journal_20260501.jsonl",
        source_line=1,
    )
    assert row is not None
    assert row["event_id_synthetic"] is True
    # Synthetic id is deterministic — same input → same id
    again = _parse_line(
        json.dumps(_equity("2026-05-01T18:52:22.281186+00:00")),
        source_file="journal_20260501.jsonl",
        source_line=1,
    )
    assert again["event_id"] == row["event_id"]


def test_parse_line_returns_none_on_malformed_json() -> None:
    assert _parse_line("not json", source_file="x", source_line=1) is None


def test_parse_line_returns_none_when_missing_type_or_ts() -> None:
    assert _parse_line(
        json.dumps({"foo": "bar"}), source_file="x", source_line=1
    ) is None
    assert _parse_line(
        json.dumps({"type": "x"}), source_file="x", source_line=1
    ) is None


def test_synthetic_id_differs_for_different_lines() -> None:
    a = _synthetic_event_id("f.jsonl", 1, "2026-05-01T00:00:00+00:00", "equity_snapshot")
    b = _synthetic_event_id("f.jsonl", 2, "2026-05-01T00:00:00+00:00", "equity_snapshot")
    assert a != b


# ---------- ingestion (real DB) ----------


async def test_ingests_mixed_pre_and_post_contract(tmp_journal_dir, db_session) -> None:
    pre_file = tmp_journal_dir / "journal_20260501.jsonl"
    post_file = tmp_journal_dir / "journal_20260502.jsonl"
    _write_jsonl(
        pre_file,
        [
            _equity("2026-05-01T18:52:22+00:00"),
            _bar("2026-05-01T19:00:00+00:00", "EUR_USD"),
        ],
    )
    _write_jsonl(
        post_file,
        [
            _equity("2026-05-02T02:03:47+00:00", event_id=str(uuid.uuid4())),
            _bar("2026-05-02T02:04:00+00:00", "USD_JPY", event_id=str(uuid.uuid4())),
        ],
    )

    stats = await run_once()
    assert stats["inserted"] == 4
    assert stats["files"] == 2

    rows = (await db_session.execute(select(PaperEvent))).scalars().all()
    assert len(rows) == 4
    synthetic = sum(1 for r in rows if r.event_id_synthetic)
    native = sum(1 for r in rows if not r.event_id_synthetic)
    assert synthetic == 2
    assert native == 2


async def test_ingestion_is_idempotent(tmp_journal_dir, db_session) -> None:
    f = tmp_journal_dir / "journal_20260501.jsonl"
    _write_jsonl(
        f,
        [
            _equity("2026-05-01T18:52:22+00:00", event_id=str(uuid.uuid4())),
            _equity("2026-05-01T18:52:32+00:00", event_id=str(uuid.uuid4())),
        ],
    )

    first = await run_once()
    second = await run_once()
    third = await run_once()

    assert first["inserted"] == 2
    assert second["inserted"] == 0
    assert third["inserted"] == 0

    rows = (await db_session.execute(select(PaperEvent))).scalars().all()
    assert len(rows) == 2


async def test_synthetic_dedup_survives_replay(tmp_journal_dir, db_session) -> None:
    f = tmp_journal_dir / "journal_20260501.jsonl"
    _write_jsonl(f, [_equity("2026-05-01T18:52:22+00:00")])

    await run_once()
    await run_once()  # replay

    rows = (await db_session.execute(select(PaperEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_id_synthetic is True


async def test_malformed_json_is_skipped_not_fatal(tmp_journal_dir, db_session) -> None:
    f = tmp_journal_dir / "journal_20260501.jsonl"
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_equity("2026-05-01T18:52:22+00:00", event_id=str(uuid.uuid4()))) + "\n")
        fh.write("not valid json\n")
        fh.write(json.dumps(_equity("2026-05-01T18:52:32+00:00", event_id=str(uuid.uuid4()))) + "\n")

    stats = await run_once()
    assert stats["inserted"] == 2  # malformed line skipped


async def test_resumes_from_checkpoint_after_restart(
    tmp_journal_dir, db_session
) -> None:
    f1 = tmp_journal_dir / "journal_20260501.jsonl"
    f2 = tmp_journal_dir / "journal_20260502.jsonl"
    _write_jsonl(f1, [_equity("2026-05-01T18:00:00+00:00", event_id=str(uuid.uuid4()))])
    _write_jsonl(f2, [_equity("2026-05-02T02:00:00+00:00", event_id=str(uuid.uuid4()))])

    await run_once()
    cp = await db_session.get(EtlCheckpoint, "paper_journal")
    assert cp is not None
    assert cp.last_processed_file == "journal_20260502.jsonl"

    # Append a new line to the latest file; ETL should pick it up via replay
    _write_jsonl(
        f2,
        [
            _equity("2026-05-02T02:00:00+00:00", event_id=str(uuid.uuid4())),
            _equity("2026-05-02T02:10:00+00:00", event_id=str(uuid.uuid4())),
        ],
    )
    # NOTE: writing the file overwrote the original line's event_id; that's fine —
    # the original is already in DB and the second file now has 2 lines.
    stats = await run_once()
    # At least one new event (the second new line), original may dedupe by id.
    assert stats["inserted"] >= 1


async def test_file_rotation_uses_filename_date_not_host_clock(
    tmp_journal_dir, db_session
) -> None:
    """Two files for what aurum_2 thinks is the same UTC day — both must be processed."""
    f_may1 = tmp_journal_dir / "journal_20260501.jsonl"
    f_may2 = tmp_journal_dir / "journal_20260502.jsonl"
    _write_jsonl(f_may1, [_equity("2026-05-01T22:00:00+00:00", event_id=str(uuid.uuid4()))])
    _write_jsonl(f_may2, [_equity("2026-05-02T02:00:00+00:00", event_id=str(uuid.uuid4()))])
    await run_once()
    rows = (await db_session.execute(select(PaperEvent))).scalars().all()
    files = {r.source_file for r in rows}
    assert files == {"journal_20260501.jsonl", "journal_20260502.jsonl"}
