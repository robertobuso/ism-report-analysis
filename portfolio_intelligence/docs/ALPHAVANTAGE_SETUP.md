# AlphaVantage Integration Setup Guide

## Overview

The Portfolio Intelligence backend now supports **three market data providers**:
1. **TradeStation** (default) - Real brokerage API
2. **AlphaVantage** - Market data provider (supports paid tier features)
3. **Mock** - Synthetic data for testing

You can switch between providers using environment variables, with no code changes required.

---

## AlphaVantage Provider

### What AlphaVantage Provides

✅ **What it CAN do:**
- Daily OHLCV price data (20+ years of history)
- Real-time quotes
- Intraday bars (1min, 5min, 15min, 30min, 60min)
- Adjusted close prices (for splits/dividends)
- High API rate limits on paid tier

❌ **What it CANNOT do:**
- Sync account positions (it's not a brokerage API)
- Provide portfolio holdings automatically
- Execute trades

### Recommended Use Cases

**Option 1: Hybrid Approach (Best for real accounts)**
- Use **TradeStation** for position sync (import your real holdings)
- Use **AlphaVantage** for market data (price updates, analytics)
- Benefit: Real positions + reliable market data

**Option 2: Manual Positions + AlphaVantage (Best for testing/simulation)**
- Manually create portfolios and add positions
- Use **AlphaVantage** for all market data
- Benefit: No brokerage integration needed

---

## Configuration

### 1. Get Your AlphaVantage API Key

1. Sign up at: https://www.alphavantage.co/
2. Get your API key from your dashboard
3. Note your tier limits:
   - **Free tier**: 25 requests/day, 5 requests/minute
   - **Paid tier**: Higher limits based on your plan

### 2. Update Environment Variables

Edit `portfolio_intelligence/backend/.env`:

```bash
# Market Data Provider
MARKET_DATA_PROVIDER=alphavantage  # Options: "tradestation", "alphavantage", "mock"

# AlphaVantage API Key
ALPHAVANTAGE_API_KEY=your_api_key_here

# TradeStation (still needed for OAuth if using hybrid approach)
TRADESTATION_CLIENT_ID=your_client_id
TRADESTATION_CLIENT_SECRET=your_secret
# ... other TradeStation settings
```

### 3. Restart the Backend

```bash
cd portfolio_intelligence/backend
source venv/bin/activate  # if using virtualenv
uvicorn app.main:app --reload
```

---

## Usage Examples

### Example 1: Pure AlphaVantage Mode

**.env configuration:**
```bash
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=DEMO  # Replace with your real key
USE_MOCK_TRADESTATION=false
```

**Workflow:**
1. Login via TradeStation OAuth (or mock mode)
2. Manually create portfolio
3. Add positions with symbols and quantities
4. AlphaVantage provides all price data
5. Analytics engine calculates performance metrics

### Example 2: Hybrid Mode (TradeStation + AlphaVantage)

**.env configuration:**
```bash
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_key_here
# TradeStation OAuth credentials for position sync
TRADESTATION_CLIENT_ID=your_client_id
TRADESTATION_CLIENT_SECRET=your_secret
```

**Workflow:**
1. Login via TradeStation OAuth
2. Sync positions from TradeStation account
3. AlphaVantage provides market data for analytics
4. Best of both worlds: real positions + reliable data

---

## API Compatibility

The `AlphaVantageAdapter` implements the same interface as `TradeStationClient`, so switching providers requires **zero code changes**.

### Interface Methods

```python
class AlphaVantageAdapter:
    async def get_daily_bars(
        self,
        access_token: str,  # Ignored (AlphaVantage uses API key)
        symbol: str,
        bars_back: int = 30,
        unit: str = "Daily",  # Ignored (always daily)
    ) -> list[dict[str, Any]]:
        """Get daily OHLCV bars - TradeStation-compatible interface"""

    @staticmethod
    def parse_bars(bars: list[dict]) -> list[dict]:
        """Parse bars - TradeStation-compatible interface"""
```

### Response Format

AlphaVantage returns data in the **same format** as TradeStation:

```python
[
    {
        "TimeStamp": "2024-01-15T00:00:00Z",
        "Open": 185.50,
        "High": 187.20,
        "Low": 184.80,
        "Close": 186.75,
        "AdjustedClose": 186.75,  # Includes split/dividend adjustments
        "Volume": 52000000
    },
    # ... more bars
]
```

---

## Rate Limits

### AlphaVantage API Limits

**Free Tier:**
- 25 requests/day
- 5 requests/minute
- Best for: Testing, small portfolios (< 5 symbols)

**Paid Tier:**
- Higher limits based on your plan
- Best for: Production use, large portfolios

### Handling Rate Limits

The client automatically handles common errors:

```python
# Rate limit response
{
    "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute..."
}
```

When rate limited:
- Client logs a warning
- Returns empty array (graceful degradation)
- Cached data is used if available

**Recommendation:** For production, use paid tier or implement caching/batching.

---

## Testing

### Test AlphaVantage Connection

```python
# In your backend shell or script
from app.services.alphavantage import AlphaVantageClient

async def test_connection():
    client = AlphaVantageClient(api_key="your_key_here")

    # Test daily bars
    bars = await client.get_daily_bars("AAPL", outputsize="compact")
    print(f"Fetched {len(bars)} bars for AAPL")

    # Test quote
    quote = await client.get_quote("MSFT")
    print(f"MSFT current price: ${quote['price']}")

    await client.close()
```

### Expected Output

```
Fetched 100 bars for AAPL
MSFT current price: $420.30
```

---

## Troubleshooting

### Issue: "No data returned"

**Cause:** Invalid API key or rate limit exceeded

**Solution:**
1. Verify your API key in `.env`
2. Check AlphaVantage dashboard for usage
3. Wait if rate limited (free tier: 1 minute)

### Issue: "Symbol not found"

**Cause:** Invalid ticker symbol

**Solution:**
1. Verify symbol is correct (e.g., "AAPL" not "Apple")
2. Check symbol exists on US exchanges
3. AlphaVantage primarily covers US equities

### Issue: "Old data only"

**Cause:** Free tier data has 15-minute delay

**Solution:**
- Upgrade to paid tier for real-time data
- Or use end-of-day data for analytics (sufficient for most use cases)

---

## Production Recommendations

### For Live Trading/Real Accounts

1. **Use TradeStation for positions** - Automatic sync of real holdings
2. **Use AlphaVantage for market data** - Reliable, fast, well-documented
3. **Set `MARKET_DATA_PROVIDER=alphavantage`** - Uses your paid tier
4. **Implement caching** - Redis cache to reduce API calls
5. **Monitor usage** - Track API call counts to avoid overage charges

### For Paper Trading/Simulation

1. **Manual positions** - Create portfolios in UI
2. **Use AlphaVantage for everything** - No brokerage needed
3. **Daily rebalance jobs** - Celery tasks for analytics
4. **Set `MARKET_DATA_PROVIDER=alphavantage`**

---

## Cost Considerations

### AlphaVantage Pricing (as of 2024)

- **Free**: $0/month - 25 calls/day
- **Basic**: ~$50/month - 120 calls/minute
- **Premium**: ~$250/month - Higher limits + support
- **Enterprise**: Custom pricing

**Recommendation:** Start with free tier for testing, upgrade to Basic for production (typically sufficient for 20-50 symbol portfolios with daily updates).

---

## Migration Path

### From Mock → AlphaVantage

```bash
# 1. Update .env
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_key

# 2. Keep existing portfolios
# No data migration needed - positions stay the same

# 3. Restart backend
# Analytics will now use AlphaVantage for price data
```

### From TradeStation → AlphaVantage (Hybrid)

```bash
# 1. Keep TradeStation OAuth for position sync
TRADESTATION_CLIENT_ID=...
TRADESTATION_CLIENT_SECRET=...

# 2. Switch market data provider
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_key

# 3. Positions sync from TradeStation
# 4. Prices fetch from AlphaVantage
# Best of both!
```

---

## Summary

| Feature | TradeStation | AlphaVantage | Mock |
|---------|-------------|--------------|------|
| **Position Sync** | ✅ Real account | ❌ Manual only | ✅ Simulated |
| **Market Data** | ✅ Real-time | ✅ Real-time (paid) | ✅ Synthetic |
| **Historical Data** | ✅ Limited | ✅ 20+ years | ✅ 90 days |
| **Rate Limits** | API-dependent | 5-120/min | Unlimited |
| **Cost** | Brokerage account | $0-$250/mo | Free |
| **Best For** | Real trading | Analytics/testing | Development |

**Recommended Setup for Production:**
- Positions: TradeStation (real account sync)
- Market Data: AlphaVantage (reliable, fast, well-documented)
- Analytics: Portfolio Intelligence backend (our custom engine)

This gives you the best of all worlds! 🚀
