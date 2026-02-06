import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PortfolioMetricsRead(BaseModel):
    date: date
    nav: Decimal
    return_1d: Decimal | None = None
    return_mtd: Decimal | None = None
    return_ytd: Decimal | None = None
    volatility_30d: Decimal | None = None
    max_drawdown: Decimal | None = None

    model_config = {"from_attributes": True}


class PerformanceSeries(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_name: str
    dates: list[date]
    nav_values: list[Decimal]
    returns: list[Decimal | None]


class HoldingContribution(BaseModel):
    symbol: str
    weight: Decimal
    return_pct: Decimal
    contribution: Decimal


class ComparisonResult(BaseModel):
    portfolios: list[PerformanceSeries]
    start_date: date
    end_date: date
