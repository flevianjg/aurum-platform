"""Phase 4 — /aurum/* read + control endpoints.

Endpoint family:
    GET  /aurum/status            (60/min) — live snapshot
    GET  /aurum/equity?days=N     (30/min) — Postgres time-series
    GET  /aurum/positions/open    (60/min) — live snapshot field
    GET  /aurum/positions/closed  (30/min) — paginated history
    GET  /aurum/regime            (60/min) — live snapshot field
    GET  /aurum/report/daily      (30/min) — Postgres aggregation
    GET  /aurum/control           (60/min) — flag state
    POST /aurum/pause             (5/min)  — OWNER only
    POST /aurum/resume            (5/min)  — OWNER only
    POST /aurum/stop              (5/min)  — OWNER only + X-Confirm-Stop header

High-frequency reads (status, positions/open, regime) audit only on FIRST
call per (user_id, endpoint) per backend process — this stops the audit
table from drowning under polling.

All control endpoints write a row to BOTH audit_log and control_actions,
sharing the request_id. The same request_id will be referenced in the
journal's control_event line, so cross-system joins on request_id work.
"""

import uuid
from datetime import date as date_cls
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, user_agent
from app.aurum.control import (
    read_control_state,
    remove_pause_flag,
    write_pause_flag,
    write_stop_flag,
)
from app.aurum.snapshot import read_current_state
from app.core.audit import write_audit
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.rate_limit import limiter
from app.db.models import User
from app.db.session import get_session
from app.schemas.aurum import (
    ClosedPosition,
    ClosedPositionsPage,
    ControlActionResponse,
    ControlState,
    DailyReport,
    EquityBar,
)

router = APIRouter(prefix="/aurum", tags=["aurum"])


# Rate-limit string constants (slowapi accepts the bare strings)
_LIMIT_POLLED = "60/minute"   # /status, /positions/open, /regime, /control
_LIMIT_NORMAL = "30/minute"   # /equity, /positions/closed, /report/daily
_LIMIT_CONTROL = "5/minute"   # /pause, /resume, /stop


# In-memory dedup for high-frequency endpoint audits. Reset on backend
# restart is fine — that just means the user sees one audit row each time
# the backend cycles, not per request.
_AUDIT_SEEN: set[tuple[uuid.UUID, str]] = set()


def _require_owner(user: User) -> None:
    if user.role.value != "OWNER":
        raise ForbiddenError("only OWNER may control aurum_2")


async def _audit_polled_read(
    session: AsyncSession,
    *,
    user: User,
    request: Request,
    endpoint: str,
) -> None:
    key = (user.id, endpoint)
    if key in _AUDIT_SEEN:
        return
    _AUDIT_SEEN.add(key)
    await write_audit(
        session,
        action=f"aurum.read.{endpoint}",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata={"first_seen_in_session": True},
    )


async def _audit_read(
    session: AsyncSession,
    *,
    user: User,
    request: Request,
    endpoint: str,
    metadata: dict | None = None,
) -> None:
    await write_audit(
        session,
        action=f"aurum.read.{endpoint}",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata=metadata,
    )


# ============================================================
# Live snapshot endpoints
# ============================================================


