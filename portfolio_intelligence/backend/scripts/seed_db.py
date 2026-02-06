"""
Database seeding script for Portfolio Intelligence.

Creates realistic test data for:
- Users
- Portfolios (various allocation types)
- Portfolio versions and positions
- Instruments
- Historical price data
- Portfolio metrics

Usage:
    python -m scripts.seed_db

Options:
    --clear    Clear all existing data before seeding
    --days     Number of days of historical data (default: 90)
"""
import asyncio
import sys
import argparse
from datetime import datetime, timedelta, date
from decimal import Decimal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import get_settings
from app.models.user import User
from app.models.portfolio import Portfolio, PortfolioVersion, PortfolioPosition, AllocationType
from app.models.instrument import Instrument
from app.models.price import PriceDaily
from app.models.analytics import PortfolioMetricsDaily
from app.db.database import Base


# Seed data configurations
INSTRUMENTS_DATA = [
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Consumer Electronics"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Internet"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "E-Commerce"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Social Media"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "NYSE", "sector": "ETF", "industry": "Broad Market"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "exchange": "NASDAQ", "sector": "ETF", "industry": "Technology"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "exchange": "NYSE", "sector": "ETF", "industry": "Broad Market"},
]

# Base prices for generating historical data
BASE_PRICES = {
    "AAPL": 185.50,
    "MSFT": 420.30,
    "GOOGL": 145.20,
    "AMZN": 178.90,
    "TSLA": 245.60,
    "NVDA": 875.40,
    "META": 485.20,
    "SPY": 510.75,
    "QQQ": 445.30,
    "VTI": 265.80,
}

USERS_DATA = [
    {"email": "demo@portfoliointel.com", "tradestation_user_id": "TS_DEMO_001"},
    {"email": "investor@example.com", "tradestation_user_id": "TS_DEMO_002"},
    {"email": "trader@example.com", "tradestation_user_id": "TS_DEMO_003"},
]


def generate_price_series(symbol: str, days: int = 90) -> list[dict]:
    """Generate realistic daily OHLCV data for a symbol."""
    import random

    base_price = BASE_PRICES.get(symbol, 100.0)
    volatility = 0.015 if symbol in ["SPY", "VTI", "QQQ"] else 0.025
    trend = 0.0005

    prices = []
    current_price = base_price
    end_date = datetime.now()

    for i in range(days - 1, -1, -1):
        bar_date = end_date - timedelta(days=i)

        # Skip weekends
        if bar_date.weekday() >= 5:
            continue

        # Deterministic random but different per symbol/date
        random.seed(f"{symbol}{bar_date.date()}")

        # Daily return with trend and volatility
        daily_return = random.gauss(trend, volatility)
        current_price *= (1 + daily_return)

        # Generate OHLC
        daily_vol = abs(random.gauss(0, volatility * 0.5))
        high = current_price * (1 + daily_vol)
        low = current_price * (1 - daily_vol)
        open_price = random.uniform(low, high)
        close_price = current_price

        # Generate volume
        base_volume = 50_000_000 if symbol in ["AAPL", "MSFT", "TSLA"] else 10_000_000
        volume = int(base_volume * random.uniform(0.7, 1.3))

        prices.append({
            "date": bar_date.date(),
            "open": Decimal(str(round(open_price, 2))),
            "high": Decimal(str(round(high, 2))),
            "low": Decimal(str(round(low, 2))),
            "close": Decimal(str(round(close_price, 2))),
            "adj_close": Decimal(str(round(close_price, 2))),
            "volume": volume,
            "source": "mock",
        })

    return prices


async def clear_database(session):
    """Clear all data from database."""
    print("🧹 Clearing existing data...")
    await session.execute(delete(PortfolioMetricsDaily))
    await session.execute(delete(PriceDaily))
    await session.execute(delete(PortfolioPosition))
    await session.execute(delete(PortfolioVersion))
    await session.execute(delete(Portfolio))
    await session.execute(delete(Instrument))
    await session.execute(delete(User))
    await session.commit()
    print("✅ Database cleared")


async def seed_users(session) -> dict:
    """Create test users."""
    print("\n👥 Creating users...")
    users = {}
    for user_data in USERS_DATA:
        user = User(**user_data)
        session.add(user)
        users[user_data["email"]] = user
        print(f"   ✓ {user.email}")

    await session.commit()
    return users


async def seed_instruments(session) -> dict:
    """Create instruments."""
    print("\n📈 Creating instruments...")
    instruments = {}
    for inst_data in INSTRUMENTS_DATA:
        inst = Instrument(**inst_data)
        session.add(inst)
        instruments[inst_data["symbol"]] = inst
        print(f"   ✓ {inst.symbol} - {inst.name}")

    await session.commit()
    return instruments


async def seed_prices(session, instruments: dict, days: int = 90):
    """Create historical price data."""
    print(f"\n💰 Generating {days} days of price data...")
    for symbol, instrument in instruments.items():
        price_series = generate_price_series(symbol, days)
        for price_data in price_series:
            price = PriceDaily(
                instrument_id=instrument.id,
                **price_data
            )
            session.add(price)
        print(f"   ✓ {symbol}: {len(price_series)} trading days")

    await session.commit()


