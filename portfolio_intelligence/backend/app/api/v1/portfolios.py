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
    )
    db.add(portfolio)
    await db.flush()

    version = PortfolioVersion(
        portfolio_id=portfolio.id,
        version_number=1,
        note=body.note,
    )
    db.add(version)
    await db.flush()

    for pos in body.positions:
        db.add(PortfolioPosition(
            portfolio_version_id=version.id,
            symbol=pos.symbol,
            allocation_type=pos.allocation_type,
            value=pos.value,
        ))

    await db.commit()

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
            allocation_type=pos.allocation_type,
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
