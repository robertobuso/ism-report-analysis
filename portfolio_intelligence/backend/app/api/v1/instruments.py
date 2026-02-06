import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.instrument import Instrument
from app.models.price import PriceDaily
from app.schemas.instrument import InstrumentRead, PriceDailyRead

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("/search", response_model=list[InstrumentRead])
async def search_instruments(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search instruments by symbol or name."""
    pattern = f"%{q.upper()}%"
    result = await db.execute(
        select(Instrument)
        .where(
            Instrument.symbol.ilike(pattern)
            | Instrument.name.ilike(pattern)
        )
        .order_by(Instrument.symbol)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{symbol}", response_model=InstrumentRead)
async def get_instrument(
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get instrument metadata by symbol."""
    result = await db.execute(
        select(Instrument).where(Instrument.symbol == symbol.upper())
    )
    instrument = result.scalar_one_or_none()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument


@router.get("/{symbol}/prices", response_model=list[PriceDailyRead])
async def get_prices(
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily price history for an instrument."""
    result = await db.execute(
        select(Instrument).where(Instrument.symbol == symbol.upper())
    )
    instrument = result.scalar_one_or_none()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    query = (
        select(PriceDaily)
        .where(PriceDaily.instrument_id == instrument.id)
        .order_by(PriceDaily.date)
    )
    if start:
        query = query.where(PriceDaily.date >= start)
    if end:
        query = query.where(PriceDaily.date <= end)

    result = await db.execute(query)
    return result.scalars().all()
