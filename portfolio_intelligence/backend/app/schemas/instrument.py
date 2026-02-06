import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class InstrumentRead(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    logo_url: str | None = None

    model_config = {"from_attributes": True}


class PriceDailyRead(BaseModel):
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Decimal
    volume: int

    model_config = {"from_attributes": True}
