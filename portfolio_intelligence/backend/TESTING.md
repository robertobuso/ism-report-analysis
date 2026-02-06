# Portfolio Intelligence - Testing with Mock Data

This guide explains how to test the Portfolio Intelligence app using mock data while waiting for TradeStation API approval.

## Overview

The mock infrastructure allows you to:
- ✅ Test all UI/UX features and user journeys
- ✅ Develop and test the Next.js frontend
- ✅ Validate portfolio analytics calculations
- ✅ Demo the app to stakeholders
- ✅ Easily switch to real TradeStation API when ready

## Architecture

The mock system uses **dependency injection** to swap between mock and real TradeStation clients:

```
┌─────────────────────────────────┐
│   get_tradestation_client()     │  Factory function
│   (in dependencies.py)           │
└───────────┬─────────────────────┘
            │
            ├─── USE_MOCK_TRADESTATION=true
            │    └─> MockTradeStationClient
            │
            └─── USE_MOCK_TRADESTATION=false
                 └─> TradeStationClient (real API)
```

**Migration path:** Change one environment variable, zero code changes needed.

## Quick Start

### 1. Enable Mock Mode

Edit `.env`:
```bash
USE_MOCK_TRADESTATION=true
```

### 2. Set Up Database

Make sure PostgreSQL is running:
```bash
# Start PostgreSQL (if using Homebrew)
brew services start postgresql@14

# Create database
createdb portfolio_intelligence
```

### 3. Run Migrations

```bash
cd portfolio_intelligence/backend
source .venv/bin/activate  # or activate your venv

# Run Alembic migrations
alembic upgrade head
```

### 4. Seed Test Data

```bash
# Seed database with mock data (clears existing data)
python -m scripts.seed_db --clear --days 90

# Output:
# ============================================================
#   Portfolio Intelligence - Database Seeder
# ============================================================
#
# 👥 Creating users...
#    ✓ demo@portfoliointel.com
#    ✓ investor@example.com
#    ✓ trader@example.com
#
# 📈 Creating instruments...
#    ✓ AAPL - Apple Inc.
#    ✓ MSFT - Microsoft Corporation
#    ... (10 instruments total)
#
# 💰 Generating 90 days of price data...
#    ✓ AAPL: 64 trading days
#    ✓ MSFT: 64 trading days
#    ...
#
# 💼 Creating portfolios...
#    ✓ Tech Growth Portfolio (demo@portfoliointel.com)
#    ✓ Balanced ETF Portfolio (demo@portfoliointel.com)
#    ✓ Core Holdings (investor@example.com)
#    ✓ High Conviction Plays (trader@example.com)
#    ✓ Index Tracker (trader@example.com)
#
# 📊 Generating portfolio metrics...
#    ✓ Tech Growth Portfolio: 30 days of metrics
#    ...
#
# ✅ Seeding completed successfully!
```

**Seed script options:**
- `--clear`: Clear existing data before seeding (recommended for fresh start)
- `--days N`: Number of days of historical price data (default: 90)

### 5. Start Backend

```bash
uvicorn app.main:app --reload --port 8000

# You should see:
# INFO: Portfolio Intelligence API starting up...
# INFO: Using MOCK TradeStation client  <-- Confirms mock mode
```

### 6. Test the API

```bash
# Health check
curl http://localhost:8000/health

# Get instruments
curl http://localhost:8000/api/v1/instruments

# Mock OAuth flow (simplified for testing)
curl http://localhost:8000/api/v1/auth/login
# Returns mock auth URL
```

## Test Data Created

The seed script creates:

### Users (3)
| Email | TradeStation ID | Description |
|-------|----------------|-------------|
| `demo@portfoliointel.com` | `TS_DEMO_001` | Demo account with 2 portfolios |
| `investor@example.com` | `TS_DEMO_002` | Long-term investor |
| `trader@example.com` | `TS_DEMO_003` | Active trader with 2 portfolios |

### Instruments (10)
- **Tech Stocks:** AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META
- **ETFs:** SPY, QQQ, VTI

### Portfolios (5)

1. **Tech Growth Portfolio** (demo user)
   - Weight-based allocation
   - AAPL: 25%, MSFT: 25%, GOOGL: 20%, NVDA: 30%

2. **Balanced ETF Portfolio** (demo user)
   - Weight-based allocation
   - SPY: 60%, QQQ: 30%, VTI: 10%

3. **Core Holdings** (investor user)
   - Quantity-based allocation
   - AAPL: 100 shares, MSFT: 50 shares, AMZN: 75 shares, META: 25 shares

4. **High Conviction Plays** (trader user)
   - Quantity-based allocation
   - TSLA: 200 shares, NVDA: 50 shares

5. **Index Tracker** (trader user)
   - Quantity-based allocation
   - SPY: 500 shares

### Price Data
- 90 days of realistic OHLCV data (excludes weekends)
- Realistic volatility and trends
- Deterministic (same seed produces same data)

### Portfolio Metrics
- 30 days of daily metrics per portfolio
- NAV, returns (1D, MTD, YTD), volatility, max drawdown

## Mock Features

### What Works in Mock Mode