async def seed_portfolios(session, users: dict, instruments: dict):
    """Create portfolios with various allocation strategies."""
    print("\n💼 Creating portfolios...")

    demo_user = users["demo@portfoliointel.com"]
    investor_user = users["investor@example.com"]
    trader_user = users["trader@example.com"]

    portfolios_config = [
        {
            "user": demo_user,
            "name": "Tech Growth Portfolio",
            "positions": [
                {"symbol": "AAPL", "allocation_type": AllocationType.weight, "value": 0.25},
                {"symbol": "MSFT", "allocation_type": AllocationType.weight, "value": 0.25},
                {"symbol": "GOOGL", "allocation_type": AllocationType.weight, "value": 0.20},
                {"symbol": "NVDA", "allocation_type": AllocationType.weight, "value": 0.30},
            ],
            "note": "Concentrated tech growth strategy",
        },
        {
            "user": demo_user,
            "name": "Balanced ETF Portfolio",
            "positions": [
                {"symbol": "SPY", "allocation_type": AllocationType.weight, "value": 0.60},
                {"symbol": "QQQ", "allocation_type": AllocationType.weight, "value": 0.30},
                {"symbol": "VTI", "allocation_type": AllocationType.weight, "value": 0.10},
            ],
            "note": "Low-cost diversified approach",
        },
        {
            "user": investor_user,
            "name": "Core Holdings",
            "positions": [
                {"symbol": "AAPL", "allocation_type": AllocationType.quantity, "value": 100},
                {"symbol": "MSFT", "allocation_type": AllocationType.quantity, "value": 50},
                {"symbol": "AMZN", "allocation_type": AllocationType.quantity, "value": 75},
                {"symbol": "META", "allocation_type": AllocationType.quantity, "value": 25},
            ],
            "note": "Long-term buy and hold positions",
        },
        {
            "user": trader_user,
            "name": "High Conviction Plays",
            "positions": [
                {"symbol": "TSLA", "allocation_type": AllocationType.quantity, "value": 200},
                {"symbol": "NVDA", "allocation_type": AllocationType.quantity, "value": 50},
            ],
            "note": "Concentrated bets on high-growth names",
        },
        {
            "user": trader_user,
            "name": "Index Tracker",
            "positions": [
                {"symbol": "SPY", "allocation_type": AllocationType.quantity, "value": 500},
            ],
            "note": "Passive market exposure",
        },
    ]

    for config in portfolios_config:
        # Create portfolio
        portfolio = Portfolio(
            user_id=config["user"].id,
            name=config["name"],
            base_currency="USD",
        )
        session.add(portfolio)
        await session.flush()

        # Create version
        version = PortfolioVersion(
            portfolio_id=portfolio.id,
            version_number=1,
            effective_at=datetime.now() - timedelta(days=30),  # Started 30 days ago
            note=config["note"],
        )
        session.add(version)
        await session.flush()

        # Create positions
        for pos_data in config["positions"]:
            position = PortfolioPosition(
                portfolio_version_id=version.id,
                symbol=pos_data["symbol"],
                allocation_type=pos_data["allocation_type"],
                value=pos_data["value"],
            )
            session.add(position)

        print(f"   ✓ {portfolio.name} ({config['user'].email}) - {len(config['positions'])} positions")

    await session.commit()


async def seed_metrics(session):
    """Generate sample portfolio metrics."""
    print("\n📊 Generating portfolio metrics...")

    # Get all portfolios
    result = await session.execute(select(Portfolio))
    portfolios = result.scalars().all()

    for portfolio in portfolios:
        # Generate last 30 days of metrics
        base_nav = 100000  # Start with $100k
        for i in range(29, -1, -1):
            metric_date = (datetime.now() - timedelta(days=i)).date()

            # Skip weekends
            if datetime.combine(metric_date, datetime.min.time()).weekday() >= 5:
                continue

            # Simulate realistic returns
            import random
            random.seed(f"{portfolio.id}{metric_date}")

            daily_return = random.gauss(0.0005, 0.01)  # 5bps mean, 1% vol
            base_nav *= (1 + daily_return)

            metric = PortfolioMetricsDaily(
                portfolio_id=portfolio.id,
                date=metric_date,
                nav=Decimal(str(round(base_nav, 2))),
                return_1d=Decimal(str(round(daily_return, 6))),
                return_mtd=Decimal(str(round(random.gauss(0.01, 0.03), 6))),
                return_ytd=Decimal(str(round(random.gauss(0.05, 0.10), 6))),
                volatility_30d=Decimal(str(round(random.uniform(0.10, 0.25), 6))),
                max_drawdown=Decimal(str(round(random.uniform(-0.15, -0.05), 6))),
            )
            session.add(metric)

        print(f"   ✓ {portfolio.name}: 30 days of metrics")

    await session.commit()


async def main(clear: bool = False, days: int = 90):
    """Main seeding function."""
    print("\n" + "=" * 60)
    print("  Portfolio Intelligence - Database Seeder")
    print("=" * 60)

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        if clear:
            await clear_database(session)

        users = await seed_users(session)
        instruments = await seed_instruments(session)
        await seed_prices(session, instruments, days)
        await seed_portfolios(session, users, instruments)
        await seed_metrics(session)

    await engine.dispose()

    print("\n" + "=" * 60)
    print("✅ Seeding completed successfully!")
    print("=" * 60)
    print(f"\n📝 Summary:")
    print(f"   Users:        {len(USERS_DATA)}")
    print(f"   Instruments:  {len(INSTRUMENTS_DATA)}")
    print(f"   Price Days:   {days}")
    print(f"   Portfolios:   5 (various allocation types)")
    print(f"\n🔐 Test Credentials:")
    print(f"   demo@portfoliointel.com")
    print(f"   investor@example.com")
    print(f"   trader@example.com")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Portfolio Intelligence database")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before seeding")
    parser.add_argument("--days", type=int, default=90, help="Number of days of historical data")
    args = parser.parse_args()

    asyncio.run(main(clear=args.clear, days=args.days))
