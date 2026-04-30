"""OANDA v20 REST adapter.

Pure async over httpx. Credentials shape:
    {"account_id": "...", "api_token": "...", "environment": "practice"|"live"}

All errors sanitized (no echoed token in error_message).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings

from .base import AccountInfo, BrokerAdapter, Position, TestConnectionResult, Tick
from .exceptions import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerError,
    BrokerNotFoundError,
    BrokerValidationError,
)

logger = logging.getLogger(__name__)

_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def _sanitize(text: str | None, token: str) -> str:
    """Strip the token (and obvious lookalikes) from any echoed string."""
    if not text:
        return ""
    cleaned = text.replace(token, "[REDACTED_TOKEN]")
    if len(token) >= 8:
        # also redact the first 8 chars in case of partial echo
        cleaned = cleaned.replace(token[:8], "[REDACTED_TOKEN]")
    return cleaned[:500]  # cap length to keep error messages bounded


class OandaAdapter(BrokerAdapter):
    @classmethod
    def required_credential_fields(cls) -> list[str]:
        return ["account_id", "api_token", "environment"]

    @staticmethod
    def _validate(credentials: dict[str, Any]) -> tuple[str, str, str, str]:
        for field in OandaAdapter.required_credential_fields():
            if field not in credentials:
                raise BrokerValidationError(f"missing credential field: {field}")
        env = credentials["environment"]
        if env not in _BASE_URLS:
            raise BrokerValidationError("environment must be 'practice' or 'live'")
        return (
            str(credentials["account_id"]),
            str(credentials["api_token"]),
            env,
            _BASE_URLS[env],
        )

    @staticmethod
    def _client(token: str, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=get_settings().OANDA_API_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept-Datetime-Format": "UNIX",
                "Content-Type": "application/json",
            },
        )

    @staticmethod
    def _raise_for_status(resp: httpx.Response, token: str) -> None:
        if 200 <= resp.status_code < 300:
            return
        body_text = ""
        try:
            body_text = resp.text
        except Exception:  # noqa: BLE001
            body_text = ""
        sanitized = _sanitize(body_text, token)
        if resp.status_code in (401, 403):
            raise BrokerAuthError(
                "OANDA rejected credentials",
                error_code=str(resp.status_code),
            )
        if resp.status_code == 404:
            raise BrokerNotFoundError(
                "OANDA account not found",
                error_code="404",
            )
        if 500 <= resp.status_code < 600:
            raise BrokerConnectionError(
                f"OANDA server error ({resp.status_code})",
                error_code=str(resp.status_code),
            )
        raise BrokerError(
            f"OANDA returned {resp.status_code}: {sanitized}",
            error_code=str(resp.status_code),
        )

    async def test_connection(
        self, credentials: dict[str, Any]
    ) -> TestConnectionResult:
        try:
            account_id, token, env, base_url = self._validate(credentials)
        except BrokerValidationError as exc:
            return TestConnectionResult(
                success=False,
                error_code="validation_error",
                error_message=exc.message,
            )

        try:
            async with self._client(token, base_url) as client:
                # /summary returns balance/currency/server too; use it for richer test result
                resp = await client.get(f"/v3/accounts/{account_id}/summary")
                self._raise_for_status(resp, token)
                data = resp.json().get("account", {})
                return TestConnectionResult(
                    success=True,
                    account_number=data.get("id") or account_id,
                    account_currency=data.get("currency"),
                    server=base_url.replace("https://", ""),
                    balance=float(data["balance"]) if "balance" in data else None,
                    equity=float(data["NAV"]) if "NAV" in data else None,
                )
        except BrokerError as exc:
            return TestConnectionResult(
                success=False,
                error_code=exc.error_code or exc.code,
                error_message=exc.message,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            return TestConnectionResult(
                success=False,
                error_code="connection_error",
                error_message=f"network error: {type(exc).__name__}",
            )

    async def get_account_info(self, credentials: dict[str, Any]) -> AccountInfo:
        account_id, token, env, base_url = self._validate(credentials)
        try:
            async with self._client(token, base_url) as client:
                resp = await client.get(f"/v3/accounts/{account_id}/summary")
                self._raise_for_status(resp, token)
                data = resp.json()["account"]
                margin_used = float(data.get("marginUsed", 0))
                margin_avail = float(data.get("marginAvailable", 0))
                nav = float(data.get("NAV", 0))
                return AccountInfo(
                    account_number=data.get("id", account_id),
                    currency=data["currency"],
                    balance=float(data["balance"]),
                    equity=nav,
                    margin=margin_used,
                    free_margin=margin_avail,
                    margin_level=(
                        (nav / margin_used * 100.0) if margin_used > 0 else None
                    ),
                    server=base_url.replace("https://", ""),
                )
        except BrokerError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise BrokerConnectionError(
                f"network error: {type(exc).__name__}"
            ) from exc

    async def get_positions(self, credentials: dict[str, Any]) -> list[Position]:
        account_id, token, env, base_url = self._validate(credentials)
        try:
            async with self._client(token, base_url) as client:
                resp = await client.get(f"/v3/accounts/{account_id}/openPositions")
                self._raise_for_status(resp, token)
                positions: list[Position] = []
                for p in resp.json().get("positions", []):
                    instrument = p["instrument"]
                    long_units = float(p.get("long", {}).get("units", 0) or 0)
                    short_units = float(p.get("short", {}).get("units", 0) or 0)
                    if long_units != 0:
                        side = "BUY"
                        units = long_units
                        avg_price = float(p["long"].get("averagePrice", 0))
                        upl = float(p["long"].get("unrealizedPL", 0))
                    elif short_units != 0:
                        side = "SELL"
                        units = abs(short_units)
                        avg_price = float(p["short"].get("averagePrice", 0))
                        upl = float(p["short"].get("unrealizedPL", 0))
                    else:
                        continue
                    positions.append(
                        Position(
                            position_id=f"{account_id}:{instrument}",
                            symbol=instrument,
                            side=side,
                            volume=units,
                            open_price=avg_price,
                            current_price=avg_price,  # OANDA doesn't expose mark in this endpoint
                            unrealized_pnl=upl,
                            open_time=datetime.now(timezone.utc),
                        )
                    )
                return positions
        except BrokerError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise BrokerConnectionError(
                f"network error: {type(exc).__name__}"
            ) from exc

    async def get_tick(self, credentials: dict[str, Any], symbol: str) -> Tick:
        account_id, token, env, base_url = self._validate(credentials)
        try:
            async with self._client(token, base_url) as client:
                resp = await client.get(
                    f"/v3/accounts/{account_id}/pricing",
                    params={"instruments": symbol},
                )
                self._raise_for_status(resp, token)
                prices = resp.json().get("prices", [])
                if not prices:
                    raise BrokerNotFoundError(f"no price for symbol {symbol}")
                p = prices[0]
                bid = float(p["bids"][0]["price"])
                ask = float(p["asks"][0]["price"])
                # time format depends on Accept-Datetime-Format: UNIX → "1234567890.123456789"
                ts_str = p.get("time", "0")
                try:
                    ts_ms = int(float(ts_str) * 1000)
                except ValueError:
                    ts_ms = 0
                return Tick(symbol=symbol, bid=bid, ask=ask, timestamp_ms=ts_ms)
        except BrokerError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise BrokerConnectionError(
                f"network error: {type(exc).__name__}"
            ) from exc
