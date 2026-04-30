"""Pydantic schemas for broker endpoints.

* `SecretStr` is used for password / api_token so accidental dumps redact them.
* The wire shape is `{broker_type, credentials: {...}, ...}`. The discriminator
  field `broker_type` is mirrored INTO the credentials dict by a model_validator
  so pydantic can pick the right credentials class via discriminated union.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

BrokerType = Literal["MT5", "OANDA"]


class BrokerCredentialsMT5(BaseModel):
    broker_type: Literal["MT5"] = "MT5"
    account: int
    password: SecretStr
    server: str = Field(min_length=1, max_length=128)


class BrokerCredentialsOANDA(BaseModel):
    broker_type: Literal["OANDA"] = "OANDA"
    account_id: str = Field(min_length=1, max_length=64)
    api_token: SecretStr
    environment: Literal["practice", "live"]


CredentialsUnion = Annotated[
    Union[BrokerCredentialsMT5, BrokerCredentialsOANDA],
    Field(discriminator="broker_type"),
]


class _BrokerRequestBase(BaseModel):
    broker_type: BrokerType
    credentials: CredentialsUnion

    @model_validator(mode="before")
    @classmethod
    def _inject_discriminator(cls, data):
        # The wire format has broker_type at top level; pydantic's discriminator
        # needs the same field inside credentials. Mirror it here.
        if isinstance(data, dict):
            bt = data.get("broker_type")
            creds = data.get("credentials")
            if bt and isinstance(creds, dict) and "broker_type" not in creds:
                creds["broker_type"] = bt
        return data

    @model_validator(mode="after")
    def _check_match(self):
        if self.broker_type != self.credentials.broker_type:
            raise ValueError("broker_type does not match credentials shape")
        return self


class BrokerTestRequest(_BrokerRequestBase):
    pass


class BrokerConnectRequest(_BrokerRequestBase):
    account_label: str = Field(min_length=1, max_length=64)


class BrokerTestResponse(BaseModel):
    success: bool
    account_number: str | None = None
    account_currency: str | None = None
    server: str | None = None
    balance: float | None = None
    equity: float | None = None
    error_code: str | None = None
    error_message: str | None = None


class BrokerAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    broker_type: BrokerType
    account_label: str
    account_number: str | None
    server: str | None
    account_currency: str | None
    is_active: bool
    last_tested_at: datetime | None
    last_test_status: str | None
    created_at: datetime


class LiveAccountInfo(BaseModel):
    account_number: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float | None
    server: str


class BrokerAccountDetailResponse(BrokerAccountResponse):
    last_test_error: str | None = None
    live_account_info: LiveAccountInfo | None = None
