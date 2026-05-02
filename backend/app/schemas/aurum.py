"""Phase 4 — schemas for /aurum/* responses.

Most endpoints stream the brain's snapshot or aggregate from paper_events.
Where the wire shape is fully controlled by aurum_2 (snapshot, regime), we
return raw dicts so platform schema doesn't have to track every brain
addition. Where we own the shape (equity bars, daily report, control), we
declare typed models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EquityBar(BaseModel):
    ts: datetime
    equity: float | None = None
    peak_equity: float | None = None
    drawdown_pct: float | None = None


class ClosedPosition(BaseModel):
    """One row from paper_events WHERE event_type='position_closed'.

    Keeps the full payload so any brain-side schema additions surface in the
    UI without a backend change. The named fields are the ones the dashboard
    reliably consumes.
    """

    ts: datetime
    instrument: str | None
    payload: dict[str, Any]


class ClosedPositionsPage(BaseModel):
    items: list[ClosedPosition]
    next_before: datetime | None = Field(
        default=None,
        description="Pass back as 'before' to fetch the next page; None when exhausted.",
    )


class DailyReport(BaseModel):
    date: str
    n_trades: int
    n_wins: int
    n_losses: int
    win_rate: float | None  # None when n_trades == 0
    total_pnl: float
    avg_win: float | None
    avg_loss: float | None
    per_instrument: dict[str, dict[str, float | int]]


class ControlState(BaseModel):
    paused: bool
    stop_requested: bool
    pause_meta: dict[str, Any] | None


class ControlActionResponse(BaseModel):
    request_id: uuid.UUID
    action: Literal["pause", "resume", "stop"]
    paused: bool | None = None
    stop_requested: bool | None = None
