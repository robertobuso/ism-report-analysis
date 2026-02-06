import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.portfolio import Portfolio, PortfolioVersion, PortfolioPosition
from app.schemas.portfolio import (
    PortfolioCreate, PortfolioVersionCreate, PortfolioRead,
    PortfolioSummary, PortfolioVersionRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


async def _ensure_owned(
    portfolio_id: uuid.UUID, user: User, db: AsyncSession
) -> Portfolio:
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.versions).selectinload(PortfolioVersion.positions))
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: PortfolioCreate,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new portfolio with version 1 and positions."""
    portfolio = Portfolio(
        user_id=user.id,
        name=body.name,
        base_currency=body.base_currency,
        allocation_type=body.allocation_type,  # Portfolio-level allocation type
    )
    db.add(portfolio)
    await db.flush()

    # Placeholder effective_at - will be updated after price fetch
    from datetime import datetime
    version = PortfolioVersion(
        portfolio_id=portfolio.id,
        version_number=1,
        note=body.note,
        effective_at=datetime.now(),  # Temporary - updated below
    )
    db.add(version)
    await db.flush()

    # Collect unique symbols
    # All positions inherit allocation_type from portfolio
    symbols = set()
    for pos in body.positions:
        db.add(PortfolioPosition(
            portfolio_version_id=version.id,
            symbol=pos.symbol,
            allocation_type=portfolio.allocation_type,  # Inherited from portfolio
            value=pos.value,
        ))
        symbols.add(pos.symbol.upper())

    await db.commit()

    # Fetch prices for new symbols and set proper effective_at
    if symbols:
        async def fetch_prices_and_set_start_date():
            from app.db.database import AsyncSessionLocal
            from app.services.ingestion import PriceIngestionService
            from app.dependencies import get_tradestation_client
            from app.models.instrument import Instrument
            from app.models.price import PriceDaily
            from sqlalchemy import select, func

            async with AsyncSessionLocal() as price_db:
                ts_client = get_tradestation_client()
                service = PriceIngestionService(price_db, ts_client)

                # Fetch 90 days of prices for each symbol
                for symbol in symbols:
                    try:
                        logger.info(f"Fetching prices for {symbol} (new portfolio symbol)")
                        await service.backfill_symbol("", symbol, bars_back=90)
                    except Exception as e:
                        logger.error(f"Failed to fetch prices for {symbol}: {e}")

                # Find the earliest date where ALL symbols have price data
                # This ensures analytics have complete data from the start
                earliest_dates = []
                for symbol in symbols:
                    result = await price_db.execute(
                        select(func.min(PriceDaily.date))
                        .join(Instrument)
                        .where(Instrument.symbol == symbol)
                    )
                    min_date = result.scalar()
                    if min_date:
                        earliest_dates.append(min_date)

                if earliest_dates:
                    # Use the LATEST of the earliest dates (when ALL symbols have data)
                    portfolio_start_date = max(earliest_dates)

                    # Update version's effective_at to match available data
                    from app.models.portfolio import PortfolioVersion as PV
                    await price_db.execute(
                        select(PV)
                        .where(PV.id == version.id)
                        .with_for_update()
                    )
                    result = await price_db.execute(
                        select(PV).where(PV.id == version.id)
                    )
                    ver = result.scalar_one()
                    ver.effective_at = datetime.combine(portfolio_start_date, datetime.min.time())
                    await price_db.commit()

                    logger.info(f"Set portfolio effective_at to {portfolio_start_date} (earliest date with complete data)")

        background_tasks.add_task(fetch_prices_and_set_start_date)

    # Reload with relationships
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.versions).selectinload(PortfolioVersion.positions))
        .where(Portfolio.id == portfolio.id)
    )
    portfolio = result.scalar_one()

    return PortfolioRead(
        id=portfolio.id,
        name=portfolio.name,
        base_currency=portfolio.base_currency,
        allocation_type=portfolio.allocation_type,
        created_at=portfolio.created_at,
        latest_version=PortfolioVersionRead.model_validate(portfolio.versions[-1]) if portfolio.versions else None,
    )


@router.get("", response_model=list[PortfolioSummary])
async def list_portfolios(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all portfolios for the current user."""
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.versions).selectinload(PortfolioVersion.positions))
        .where(Portfolio.user_id == user.id)
        .order_by(Portfolio.created_at.desc())
    )
    portfolios = result.scalars().all()

    return [
        PortfolioSummary(
            id=p.id,
            name=p.name,
            base_currency=p.base_currency,
            created_at=p.created_at,
            version_count=len(p.versions),
            position_count=len(p.versions[-1].positions) if p.versions else 0,
        )
        for p in portfolios
    ]


