"""Broker adapter unit tests with httpx mocking for OANDA and TEST_MODE for MT5."""

from __future__ import annotations

import json

import httpx
import pytest

from app.brokers.exceptions import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerError,
    BrokerNotFoundError,
    BrokerValidationError,
)
from app.brokers.factory import get_adapter
from app.brokers.mt5_adapter import MT5Adapter
from app.brokers.oanda_adapter import OandaAdapter


# ---------------- Factory ----------------


def test_factory_returns_correct_class() -> None:
    assert isinstance(get_adapter("OANDA"), OandaAdapter)
    assert isinstance(get_adapter("MT5"), MT5Adapter)


def test_factory_raises_on_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown broker_type"):
        get_adapter("XYZ")


# ---------------- MT5 (TEST_MODE) ----------------


async def test_mt5_test_mode_returns_canned_success() -> None:
    adapter = MT5Adapter()
    result = await adapter.test_connection(
        {"account": 1234, "password": "pw", "server": "S"}
    )
    assert result.success is True
    assert result.account_number == "1234"
    assert result.account_currency == "USD"


async def test_mt5_validates_required_fields() -> None:
    adapter = MT5Adapter()
    result = await adapter.test_connection({"account": 1, "password": "pw"})  # missing server
    assert result.success is False
    assert result.error_code == "validation_error"
    assert "server" in (result.error_message or "")


async def test_mt5_validates_account_is_integer() -> None:
    adapter = MT5Adapter()
    result = await adapter.test_connection(
        {"account": "not-an-int", "password": "pw", "server": "S"}
    )
    assert result.success is False
    assert result.error_code == "validation_error"


def test_mt5_required_credential_fields() -> None:
    assert MT5Adapter.required_credential_fields() == ["account", "password", "server"]


# ---------------- OANDA (mocked httpx) ----------------


def _oanda_creds() -> dict:
    return {
        "account_id": "001-001-1234567-001",
        "api_token": "secret-token-do-not-leak",
        "environment": "practice",
    }


def _mock_transport(handler):
    """Wrap a request handler in an httpx MockTransport injected via monkeypatch."""
    return httpx.MockTransport(handler)


@pytest.fixture
def patch_httpx_client(monkeypatch):
    def _apply(handler):
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = _mock_transport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
    return _apply


async def test_oanda_test_connection_success(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/summary")
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(
            200,
            json={
                "account": {
                    "id": "001-001-1234567-001",
                    "currency": "USD",
                    "balance": "1000.00",
                    "NAV": "1010.50",
                }
            },
        )

    patch_httpx_client(handler)
    result = await OandaAdapter().test_connection(_oanda_creds())
    assert result.success is True
    assert result.account_currency == "USD"
    assert result.balance == 1000.00
    assert result.equity == 1010.50


async def test_oanda_test_connection_401(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errorMessage": "Unauthorized"})

    patch_httpx_client(handler)
    result = await OandaAdapter().test_connection(_oanda_creds())
    assert result.success is False
    assert result.error_code == "401"
    assert "rejected" in (result.error_message or "").lower()


async def test_oanda_test_connection_404(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errorMessage": "no such account"})

    patch_httpx_client(handler)
    result = await OandaAdapter().test_connection(_oanda_creds())
    assert result.success is False
    assert result.error_code == "404"


async def test_oanda_test_connection_5xx_is_connection_error(
    patch_httpx_client,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    patch_httpx_client(handler)
    result = await OandaAdapter().test_connection(_oanda_creds())
    assert result.success is False
    assert result.error_code == "503"


async def test_oanda_test_connection_timeout(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout")

    patch_httpx_client(handler)
    result = await OandaAdapter().test_connection(_oanda_creds())
    assert result.success is False
    assert result.error_code == "connection_error"


async def test_oanda_strips_token_from_error_body(patch_httpx_client) -> None:
    """OANDA echoes the token in some error bodies — adapter must scrub it."""
    creds = _oanda_creds()
    token = creds["api_token"]

    def handler(request: httpx.Request) -> httpx.Response:
        # 418 to hit the generic branch where body is included in the message
        return httpx.Response(
            418,
            json={"errorMessage": f"oops, your token {token} is bad"},
        )

    patch_httpx_client(handler)
    result = await OandaAdapter().test_connection(creds)
    assert result.success is False
    # The plaintext token MUST NOT appear in the sanitized error message
    assert token not in (result.error_message or "")


async def test_oanda_get_account_info_happy_path(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "account": {
                    "id": "X",
                    "currency": "USD",
                    "balance": "5000",
                    "NAV": "5100",
                    "marginUsed": "100",
                    "marginAvailable": "4900",
                }
            },
        )

    patch_httpx_client(handler)
    info = await OandaAdapter().get_account_info(_oanda_creds())
    assert info.balance == 5000.0
    assert info.equity == 5100.0
    assert info.margin == 100.0
    assert info.free_margin == 4900.0
    assert info.margin_level is not None and info.margin_level > 0


async def test_oanda_get_positions_maps_long_and_short(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "positions": [
                    {
                        "instrument": "EUR_USD",
                        "long": {
                            "units": "1000",
                            "averagePrice": "1.10",
                            "unrealizedPL": "5.0",
                        },
                        "short": {"units": "0"},
                    },
                    {
                        "instrument": "USD_JPY",
                        "long": {"units": "0"},
                        "short": {
                            "units": "-500",
                            "averagePrice": "150.0",
                            "unrealizedPL": "-2.0",
                        },
                    },
                ]
            },
        )

    patch_httpx_client(handler)
    positions = await OandaAdapter().get_positions(_oanda_creds())
    assert len(positions) == 2
    sides = {p.symbol: p.side for p in positions}
    assert sides["EUR_USD"] == "BUY"
    assert sides["USD_JPY"] == "SELL"


async def test_oanda_get_tick_parses_bid_ask(patch_httpx_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "prices": [
                    {
                        "bids": [{"price": "1.1000"}],
                        "asks": [{"price": "1.1003"}],
                        "time": "1714435200.000000000",
                    }
                ]
            },
        )

    patch_httpx_client(handler)
    tick = await OandaAdapter().get_tick(_oanda_creds(), "EUR_USD")
    assert tick.bid == 1.1
    assert tick.ask == 1.1003
    assert tick.timestamp_ms == 1714435200000


async def test_oanda_validation_error_on_missing_field() -> None:
    result = await OandaAdapter().test_connection(
        {"account_id": "x", "environment": "practice"}  # missing api_token
    )
    assert result.success is False
    assert result.error_code == "validation_error"


async def test_oanda_validation_error_on_bad_environment() -> None:
    result = await OandaAdapter().test_connection(
        {"account_id": "x", "api_token": "y", "environment": "wrong"}
    )
    assert result.success is False
    assert result.error_code == "validation_error"