✅ **OAuth Flow** (simulated)
- `GET /api/v1/auth/login` → Returns mock auth URL
- `GET /api/v1/auth/callback?code=test` → Creates mock user session
- Tokens are fake but structurally valid

✅ **Market Data**
- `get_daily_bars()` → Returns realistic OHLCV data
- Prices generated algorithmically with realistic volatility
- Deterministic but varies by symbol/date

✅ **User Profile**
- Returns mock TradeStation account data

✅ **All Database Operations**
- Portfolios, positions, instruments, prices, metrics
- All CRUD operations work normally

### What's Mocked

- ❌ Real TradeStation authentication (returns fake tokens)
- ❌ Real market data (uses generated data)
- ❌ Real account/position data (returns mocks)

### Mock vs. Real Behavior

| Feature | Mock Mode | Real Mode |
|---------|-----------|-----------|
| OAuth | Fake flow, instant success | Real TradeStation OAuth |
| Market Data | Generated algorithmically | Live from TradeStation API |
| Rate Limits | None | TradeStation API limits apply |
| Symbols | Only seeded instruments | Any valid symbol |
| Historical Data | 90 days (configurable) | Up to 5 years |

## Switching to Real TradeStation API

When you receive TradeStation credentials:

### 1. Update Environment

Edit `.env`:
```bash
# Disable mock mode
USE_MOCK_TRADESTATION=false

# Add real credentials
TRADESTATION_CLIENT_ID=your_real_client_id
TRADESTATION_CLIENT_SECRET=your_real_client_secret
TRADESTATION_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback

# Use production or simulation URL
TRADESTATION_BASE_URL=https://sim-api.tradestation.com/v3  # for testing
# TRADESTATION_BASE_URL=https://api.tradestation.com/v3   # for production
```

### 2. Restart Backend

```bash
uvicorn app.main:app --reload --port 8000

# You should see:
# INFO: Using REAL TradeStation client  <-- Confirms real mode
```

### 3. Test Real OAuth

Navigate to:
```
http://localhost:8000/api/v1/auth/login
```

You'll be redirected to real TradeStation login.

**That's it!** No code changes needed.

## Development Workflow

### Testing New Features

1. **Develop with mock data**
   ```bash
   USE_MOCK_TRADESTATION=true
   python -m scripts.seed_db --clear
   uvicorn app.main:app --reload
   ```

2. **Test UI/UX flows**
   - Create portfolios
   - View analytics
   - Test error handling

3. **Verify calculations**
   - Check portfolio metrics
   - Validate returns, volatility, drawdowns

4. **Switch to real API** (when ready)
   ```bash
   USE_MOCK_TRADESTATION=false
   ```

### Re-seeding Data

To start fresh:
```bash
# Clear and reseed with default 90 days
python -m scripts.seed_db --clear

# Seed with different time period
python -m scripts.seed_db --clear --days 180
```

### Adding Custom Test Data

Edit `scripts/seed_db.py` to add:
- More users
- Different portfolio allocations
- Additional instruments
- Custom price scenarios

## Customizing Mock Behavior

### Add New Symbols

Edit `mock_tradestation.py`:
```python
MOCK_PRICE_DATA = {
    "AAPL": {...},
    # Add your symbol
    "BRK.B": {
        "base_price": 450.00,
        "volatility": 0.010,
        "trend": 0.0003,
    },
}
```

Then reseed:
```python
# In scripts/seed_db.py
INSTRUMENTS_DATA = [
    # ... existing instruments ...
    {"symbol": "BRK.B", "name": "Berkshire Hathaway Inc.", ...},
]
```

### Adjust Price Volatility

In `mock_tradestation.py`, modify volatility per symbol or globally:
```python
"AAPL": {
    "base_price": 185.50,
    "volatility": 0.025,  # Increase for more volatile data
    "trend": 0.001,
}
```

## Troubleshooting

### "Module not found" Error
```bash
# Make sure you're in the backend directory
cd portfolio_intelligence/backend
python -m scripts.seed_db --clear
```

### Database Connection Error
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Verify DATABASE_URL in .env
DATABASE_URL=postgresql+asyncpg://user@localhost:5432/portfolio_intelligence
```

### No Data Showing in Frontend
```bash
# Check if seeding completed successfully
python -m scripts.seed_db --clear

# Verify backend is running
curl http://localhost:8000/api/v1/instruments
```

### Mock Client Not Being Used
```bash
# Check .env file
cat .env | grep USE_MOCK

# Should show:
# USE_MOCK_TRADESTATION=true

# Restart backend after changing .env
```

## Next Steps

1. ✅ **Enable mock mode** and seed database
2. ✅ **Start backend** and verify logs show "Using MOCK"
3. ✅ **Test API endpoints** with curl or frontend
4. ✅ **Develop UI/UX** with realistic data
5. ⏳ **Wait for TradeStation approval**
6. ✅ **Flip to real API** with one env var change

## Questions?

The mock infrastructure is designed to be a drop-in replacement for the real TradeStation API. If you encounter any issues or need additional mock functionality, the code is well-documented in:

- `app/services/mock_tradestation.py` - Mock client implementation
- `app/dependencies.py` - Factory function for client selection
- `scripts/seed_db.py` - Database seeding logic