@router.get("/{portfolio_id}", response_model=PortfolioRead)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a portfolio with its latest version and positions."""
    portfolio = await _ensure_owned(portfolio_id, user, db)
    latest = portfolio.versions[-1] if portfolio.versions else None

    return PortfolioRead(
        id=portfolio.id,
        name=portfolio.name,
        base_currency=portfolio.base_currency,
        allocation_type=portfolio.allocation_type,
        created_at=portfolio.created_at,
        latest_version=PortfolioVersionRead.model_validate(latest) if latest else None,
    )


@router.post("/{portfolio_id}/versions", response_model=PortfolioVersionRead, status_code=status.HTTP_201_CREATED)
async def create_version(
    portfolio_id: uuid.UUID,
    body: PortfolioVersionCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new version of a portfolio."""
    portfolio = await _ensure_owned(portfolio_id, user, db)

    next_version_number = (
        max(v.version_number for v in portfolio.versions) + 1
        if portfolio.versions else 1
    )

    version = PortfolioVersion(
        portfolio_id=portfolio.id,
        version_number=next_version_number,
        note=body.note,
    )
    if body.effective_at:
        version.effective_at = body.effective_at

    db.add(version)
    await db.flush()

    for pos in body.positions:
        db.add(PortfolioPosition(
            portfolio_version_id=version.id,
            symbol=pos.symbol,
            allocation_type=portfolio.allocation_type,  # Inherited from portfolio
            value=pos.value,
        ))

    await db.commit()
    await db.refresh(version, attribute_names=["positions"])

    return PortfolioVersionRead.model_validate(version)


@router.get("/{portfolio_id}/versions", response_model=list[PortfolioVersionRead])
async def list_versions(
    portfolio_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all versions of a portfolio."""
    portfolio = await _ensure_owned(portfolio_id, user, db)
    return [PortfolioVersionRead.model_validate(v) for v in portfolio.versions]


@router.get("/{portfolio_id}/versions/{version_id}", response_model=PortfolioVersionRead)
async def get_version(
    portfolio_id: uuid.UUID,
    version_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a specific version snapshot."""
    portfolio = await _ensure_owned(portfolio_id, user, db)

    for v in portfolio.versions:
        if v.id == version_id:
            return PortfolioVersionRead.model_validate(v)

    raise HTTPException(status_code=404, detail="Version not found")


@router.get("/{portfolio_id}/holdings")
async def get_holdings_with_values(
    portfolio_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get portfolio holdings with current values, weights, and P&L."""
    from decimal import Decimal
    from app.models.price import PriceDaily
    from app.models.instrument import Instrument
    from datetime import date

    portfolio = await _ensure_owned(portfolio_id, user, db)
    if not portfolio.versions:
        return {"holdings": [], "total_value": 0}

    latest_version = portfolio.versions[-1]
    holdings = []
    total_value = Decimal("0")

    for position in latest_version.positions:
        # Get latest price
        result = await db.execute(
            select(Instrument).where(Instrument.symbol == position.symbol)
        )
        instrument = result.scalar_one_or_none()

        if not instrument:
            continue

        result = await db.execute(
            select(PriceDaily.adj_close)
            .where(PriceDaily.instrument_id == instrument.id)
            .order_by(PriceDaily.date.desc())
            .limit(1)
        )
        price_row = result.first()

        if not price_row:
            continue

        current_price = Decimal(str(price_row[0]))
        quantity = Decimal(str(position.value))
        market_value = quantity * current_price
        total_value += market_value

        holdings.append({
            "symbol": position.symbol,
            "quantity": quantity,
            "current_price": current_price,
            "market_value": market_value,
        })

    # Add weights
    for holding in holdings:
        holding["weight"] = holding["market_value"] / total_value if total_value > 0 else 0
        holding["weight_pct"] = float(holding["weight"] * 100)

    return {
        "portfolio_id": str(portfolio_id),
        "portfolio_name": portfolio.name,
        "total_value": total_value,
        "holdings": sorted(holdings, key=lambda x: x["market_value"], reverse=True),
    }


@router.post("/{portfolio_id}/refresh-prices", status_code=status.HTTP_202_ACCEPTED)
async def refresh_portfolio_prices(
    portfolio_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Manually trigger price refresh for all symbols in the portfolio."""
    portfolio = await _ensure_owned(portfolio_id, user, db)

    if not portfolio.versions:
        raise HTTPException(status_code=400, detail="Portfolio has no versions")

    # Get unique symbols from latest version
    latest_version = portfolio.versions[-1]
    symbols = {pos.symbol.upper() for pos in latest_version.positions}

    if not symbols:
        raise HTTPException(status_code=400, detail="Portfolio has no positions")

    # Calculate how many days to fetch based on portfolio start date
    from datetime import date
    portfolio_start = latest_version.effective_at.date() if hasattr(latest_version.effective_at, 'date') else latest_version.effective_at
    days_since_start = (date.today() - portfolio_start).days + 1  # +1 to include today

    # Trigger background price fetch
    async def fetch_latest_prices():
        from app.db.database import AsyncSessionLocal
        from app.services.ingestion import PriceIngestionService
        from app.dependencies import get_tradestation_client

        async with AsyncSessionLocal() as price_db:
            ts_client = get_tradestation_client()
            service = PriceIngestionService(price_db, ts_client)

            logger.info(f"Fetching {days_since_start} days of data (from {portfolio_start} to today)")

            for symbol in symbols:
                try:
                    logger.info(f"Refreshing prices for {symbol} (manual refresh)")
                    # Fetch from portfolio start to today (dynamic, not hardcoded)
                    await service.backfill_symbol("", symbol, bars_back=days_since_start)
                except Exception as e:
                    logger.error(f"Failed to refresh prices for {symbol}: {e}")

    background_tasks.add_task(fetch_latest_prices)

    return {
        "status": "accepted",
        "message": f"Refreshing prices for {len(symbols)} symbols",
        "symbols": list(symbols),
    }


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a portfolio and all its versions."""
    portfolio = await _ensure_owned(portfolio_id, user, db)
    await db.delete(portfolio)
    await db.commit()
