# Mock TradeStation Setup - Summary

## What Was Created

### 1. **MockTradeStationClient** (`app/services/mock_tradestation.py`)
   - Drop-in replacement for real TradeStation API
   - Generates realistic OHLCV data for 10 common symbols
   - Simulates OAuth flow
   - Same interface as `TradeStationClient` for seamless swapping

### 2. **Factory Function** (`app/dependencies.py`)
   - `get_tradestation_client()` returns mock or real client based on env var
   - All API endpoints updated to use factory
   - Zero code changes needed to switch modes

### 3. **Database Seed Script** (`scripts/seed_db.py`)
   - Creates 3 test users
   - 10 instruments (AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META, SPY, QQQ, VTI)
   - 5 portfolios with different allocation strategies
   - 90 days of realistic price data (configurable)
   - 30 days of portfolio metrics
   - Usage: `python -m scripts.seed_db --clear --days 90`

### 4. **Configuration** (`.env`)
   - New env var: `USE_MOCK_TRADESTATION=true`
   - Toggle between mock and real API instantly

### 5. **Documentation** (`TESTING.md`)
   - Complete testing guide
   - Step-by-step setup instructions
   - Migration path to real API

## Files Modified

```
portfolio_intelligence/backend/
├── app/
│   ├── config.py                    # Added use_mock_tradestation setting
│   ├── dependencies.py              # Added get_tradestation_client() factory
│   ├── main.py                      # Updated to use factory
│   ├── api/v1/auth.py              # Updated to use factory
│   ├── services/
│   │   ├── tradestation.py         # Removed singleton export
│   │   ├── mock_tradestation.py    # NEW: Mock implementation
│   │   └── ingestion.py            # Updated to accept client parameter
│   └── ...
├── scripts/
│   ├── __init__.py                 # NEW
│   └── seed_db.py                  # NEW: Database seeder
├── .env                            # Added USE_MOCK_TRADESTATION
├── .env.example                    # Added USE_MOCK_TRADESTATION
├── TESTING.md                      # NEW: Testing guide
└── MOCK_SETUP_SUMMARY.md          # THIS FILE
```

## Quick Start (5 Minutes)

```bash
# 1. Navigate to backend
cd portfolio_intelligence/backend

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Ensure PostgreSQL is running
brew services start postgresql@14

# 4. Create database (if needed)
createdb portfolio_intelligence

# 5. Run migrations
alembic upgrade head

# 6. Seed test data
python -m scripts.seed_db --clear --days 90

# 7. Start backend (mock mode enabled by default)
uvicorn app.main:app --reload --port 8000

# ✅ You should see: "Using MOCK TradeStation client"
```

## Test the Setup

```bash
# Health check
curl http://localhost:8000/health

# Get instruments (should return 10)
curl http://localhost:8000/api/v1/instruments | jq

# Mock OAuth login
curl http://localhost:8000/api/v1/auth/login
```

## Migration to Real API (When Ready)

```bash
# 1. Edit .env
USE_MOCK_TRADESTATION=false
TRADESTATION_CLIENT_ID=your_real_client_id
TRADESTATION_CLIENT_SECRET=your_real_client_secret

# 2. Restart backend
uvicorn app.main:app --reload --port 8000

# ✅ You should see: "Using REAL TradeStation client"
```

**That's it!** No code changes needed.

## What You Can Test Now

### ✅ Full Feature Testing
- Create portfolios (weight-based or quantity-based)
- Add/edit positions
- View analytics and metrics
- Test all API endpoints
- Develop Next.js frontend

### ✅ UI/UX Development
- 5 pre-seeded portfolios with different strategies
- 90 days of realistic price history
- 30 days of portfolio metrics (NAV, returns, volatility)
- Test user journeys end-to-end

### ✅ Analytics Validation
- Portfolio returns calculations
- Risk metrics (volatility, drawdown)
- Position performance
- Attribution analysis

## Key Benefits

1. **No TradeStation Credentials Needed** - Start testing immediately
2. **Realistic Data** - Algorithmic price generation with proper volatility
3. **Deterministic** - Same seed produces same data for reproducibility
4. **Scalable** - Easy to add more symbols, users, portfolios
5. **Production-Ready** - Flip one env var to switch to real API
6. **Zero Technical Debt** - Mock code is isolated, doesn't pollute production code

## Architecture Highlights

### Dependency Injection Pattern
```python
# Factory function (dependencies.py)
def get_tradestation_client():
    if settings.use_mock_tradestation:
        return MockTradeStationClient()  # Mock
    return TradeStationClient()          # Real

# Usage in endpoints
@router.get("/login")
async def login():
    client = get_tradestation_client()  # Auto-selects based on env
    auth_url = client.build_auth_url(state)
    return RedirectResponse(url=auth_url)
```

### Interface Compatibility
Both clients implement identical methods:
- `build_auth_url(state) -> str`
- `exchange_code(code) -> dict`
- `refresh_access_token(token) -> dict`
- `get_user_profile(token) -> dict`
- `get_daily_bars(token, symbol, bars_back) -> list[dict]`
- `parse_bars(bars) -> list[dict]`
- `cache_access_token(user_id, token, expires_in) -> None`
- `get_cached_token(user_id) -> str | None`
- `close() -> None`

## Troubleshooting

### Issue: Import errors
**Solution:** Run from backend directory:
```bash
cd portfolio_intelligence/backend
python -m scripts.seed_db --clear
```

### Issue: Database errors
**Solution:** Check PostgreSQL is running and DATABASE_URL is correct:
```bash
brew services list | grep postgresql
echo $DATABASE_URL
```

### Issue: Mock not being used
**Solution:** Verify .env setting and restart backend:
```bash
grep USE_MOCK .env
# Should show: USE_MOCK_TRADESTATION=true
```

## Next Steps

1. ✅ Run the quick start commands above
2. ✅ Test API endpoints with curl or Postman
3. ✅ Connect Next.js frontend to backend
4. ✅ Test all user journeys
5. ✅ Demo to stakeholders
6. ⏳ Wait for TradeStation approval
7. ✅ Switch to real API with one line change

---

**Full documentation:** See `TESTING.md` for complete testing guide.
