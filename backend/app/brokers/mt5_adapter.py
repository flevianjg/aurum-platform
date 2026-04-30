"""MetaTrader 5 adapter.

CRITICAL: the MetaTrader5 Python package is Windows-only and single-threaded
per process. Phase 2 implements the adapter SHAPE so it's testable; real MT5
calls are not exercised in this Linux container.

Behavior:
* If settings.MT5_TEST_MODE is True (default): every method returns canned
  successful results, exercising the adapter contract without launching a
  subprocess. This is what the Linux backend container uses today and what
  the test suite relies on.
* If MT5_TEST_MODE is False AND settings.WINDOWS_HOST_RUNNER is set: the
  adapter spawns the runner script via asyncio.create_subprocess_exec and
  communicates JSON over stdin/stdout. This path is implemented but not
  exercised in Phase 2 — Phase 4 will deploy mt5_runner.py on a Windows host
  and wire it up.
* If MT5_TEST_MODE is False AND WINDOWS_HOST_RUNNER is unset: every call
  raises BrokerConnectionError with a clear message — fail loud rather than
  pretend to work.

Required credential fields: ['account', 'password', 'server']
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings

from .base import AccountInfo, BrokerAdapter, Position, TestConnectionResult, Tick
from .exceptions import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerError,
    BrokerValidationError,
)

logger = logging.getLogger(__name__)

_OP_TIMEOUT_S = 30.0  # connection ops
_READ_TIMEOUT_S = 10.0  # read ops


class MT5Adapter(BrokerAdapter):
    @classmethod
    def required_credential_fields(cls) -> list[str]:
        return ["account", "password", "server"]

    @staticmethod
    def _validate(credentials: dict[str, Any]) -> None:
        for field in MT5Adapter.required_credential_fields():
            if field not in credentials:
                raise BrokerValidationError(f"missing credential field: {field}")
        try:
            int(credentials["account"])
        except (TypeError, ValueError) as exc:
            raise BrokerValidationError("account must be an integer") from exc

    # ---------- TEST_MODE canned responses ----------

    def _canned_test_result(self, credentials: dict[str, Any]) -> TestConnectionResult:
        return TestConnectionResult(
            success=True,
            account_number=str(credentials["account"]),
            account_currency="USD",
            server=str(credentials["server"]),
            balance=10_000.0,
            equity=10_000.0,
        )

    def _canned_account_info(self, credentials: dict[str, Any]) -> AccountInfo:
        return AccountInfo(
            account_number=str(credentials["account"]),
            currency="USD",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=None,
            server=str(credentials["server"]),
        )

    def _canned_positions(self) -> list[Position]:
        return []  # no positions in test mode

    def _canned_tick(self, symbol: str) -> Tick:
        return Tick(
            symbol=symbol,
            bid=1.0,
            ask=1.0001,
            timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        )

    # ---------- Subprocess bridge (Phase 4 wiring) ----------

    async def _run_subprocess(
        self,
        operation: str,
        credentials: dict[str, Any],
        args: dict[str, Any] | None = None,
        timeout: float = _OP_TIMEOUT_S,
    ) -> dict[str, Any]:
        runner = get_settings().WINDOWS_HOST_RUNNER
        if not runner:
            raise BrokerConnectionError(
                "MT5 runner not configured (WINDOWS_HOST_RUNNER unset); "
                "MT5 is unavailable in Linux container"
            )
        payload = json.dumps(
            {"operation": operation, "credentials": credentials, "args": args or {}}
        ).encode("utf-8")
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                runner,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(payload), timeout=timeout
                )
            except asyncio.TimeoutError as exc:
                proc.kill()
                await proc.wait()
                raise BrokerConnectionError(
                    f"MT5 runner timeout after {timeout}s"
                ) from exc
        except FileNotFoundError as exc:
            raise BrokerConnectionError("MT5 runner binary not found") from exc

        if proc.returncode != 0:
            # Sanitize: never include credentials in error
            raise BrokerConnectionError(
                f"MT5 runner failed (exit {proc.returncode})"
            )
        try:
            result = json.loads(stdout.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerConnectionError("MT5 runner returned invalid JSON") from exc
        if not result.get("ok"):
            err_code = result.get("error_code")
            err_msg = result.get("error_message", "MT5 operation failed")
            if err_code in {"AUTH_FAILED", "10004"}:
                raise BrokerAuthError(err_msg, error_code=err_code)
            raise BrokerError(err_msg, error_code=err_code)
        return result.get("data", {})

    # ---------- Public adapter methods ----------

    async def test_connection(
        self, credentials: dict[str, Any]
    ) -> TestConnectionResult:
        try:
            self._validate(credentials)
        except BrokerValidationError as exc:
            return TestConnectionResult(
                success=False,
                error_code="validation_error",
                error_message=exc.message,
            )
        if get_settings().MT5_TEST_MODE:
            return self._canned_test_result(credentials)
        try:
            data = await self._run_subprocess("test_connection", credentials)
            return TestConnectionResult(
                success=True,
                account_number=data.get("account_number"),
                account_currency=data.get("account_currency"),
                server=data.get("server") or credentials.get("server"),
                balance=data.get("balance"),
                equity=data.get("equity"),
            )
        except BrokerError as exc:
            return TestConnectionResult(
                success=False,
                error_code=exc.error_code or exc.code,
                error_message=exc.message,
            )

    async def get_account_info(self, credentials: dict[str, Any]) -> AccountInfo:
        self._validate(credentials)
        if get_settings().MT5_TEST_MODE:
            return self._canned_account_info(credentials)
        data = await self._run_subprocess(
            "get_account_info", credentials, timeout=_READ_TIMEOUT_S
        )
        return AccountInfo(
            account_number=data["account_number"],
            currency=data["currency"],
            balance=float(data["balance"]),
            equity=float(data["equity"]),
            margin=float(data["margin"]),
            free_margin=float(data["free_margin"]),
            margin_level=(
                float(data["margin_level"]) if data.get("margin_level") is not None else None
            ),
            server=data["server"],
        )

    async def get_positions(self, credentials: dict[str, Any]) -> list[Position]:
        self._validate(credentials)
        if get_settings().MT5_TEST_MODE:
            return self._canned_positions()
        data = await self._run_subprocess(
            "get_positions", credentials, timeout=_READ_TIMEOUT_S
        )
        positions: list[Position] = []
        for p in data.get("positions", []):
            positions.append(
                Position(
                    position_id=str(p["position_id"]),
                    symbol=p["symbol"],
                    side=p["side"],
                    volume=float(p["volume"]),
                    open_price=float(p["open_price"]),
                    current_price=float(p["current_price"]),
                    unrealized_pnl=float(p["unrealized_pnl"]),
                    open_time=datetime.fromtimestamp(
                        float(p["open_time"]), tz=timezone.utc
                    ),
                    sl=p.get("sl"),
                    tp=p.get("tp"),
                )
            )
        return positions

    async def get_tick(self, credentials: dict[str, Any], symbol: str) -> Tick:
        self._validate(credentials)
        if get_settings().MT5_TEST_MODE:
            return self._canned_tick(symbol)
        data = await self._run_subprocess(
            "get_tick", credentials, args={"symbol": symbol}, timeout=_READ_TIMEOUT_S
        )
        return Tick(
            symbol=data["symbol"],
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            timestamp_ms=int(data["timestamp_ms"]),
        )