@router.get("/status")
@limiter.limit(_LIMIT_POLLED)
async def aurum_status(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snap = read_current_state()
    if snap is None:
        raise NotFoundError("snapshot file not found")
    await _audit_polled_read(session, user=user, request=request, endpoint="status")
    return snap


@router.get("/positions/open")
@limiter.limit(_LIMIT_POLLED)
async def aurum_open_positions(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list:
    snap = read_current_state()
    await _audit_polled_read(
        session, user=user, request=request, endpoint="positions.open"
    )
    if snap is None:
        return []
    raw = snap.get("open_positions") or []
    return list(raw) if isinstance(raw, list) else []


@router.get("/regime")
@limiter.limit(_LIMIT_POLLED)
async def aurum_regime(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snap = read_current_state()
    await _audit_polled_read(session, user=user, request=request, endpoint="regime")
    if snap is None:
        return {}
    engine = snap.get("engine")
    return engine if isinstance(engine, dict) else {}


@router.get("/control", response_model=ControlState)
@limiter.limit(_LIMIT_POLLED)
async def aurum_control_state(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ControlState:
    state = read_control_state()
    await _audit_polled_read(session, user=user, request=request, endpoint="control")
    return ControlState(**state)


# ============================================================
# Postgres-backed read endpoints
# ============================================================


@router.get("/equity", response_model=list[EquityBar])
@limiter.limit(_LIMIT_NORMAL)
async def aurum_equity(
    request: Request,
    response: Response,
    days: int = Query(default=7, ge=1),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EquityBar]:
    if days > 30:
        raise _Validation("days must be <= 30")

    start_ts = datetime.now(timezone.utc) - timedelta(days=days)

    # 1-minute bars: last value per minute, ordered oldest → newest for charting
    sql = text(
        """
        SELECT ts,
               (payload->>'equity')::float       AS equity,
               (payload->>'peak_equity')::float  AS peak_equity,
               (payload->>'drawdown_pct')::float AS drawdown_pct
        FROM (
            SELECT DISTINCT ON (date_trunc('minute', ts))
                   ts, payload
            FROM paper_events
            WHERE event_type = 'equity_snapshot'
              AND ts >= :start_ts
            ORDER BY date_trunc('minute', ts), ts DESC
        ) latest_per_minute
        ORDER BY ts ASC
        """
    )
    rows = (await session.execute(sql, {"start_ts": start_ts})).mappings().all()
    await _audit_read(
        session,
        user=user,
        request=request,
        endpoint="equity",
        metadata={"days": days, "rows": len(rows)},
    )
    return [EquityBar(**dict(r)) for r in rows]


@router.get("/positions/closed", response_model=ClosedPositionsPage)
@limiter.limit(_LIMIT_NORMAL)
async def aurum_closed_positions(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ClosedPositionsPage:
    params: dict[str, object] = {"limit": limit + 1}
    where = "event_type = 'position_closed'"
    if before is not None:
        where += " AND ts < :before"
        params["before"] = before

    sql = text(
        f"""
        SELECT ts, instrument, payload
        FROM paper_events
        WHERE {where}
        ORDER BY ts DESC
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    items = [
        ClosedPosition(ts=r["ts"], instrument=r["instrument"], payload=dict(r["payload"]))
        for r in rows[:limit]
    ]
    next_before = rows[limit]["ts"] if len(rows) > limit else None

    await _audit_read(
        session,
        user=user,
        request=request,
        endpoint="positions.closed",
        metadata={"returned": len(items), "limit": limit},
    )
    return ClosedPositionsPage(items=items, next_before=next_before)


@router.get("/report/daily", response_model=DailyReport)
@limiter.limit(_LIMIT_NORMAL)
async def aurum_daily_report(
    request: Request,
    response: Response,
    date: str | None = Query(
        default=None, description="UTC date YYYY-MM-DD; defaults to today"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DailyReport:
    target = _parse_utc_date(date)
    day_start = datetime.combine(target, time(0, 0, tzinfo=timezone.utc))
    day_end = day_start + timedelta(days=1)

    summary_sql = text(
        """
        SELECT
            COUNT(*)                                                 AS n_trades,
            COALESCE(SUM((payload->>'pnl')::float), 0)               AS total_pnl,
            COUNT(*) FILTER (WHERE (payload->>'pnl')::float > 0)     AS n_wins,
            COUNT(*) FILTER (WHERE (payload->>'pnl')::float <= 0)    AS n_losses,
            AVG((payload->>'pnl')::float)
              FILTER (WHERE (payload->>'pnl')::float > 0)            AS avg_win,
            AVG((payload->>'pnl')::float)
              FILTER (WHERE (payload->>'pnl')::float <= 0)           AS avg_loss
        FROM paper_events
        WHERE event_type = 'position_closed'
          AND ts >= :day_start
          AND ts <  :day_end
        """
    )
    summary = (
        await session.execute(summary_sql, {"day_start": day_start, "day_end": day_end})
    ).mappings().one()

    per_inst_sql = text(
        """
        SELECT instrument,
               COUNT(*)                                  AS n_trades,
               COALESCE(SUM((payload->>'pnl')::float),0) AS total_pnl
        FROM paper_events
        WHERE event_type = 'position_closed'
          AND ts >= :day_start
          AND ts <  :day_end
          AND instrument IS NOT NULL
        GROUP BY instrument
        """
    )
    per_inst_rows = (
        await session.execute(per_inst_sql, {"day_start": day_start, "day_end": day_end})
    ).mappings().all()

    n_trades = int(summary["n_trades"])
    n_wins = int(summary["n_wins"])
    n_losses = int(summary["n_losses"])
    win_rate = (n_wins / n_trades) if n_trades > 0 else None

    await _audit_read(
        session,
        user=user,
        request=request,
        endpoint="report.daily",
        metadata={"date": target.isoformat(), "n_trades": n_trades},
    )

    return DailyReport(
        date=target.isoformat(),
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        win_rate=win_rate,
        total_pnl=float(summary["total_pnl"]),
        avg_win=float(summary["avg_win"]) if summary["avg_win"] is not None else None,
        avg_loss=float(summary["avg_loss"]) if summary["avg_loss"] is not None else None,
        per_instrument={
            r["instrument"]: {
                "n_trades": int(r["n_trades"]),
                "total_pnl": float(r["total_pnl"]),
            }
            for r in per_inst_rows
        },
    )


# ============================================================
# Control endpoints
# ============================================================


@router.post("/pause", response_model=ControlActionResponse)
@limiter.limit(_LIMIT_CONTROL)
async def aurum_pause(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ControlActionResponse:
    _require_owner(user)
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4()
    await write_pause_flag(session, user=user, request_id=request_id)
    return ControlActionResponse(
        request_id=request_id, action="pause", paused=True
    )


@router.post("/resume", response_model=ControlActionResponse)
@limiter.limit(_LIMIT_CONTROL)
async def aurum_resume(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ControlActionResponse:
    _require_owner(user)
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4()
    await remove_pause_flag(session, user=user, request_id=request_id)
    return ControlActionResponse(
        request_id=request_id, action="resume", paused=False
    )


@router.post("/stop", response_model=ControlActionResponse)
@limiter.limit(_LIMIT_CONTROL)
async def aurum_stop(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    x_confirm_stop: str | None = Header(default=None, alias="X-Confirm-Stop"),
) -> ControlActionResponse:
    _require_owner(user)
    if (x_confirm_stop or "").strip().lower() != "yes":
        raise _BadRequest("X-Confirm-Stop: yes header required for /aurum/stop")
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4()
    await write_stop_flag(session, user=user, request_id=request_id)
    return ControlActionResponse(
        request_id=request_id, action="stop", stop_requested=True
    )


# ============================================================
# Helpers
# ============================================================


class _Validation(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class _BadRequest(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"


def _parse_utc_date(value: str | None) -> date_cls:
    if not value:
        return datetime.now(timezone.utc).date()
    try:
        return date_cls.fromisoformat(value)
    except ValueError as exc:
        raise _Validation("date must be YYYY-MM-DD") from exc
