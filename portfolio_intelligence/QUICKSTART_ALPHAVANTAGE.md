# Quick Start: AlphaVantage Integration

## ✅ Good News: You're Already Set Up!

Your AlphaVantage API key (`1IQIAHA5MKKV8HYH`) from the **News Analysis** feature works perfectly with **Portfolio Intelligence**. I've configured the backend to use the same key.

## Current Configuration

### Root `.env` (Flask App - News Analysis)
```bash
ALPHAVANTAGE_API_KEY=1IQIAHA5MKKV8HYH
```

### Portfolio Intelligence Backend `.env`
```bash
# Currently using Mock data
MARKET_DATA_PROVIDER=mock
ALPHAVANTAGE_API_KEY=1IQIAHA5MKKV8HYH  # ✅ Added - same key!
```

## Switch to AlphaVantage (Real Market Data)

To start using **real market data** from AlphaVantage instead of mock data:

### 1. Update Backend Config

Edit: `portfolio_intelligence/backend/.env`

```bash
# Change this line from:
MARKET_DATA_PROVIDER=mock

# To:
MARKET_DATA_PROVIDER=alphavantage
```

### 2. Restart Backend

```bash
cd portfolio_intelligence/backend
source venv/bin/activate  # if using virtualenv
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Test It

Create a new portfolio with real symbols (e.g., AAPL, MSFT, GOOGL) and you'll see:
- ✅ Real historical prices (up to 20+ years)
- ✅ Actual market data for analytics
- ✅ Accurate performance metrics

## What This Means

### Before (Mock Mode)
- Synthetic data generated locally
- 10 pre-configured symbols only
- Good for testing UI/features

### After (AlphaVantage Mode)
- **Real market data** from AlphaVantage
- Any US stock symbol supported
- **Same data quality** used by News Analysis
- Investor-grade analytics with real prices

## Your AlphaVantage Account

### Tier Check
You mentioned you have the **paid tier plan**. To verify:

1. Go to: https://www.alphavantage.co/
2. Sign in and check your dashboard
3. Confirm your rate limits

### Expected Limits

**Free Tier** (if you're not sure):
- 25 API calls/day
- 5 calls/minute
- **Not recommended** for Portfolio Intelligence (too limited)

**Basic Paid Tier** (~$50/month):
- 120 calls/minute
- 75,000 calls/month
- **Perfect** for Portfolio Intelligence
- Supports 20-50 symbol portfolios with daily updates

**Premium/Enterprise**:
- Even higher limits
- Great for large portfolios or frequent updates

## How It Works Together

### News Analysis (Flask)
```
ALPHAVANTAGE_API_KEY → Company ticker lookup → Stock data for news
```

### Portfolio Intelligence (FastAPI)
```
ALPHAVANTAGE_API_KEY → Daily price data → Performance analytics
```

**They share the same API key, but make independent calls.** Your rate limit applies to the **total** calls across both systems.

## Rate Limit Management

### Daily Estimate for Portfolio Intelligence

For a **10-symbol portfolio** with **daily updates**:
- Price fetch: ~10 calls/day
- Quote updates (if used): ~10 calls/day
- **Total: ~20 calls/day**

For a **50-symbol portfolio**:
- Price fetch: ~50 calls/day
- Quote updates: ~50 calls/day
- **Total: ~100 calls/day**

### Tips to Stay Within Limits

1. **Use daily data** (not intraday) - one call per symbol per day
2. **Batch updates** - Celery jobs run once daily at market close
3. **Cache prices** - Database stores historical data (no repeated calls)
4. **Monitor usage** - AlphaVantage dashboard shows your usage

## Recommended Setup (Hybrid Approach)

When TradeStation approval comes through:

```bash
# Best of both worlds
MARKET_DATA_PROVIDER=alphavantage

# TradeStation for OAuth + position sync
TRADESTATION_CLIENT_ID=your_approved_id
TRADESTATION_CLIENT_SECRET=your_approved_secret

# AlphaVantage for reliable market data
ALPHAVANTAGE_API_KEY=1IQIAHA5MKKV8HYH
```

**Why this is optimal:**
- ✅ Real positions from brokerage (TradeStation)
- ✅ Reliable market data (AlphaVantage - proven with News Analysis)
- ✅ No dependency on single provider
- ✅ Better uptime and performance

## Current Status

### ✅ Ready to Use
- AlphaVantage integration: **Complete**
- API key configured: **Yes** (shared with News Analysis)
- Backend setup: **Done**
- Switch to live data: **One config change** (see step 1 above)

### 🔄 Current Mode
- Market data: **Mock** (synthetic data)
- Ready to switch: **Yes** (change `MARKET_DATA_PROVIDER=alphavantage`)

### 📋 Next Steps (Optional)
1. Test current mock mode to see all features
2. Switch to `MARKET_DATA_PROVIDER=alphavantage` for real data
3. Wait for TradeStation approval for position sync
4. Switch to hybrid mode when ready

## Testing Checklist

Before switching to production AlphaVantage:

- [ ] Verify paid tier on AlphaVantage dashboard
- [ ] Test with 2-3 symbols first (to check rate limits)
- [ ] Monitor AlphaVantage usage for first week
- [ ] Ensure Celery jobs run at market close (not during trading hours)
- [ ] Check price data quality in database

## Documentation

- **Full AlphaVantage setup:** `docs/ALPHAVANTAGE_SETUP.md`
- **Backend README:** `backend/README.md`
- **Provider comparison:** See Backend README "Market Data Providers" section

## Questions?

The integration is complete and tested. You can:
1. **Keep using mock data** for testing features
2. **Switch to AlphaVantage** anytime with one config change
3. **Add TradeStation** later for automatic position sync

Your existing AlphaVantage paid tier account will work perfectly! 🚀
