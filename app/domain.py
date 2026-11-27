"""Input contracts and deterministic request fingerprints."""
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    loan_ref: Annotated[str, Field(pattern=r'^SYN-[A-Z0-9-]{4,40}$')]
    amount_cents: Annotated[int, Field(gt=0, le=100_000_000)]
    currency: Literal['USD']
    effective_date: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$')]

    @field_validator('effective_date')
    @classmethod
    def calendar_date(cls, value: str) -> str:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Use YYYY-MM-DD')
        return value


class EntryResponse(BaseModel):
    entry_id: str
    loan_ref: str
    amount_cents: int
    currency: str
    effective_date: str
    state: Literal['RECORDED']
    version: int
    created_at: str
    idempotency_replayed: bool = False
    reversal_of: str | None = None
    reversal_reason: str | None = None


class ErrorResponse(BaseModel):
    error: str
    request_id: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def request_digest(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


class ReversalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    reversal_reason: Literal['DUPLICATE', 'INCORRECT_AMOUNT', 'INCORRECT_DATE', 'OPERATIONAL_ERROR']
    effective_date: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$')]

    @field_validator('effective_date')
    @classmethod
    def calendar_date(cls, value: str) -> str:
        return EntryRequest.calendar_date(value)
