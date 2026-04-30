"""broker_type → BrokerAdapter resolver."""

from __future__ import annotations

from .base import BrokerAdapter
from .mt5_adapter import MT5Adapter
from .oanda_adapter import OandaAdapter

_REGISTRY: dict[str, type[BrokerAdapter]] = {
    "MT5": MT5Adapter,
    "OANDA": OandaAdapter,
}


def get_adapter(broker_type: str) -> BrokerAdapter:
    cls = _REGISTRY.get(broker_type)
    if cls is None:
        raise ValueError(f"Unknown broker_type: {broker_type}")
    return cls()
