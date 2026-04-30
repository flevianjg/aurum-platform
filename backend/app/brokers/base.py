"""BrokerAdapter abstract base class + result dataclasses.

All adapters must:
* be safe to call concurrently (each call is a fresh connection in Phase 2)
* never log credential values
* sanitize error messages — no echoed tokens / passwords
* implement required_credential_fields() so callers can validate input shape
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TestConnectionResult:
    success: bool
    account_number: str | None = None
    account_currency: str | None = None
    server: str | None = None
    balance: float | None = None
    equity: float | None = None
    error_code: str | None = None
    error_message: str | None = None  # sanitized


@dataclass(frozen=True)
class AccountInfo:
    account_number: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float | None
    server: str


@dataclass(frozen=True)
class Position:
    position_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    volume: float
    open_price: float
    current_price: float
    unrealized_pnl: float
    open_time: datetime
    sl: float | None = None
    tp: float | None = None


@dataclass(frozen=True)
class Tick:
    symbol: str
    bid: float
    ask: float
    timestamp_ms: int


class BrokerAdapter(ABC):
    """Abstract broker adapter. One instance per process is fine — all I/O
    parameters come in on each call so adapters can be cheaply shared."""

    @classmethod
    @abstractmethod
    def required_credential_fields(cls) -> list[str]:
        """Required keys in the credentials dict (for validation)."""

    @abstractmethod
    async def test_connection(self, credentials: dict[str, Any]) -> TestConnectionResult:
        """Verify credentials work. Never raises — encodes failure in the
        result. Sanitized error_message only."""

    @abstractmethod
    async def get_account_info(self, credentials: dict[str, Any]) -> AccountInfo:
        """Fetch live balance/equity/margin. Raises BrokerError on failure."""

    @abstractmethod
    async def get_positions(self, credentials: dict[str, Any]) -> list[Position]:
        """Fetch open positions. Raises BrokerError on failure."""

    @abstractmethod
    async def get_tick(self, credentials: dict[str, Any], symbol: str) -> Tick:
        """Fetch latest bid/ask for a symbol. Raises BrokerError on failure."""
