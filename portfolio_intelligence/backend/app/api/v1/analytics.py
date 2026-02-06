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


@router.get("/portfolios/{portfolio_id}/metrics/latest")
async def get_latest_metrics(
    portfolio_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Get the latest daily metrics for a portfolio (computed on-the-fly from real price data)."""
    # Verify ownership
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Compute metrics on-the-fly from price data (last 90 days)
    from datetime import timedelta
    engine = PortfolioAnalyticsEngine(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=90)

    metrics = await engine.compute_daily_metrics(portfolio_id, start_date, end_date)

    if not metrics:
        raise HTTPException(status_code=404, detail="No price data available - try refreshing data")

    # Get latest metric
    latest = metrics[-1]

    # Calculate YTD and MTD returns
    ytd_start = date(end_date.year, 1, 1)
    ytd_metrics = [m for m in metrics if m["date"] >= ytd_start]
    return_ytd = None
    if ytd_metrics and ytd_metrics[0]["nav"] and latest["nav"]:
        return_ytd = (latest["nav"] - ytd_metrics[0]["nav"]) / ytd_metrics[0]["nav"]

    # MTD
    mtd_start = date(end_date.year, end_date.month, 1)
    mtd_metrics = [m for m in metrics if m["date"] >= mtd_start]
    return_mtd = None
    if mtd_metrics and mtd_metrics[0]["nav"] and latest["nav"]:
        return_mtd = (latest["nav"] - mtd_metrics[0]["nav"]) / mtd_metrics[0]["nav"]

    return {
        "date": latest["date"],
        "nav": latest["nav"],
        "return_1d": latest["return_1d"],
        "return_mtd": return_mtd,
        "return_ytd": return_ytd,
        "volatility_30d": latest["volatility_30d"],
        "max_drawdown": latest["max_drawdown"],
    }


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
    """Compare performance across multiple portfolios.

    Special handling: If a portfolio ID is not found, it's ignored (allows comparing
    against non-existent benchmarks without errors).
    """
    portfolio_ids = [uuid.UUID(id_str.strip()) for id_str in ids.split(",")]

    # Verify ownership - skip portfolios that don't exist (for benchmark support)
    valid_ids = []
    for pid in portfolio_ids:
        result = await db.execute(
            select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id)
        )
        if result.scalar_one_or_none():
            valid_ids.append(pid)

    if not valid_ids:
        raise HTTPException(status_code=404, detail="No valid portfolios found")

    engine = PortfolioAnalyticsEngine(db)
    return await engine.compare_portfolios(valid_ids, start, end)


@router.get("/portfolios/{portfolio_id}/attribution")
async def get_attribution(
    portfolio_id: uuid.UUID,
    period: str = Query("90d", description="Period: 30d, 90d, ytd, 1y"),
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Get return attribution by position (which holdings drove returns)."""
    from datetime import timedelta

    # Verify ownership
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Parse period
    end_date = date.today()
    if period == "30d":
        start_date = end_date - timedelta(days=30)
    elif period == "90d":
        start_date = end_date - timedelta(days=90)
    elif period == "ytd":
        start_date = date(end_date.year, 1, 1)
    elif period == "1y":
        start_date = end_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=90)

    engine = PortfolioAnalyticsEngine(db)
    contributions = await engine.get_contribution_by_holding(portfolio_id, start_date, end_date)

    # Calculate total return
    total_contribution = sum(c.contribution for c in contributions)

    return {
        "portfolio_id": str(portfolio_id),
        "portfolio_name": portfolio.name,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "total_return": total_contribution,
        "positions": [
            {
                "symbol": c.symbol,
                "weight": c.weight,
                "return": c.return_pct,
                "contribution": c.contribution,
            }
            for c in sorted(contributions, key=lambda x: x.contribution, reverse=True)
        ],
    }


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
