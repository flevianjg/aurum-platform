"""Broker exception hierarchy.

All adapter errors must subclass BrokerError so the API layer can map them
uniformly. Error messages must be SANITIZED — no credentials, no echoed
tokens. The adapter is responsible for sanitizing before raising.
"""

from __future__ import annotations


class BrokerError(Exception):
    """Base class for all broker-adapter errors. Always sanitized."""

    code: str = "broker_error"

    def __init__(self, message: str = "broker error", *, error_code: str | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class BrokerAuthError(BrokerError):
    """Authentication / authorization failure (bad creds, revoked token)."""

    code = "broker_auth_failed"


class BrokerNotFoundError(BrokerError):
    """The broker rejected the account_id / login as unknown."""

    code = "broker_not_found"


class BrokerConnectionError(BrokerError):
    """Network failure, timeout, 5xx, terminal init failure."""

    code = "broker_connection_error"


class BrokerValidationError(BrokerError):
    """Credentials dict is missing required fields or has bad types."""

    code = "broker_validation_error"
