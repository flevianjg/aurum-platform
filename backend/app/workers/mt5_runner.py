"""Standalone MT5 subprocess runner — runs on a Windows host (Phase 4 wiring).

The Linux backend container CANNOT run this script: the MetaTrader5 package
is Windows-only. This file exists in the repo as a complete, ready-to-deploy
runner that a Windows host process will exec when the host bridge lands in
Phase 4.

Wire format:
    stdin:  {"operation": "...", "credentials": {...}, "args": {...}}
    stdout: {"ok": true, "data": {...}}                (success)
            {"ok": false, "error_code": "...", "error_message": "..."}  (failure)

Operations:
    test_connection      → {account_number, account_currency, server, balance, equity}
    get_account_info     → {account_number, currency, balance, equity, margin,
                            free_margin, margin_level, server}
    get_positions        → {positions: [{position_id, symbol, side, volume,
                                          open_price, current_price,
                                          unrealized_pnl, open_time,
                                          sl, tp}]}
    get_tick             → {symbol, bid, ask, timestamp_ms}

Exit codes:
    0  → JSON written to stdout (caller parses ok flag)
    1  → unhandled fatal error before/after JSON write

Security:
* Credentials are read once from stdin and held in process memory only for
  the duration of this short-lived process.
* No credential value is ever printed to stdout/stderr in the failure path —
  only sanitized error messages from MT5 last_error().
* The runner kills the MT5 connection on exit (mt5.shutdown()) so credentials
  do not persist across calls.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def _fail(code: str, message: str) -> None:
    _emit({"ok": False, "error_code": code, "error_message": message})
    sys.exit(0)


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    try:
        req = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail("BAD_REQUEST", f"invalid JSON on stdin: {exc}")
        raise  # unreachable
    if not isinstance(req, dict):
        _fail("BAD_REQUEST", "stdin payload must be an object")
        raise  # unreachable
    return req


def _import_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
        return mt5
    except ImportError as exc:
        _fail(
            "MT5_UNAVAILABLE",
            "MetaTrader5 package not installed in this runner environment",
        )
        raise exc  # unreachable


def _connect(mt5, credentials: dict[str, Any]) -> None:
    try:
        login = int(credentials["account"])
    except (KeyError, TypeError, ValueError):
        _fail("VALIDATION", "account must be an integer")
        return
    password = credentials.get("password")
    server = credentials.get("server")
    if not password or not server:
        _fail("VALIDATION", "missing password or server")
        return
    if not mt5.initialize(login=login, password=password, server=server):
        err = mt5.last_error() if hasattr(mt5, "last_error") else (None, "unknown")
        code = str(err[0]) if isinstance(err, tuple) and err else "UNKNOWN"
        # last_error message can include the server name but never the password
        msg = str(err[1]) if isinstance(err, tuple) and len(err) > 1 else "init failed"
        if code in {"-6", "10004"}:
            _fail("AUTH_FAILED", msg)
        else:
            _fail("CONNECTION_ERROR", msg)


def _op_test_connection(mt5) -> dict[str, Any]:
    info = mt5.account_info()
    if info is None:
        _fail("CONNECTION_ERROR", "account_info() returned None")
    return {
        "account_number": str(info.login),
        "account_currency": info.currency,
        "server": info.server,
        "balance": float(info.balance),
        "equity": float(info.equity),
    }


def _op_get_account_info(mt5) -> dict[str, Any]:
    info = mt5.account_info()
    if info is None:
        _fail("CONNECTION_ERROR", "account_info() returned None")
    return {
        "account_number": str(info.login),
        "currency": info.currency,
        "balance": float(info.balance),
        "equity": float(info.equity),
        "margin": float(info.margin),
        "free_margin": float(info.margin_free),
        "margin_level": (
            float(info.margin_level) if info.margin > 0 else None
        ),
        "server": info.server,
    }


def _op_get_positions(mt5) -> dict[str, Any]:
    positions = mt5.positions_get() or []
    out = []
    for p in positions:
        out.append(
            {
                "position_id": str(p.ticket),
                "symbol": p.symbol,
                "side": "BUY" if p.type == 0 else "SELL",
                "volume": float(p.volume),
                "open_price": float(p.price_open),
                "current_price": float(p.price_current),
                "unrealized_pnl": float(p.profit),
                "open_time": float(p.time),
                "sl": float(p.sl) if p.sl else None,
                "tp": float(p.tp) if p.tp else None,
            }
        )
    return {"positions": out}


def _op_get_tick(mt5, args: dict[str, Any]) -> dict[str, Any]:
    symbol = args.get("symbol")
    if not symbol:
        _fail("VALIDATION", "missing symbol")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        _fail("NOT_FOUND", f"no tick for symbol {symbol}")
    return {
        "symbol": symbol,
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "timestamp_ms": int(tick.time_msc) if hasattr(tick, "time_msc") else int(tick.time * 1000),
    }


def main() -> None:
    req = _read_request()
    operation = req.get("operation")
    credentials = req.get("credentials") or {}
    args = req.get("args") or {}

    mt5 = _import_mt5()
    try:
        _connect(mt5, credentials)
        if operation == "test_connection":
            data = _op_test_connection(mt5)
        elif operation == "get_account_info":
            data = _op_get_account_info(mt5)
        elif operation == "get_positions":
            data = _op_get_positions(mt5)
        elif operation == "get_tick":
            data = _op_get_tick(mt5, args)
        else:
            _fail("BAD_REQUEST", f"unknown operation: {operation}")
            return
        _emit({"ok": True, "data": data})
    finally:
        try:
            mt5.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # Last-ditch sanitized error — never echo credentials.
        _fail("UNHANDLED", f"{type(exc).__name__}: {exc}")
