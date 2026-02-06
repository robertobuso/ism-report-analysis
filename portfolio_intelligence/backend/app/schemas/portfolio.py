import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.portfolio import AllocationType


class PositionCreate(BaseModel):
    symbol: str
    value: Decimal  # Either shares (quantity) or weight (0.0-1.0)

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.upper().strip()


class PortfolioCreate(BaseModel):
    name: str
    base_currency: str = "USD"
    allocation_type: AllocationType = AllocationType.quantity  # Portfolio-level setting
    positions: list[PositionCreate]
    note: str | None = None


class PortfolioVersionCreate(BaseModel):
    positions: list[PositionCreate]
    note: str | None = None
    effective_at: datetime | None = None
    # allocation_type inherited from portfolio, not changeable per version


class PositionRead(BaseModel):
    id: uuid.UUID
    symbol: str
    allocation_type: AllocationType
    value: Decimal

    model_config = {"from_attributes": True}


class PortfolioVersionRead(BaseModel):
    id: uuid.UUID
    version_number: int
    effective_at: datetime
    note: str | None = None
    positions: list[PositionRead] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class PortfolioRead(BaseModel):
    id: uuid.UUID
    name: str
    base_currency: str
    allocation_type: AllocationType
    created_at: datetime
    latest_version: PortfolioVersionRead | None = None

    model_config = {"from_attributes": True}


class PortfolioSummary(BaseModel):
    id: uuid.UUID
    name: str
    base_currency: str
    created_at: datetime
    version_count: int = 0
    position_count: int = 0

    model_config = {"from_attributes": True}
