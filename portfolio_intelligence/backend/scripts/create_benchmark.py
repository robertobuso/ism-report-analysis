#!/usr/bin/env python
"""Create SPY benchmark and generate metrics."""
import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import get_settings
from app.models.portfolio import Portfolio
from app.models.analytics import PortfolioMetricsDaily


async def generate_spy_metrics():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Portfolio).where(Portfolio.name == 'SPY Benchmark')
        )
        portfolio = result.scalar_one_or_none()

        if not portfolio:
            print('❌ SPY Benchmark not found')
            return

        base_nav = 100000
        metrics_count = 0

        # Generate 90 days of SPY metrics (lower volatility than individual stocks)
        for i in range(89, -1, -1):
            metric_date = (datetime.now() - timedelta(days=i)).date()

            # Skip weekends
            if datetime.combine(metric_date, datetime.min.time()).weekday() >= 5:
                continue

            import random
            random.seed(f'SPY{metric_date}')

            # SPY: ~12% annual return, ~15% vol
            daily_return = random.gauss(0.0004, 0.008)  # Lower vol than individual stocks
            base_nav *= (1 + daily_return)

            days_from_start = 90 - i
            ytd_return = 0.123 * (days_from_start / 90)  # ~12.3% over 90 days

            metric = PortfolioMetricsDaily(
                portfolio_id=portfolio.id,
                date=metric_date,
                nav=Decimal(str(round(base_nav, 2))),
                return_1d=Decimal(str(round(daily_return, 6))),
                return_mtd=Decimal(str(round(random.gauss(0.008, 0.015), 6))),
                return_ytd=Decimal(str(round(ytd_return, 6))),
                volatility_30d=Decimal('0.150000'),  # ~15% vol for SPY
                max_drawdown=Decimal(str(round(random.uniform(-0.08, -0.03), 6))),
            )
            session.add(metric)
            metrics_count += 1

        await session.commit()
        print(f'✅ Generated {metrics_count} days of metrics for SPY Benchmark')
        print(f'   Final NAV: ${base_nav:,.2f}')
        print(f'   90d Return: {((base_nav / 100000) - 1) * 100:.2f}%')

    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(generate_spy_metrics())
