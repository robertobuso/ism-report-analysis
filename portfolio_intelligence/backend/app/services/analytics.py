import uuid
import math
import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.portfolio import (
    Portfolio, PortfolioVersion, PortfolioPosition, AllocationType
)
from app.models.price import PriceDaily
from app.models.instrument import Instrument
from app.schemas.analytics import (
    PerformanceSeries, HoldingContribution, ComparisonResult
)
from app.services.portfolio import PortfolioService

logger = logging.getLogger(__name__)

SQRT_252 = Decimal(str(math.sqrt(252)))


class PortfolioAnalyticsEngine:
    """Computes portfolio analytics from daily close prices.

    Key assumptions (from TDD 7.1):
    - version.effective_at → next market open (new version applies following trading day)
    - All analytics are daily-close based only
    - Dividends implicitly included via adjusted close prices
    - Weekends and market holidays excluded from return calculations
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.portfolio_service = PortfolioService(db)

    async def _get_prices(
        self, symbol: str, start: date, end: date
    ) -> list[tuple[date, Decimal]]:
        """Get adjusted close prices for a symbol in date range."""
        result = await self.db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        if not instrument:
            return []

        result = await self.db.execute(
            select(PriceDaily.date, PriceDaily.adj_close)
            .where(
                PriceDaily.instrument_id == instrument.id,
                PriceDaily.date >= start,
                PriceDaily.date <= end,
            )
            .order_by(PriceDaily.date)
        )
        return [(row[0], Decimal(str(row[1]))) for row in result.all()]

    async def compute_daily_metrics(
        self, portfolio_id: uuid.UUID, start: date | None = None, end: date | None = None
    ) -> list[dict]:
        """Compute daily NAV and metrics for a portfolio.

        Weight mode: NAV₀=100, NAVₙ = NAVₙ₋₁ × (1 + Σ(wᵢ × rᵢ))
        Quantity mode: NAV = Σ(qᵢ × closeᵢ)
        """
        if end is None:
            end = date.today()
        if start is None:
            start = end - timedelta(days=365)

        # Get all versions for this portfolio
        result = await self.db.execute(
            select(PortfolioVersion)
            .options(selectinload(PortfolioVersion.positions))
            .where(PortfolioVersion.portfolio_id == portfolio_id)
            .order_by(PortfolioVersion.effective_at)
        )
        versions = result.scalars().all()
        if not versions:
            return []

        # Collect all symbols across versions
        all_symbols = set()
        for v in versions:
            for p in v.positions:
                all_symbols.add(p.symbol)

        # Load all prices
        price_data: dict[str, dict[date, Decimal]] = {}
        for symbol in all_symbols:
            prices = await self._get_prices(symbol, start, end)
            price_data[symbol] = {d: p for d, p in prices}

        # Get all trading dates (union of all dates with prices)
        all_dates = set()
        for symbol_prices in price_data.values():
            all_dates.update(symbol_prices.keys())
        trading_dates = sorted(d for d in all_dates if start <= d <= end)

        if not trading_dates:
            return []

        # Compute daily NAV
        allocation_type = versions[0].positions[0].allocation_type if versions[0].positions else AllocationType.weight
        nav_series = []
        prev_nav = Decimal("100")
        peak_nav = Decimal("100")
        daily_returns = []

        for i, current_date in enumerate(trading_dates):
            # Find effective version for this date
            effective_version = None
            for v in versions:
                if v.effective_at.date() <= current_date:
                    effective_version = v
                else:
                    break

            if not effective_version:
                continue

            if allocation_type == AllocationType.quantity:
                # Quantity mode: NAV = Σ(qᵢ × closeᵢ)
                nav = Decimal("0")
                for pos in effective_version.positions:
                    price = price_data.get(pos.symbol, {}).get(current_date)
                    if price:
                        nav += Decimal(str(pos.value)) * price
            else:
                # Weight mode: NAV₀=100, NAVₙ = NAVₙ₋₁ × (1 + Σ(wᵢ × rᵢ))
                if i == 0:
                    nav = Decimal("100")
                else:
                    prev_date = trading_dates[i - 1]
                    portfolio_return = Decimal("0")
                    for pos in effective_version.positions:
                        prev_price = price_data.get(pos.symbol, {}).get(prev_date)
                        curr_price = price_data.get(pos.symbol, {}).get(current_date)
                        if prev_price and curr_price and prev_price != 0:
                            stock_return = (curr_price - prev_price) / prev_price
                            portfolio_return += Decimal(str(pos.value)) * stock_return
                    nav = prev_nav * (1 + portfolio_return)

            # Compute return
            return_1d = None
            if i > 0 and prev_nav != 0:
                return_1d = (nav - prev_nav) / prev_nav
                daily_returns.append(float(return_1d))

            # Drawdown
            if nav > peak_nav:
                peak_nav = nav
            max_drawdown = (peak_nav - nav) / peak_nav if peak_nav > 0 else Decimal("0")

            # Volatility (30-day rolling)
            vol_30d = None
            if len(daily_returns) >= 30:
                recent = daily_returns[-30:]
                mean = sum(recent) / len(recent)
                variance = sum((r - mean) ** 2 for r in recent) / (len(recent) - 1)
                vol_30d = Decimal(str(math.sqrt(variance))) * SQRT_252

            nav_series.append({
                "date": current_date,
                "nav": nav,
                "return_1d": return_1d,
                "volatility_30d": vol_30d,
                "max_drawdown": max_drawdown,
            })

            prev_nav = nav

        return nav_series

    async def get_performance_series(
        self, portfolio_id: uuid.UUID, start: date | None = None, end: date | None = None
    ) -> PerformanceSeries:
        """Get daily NAV series for charting."""
        metrics = await self.compute_daily_metrics(portfolio_id, start, end)
        return PerformanceSeries(
            portfolio_id=portfolio_id,
            portfolio_name="",  # Caller fills this in
            dates=[m["date"] for m in metrics],
            nav_values=[m["nav"] for m in metrics],
            returns=[m["return_1d"] for m in metrics],
        )

    async def get_contribution_by_holding(
        self, portfolio_id: uuid.UUID, start: date, end: date
    ) -> list[HoldingContribution]:
        """Compute per-holding return contribution over a period."""
        version = await self.portfolio_service.get_version_at_date(portfolio_id, end)
        if not version:
            return []

        contributions = []
        for pos in version.positions:
            prices = await self._get_prices(pos.symbol, start, end)
            if len(prices) >= 2:
                first_price = prices[0][1]
                last_price = prices[-1][1]
                holding_return = (last_price - first_price) / first_price if first_price else Decimal("0")
                weight = Decimal(str(pos.value))
                contributions.append(HoldingContribution(
                    symbol=pos.symbol,
                    weight=weight,
                    return_pct=holding_return,
                    contribution=weight * holding_return,
                ))

        return contributions

    async def compare_portfolios(
        self, portfolio_ids: list[uuid.UUID], start: date | None = None, end: date | None = None
    ) -> ComparisonResult:
        """Compare performance across multiple portfolios."""
        series_list = []
        actual_start = end or date.today()
        actual_end = start or date.today() - timedelta(days=365)

        for pid in portfolio_ids:
            series = await self.get_performance_series(pid, start, end)

            # Get portfolio name
            result = await self.db.execute(
                select(Portfolio.name).where(Portfolio.id == pid)
            )
            name = result.scalar_one_or_none() or "Unknown"
            series.portfolio_name = name
            series_list.append(series)

            if series.dates:
                actual_start = min(actual_start, series.dates[0])
                actual_end = max(actual_end, series.dates[-1])

        return ComparisonResult(
            portfolios=series_list,
            start_date=actual_start,
            end_date=actual_end,
        )
