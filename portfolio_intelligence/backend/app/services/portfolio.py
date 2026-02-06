import uuid
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.portfolio import (
    Portfolio, PortfolioVersion, PortfolioPosition, AllocationType
)

logger = logging.getLogger(__name__)


class PortfolioService:
    """Business logic for portfolio operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolio_with_latest_version(
        self, portfolio_id: uuid.UUID, user_id: uuid.UUID
    ) -> Portfolio | None:
        result = await self.db.execute(
            select(Portfolio)
            .options(
                selectinload(Portfolio.versions)
                .selectinload(PortfolioVersion.positions)
            )
            .where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_version_at_date(
        self, portfolio_id: uuid.UUID, target_date
    ) -> PortfolioVersion | None:
        """Get the effective version for a given date.

        version.effective_at is interpreted as next market open,
        so we find the latest version where effective_at <= target_date.
        """
        result = await self.db.execute(
            select(PortfolioVersion)
            .options(selectinload(PortfolioVersion.positions))
            .where(
                PortfolioVersion.portfolio_id == portfolio_id,
                PortfolioVersion.effective_at <= target_date,
            )
            .order_by(PortfolioVersion.effective_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def validate_weights(positions: list, allocation_type: AllocationType) -> str | None:
        """Validate positions. Returns warning string or None."""
        if allocation_type == AllocationType.weight:
            total = sum(Decimal(str(p.value)) for p in positions)
            if abs(total - Decimal("1.0")) > Decimal("0.001"):
                return f"Weights sum to {total:.4f}, expected 1.0"
        return None
