import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.portfolio import Portfolio
from app.models.analytics import PortfolioMetricsDaily
from app.schemas.analytics import PortfolioMetricsRead, PerformanceSeries, ComparisonResult
from app.services.analytics import PortfolioAnalyticsEngine

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/portfolios/{portfolio_id}/performance", response_model=PerformanceSeries)
async def get_performance(
    portfolio_id: uuid.UUID,
    start: date | None = None,
    end: date | None = None,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Get portfolio performance time series."""
    # Verify ownership
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    engine = PortfolioAnalyticsEngine(db)
    series = await engine.get_performance_series(portfolio_id, start, end)
    series.portfolio_name = portfolio.name
    return series


@router.get("/portfolios/compare", response_model=ComparisonResult)
async def compare_portfolios(
    ids: str = Query(..., description="Comma-separated portfolio UUIDs"),
    start: date | None = None,
    end: date | None = None,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Compare performance across multiple portfolios."""
    portfolio_ids = [uuid.UUID(id_str.strip()) for id_str in ids.split(",")]

    # Verify ownership of all portfolios
    for pid in portfolio_ids:
        result = await db.execute(
            select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Portfolio {pid} not found")

    engine = PortfolioAnalyticsEngine(db)
    return await engine.compare_portfolios(portfolio_ids, start, end)


@router.get("/portfolios/{portfolio_id}/diff")
async def portfolio_diff(
    portfolio_id: uuid.UUID,
    from_version: int = Query(..., alias="from"),
    to_version: int = Query(..., alias="to"),
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Compare two versions of a portfolio — position changes and performance diff."""
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # TODO: Implement version diff logic
    return {"portfolio_id": str(portfolio_id), "from": from_version, "to": to_version, "diff": "not yet implemented"}
