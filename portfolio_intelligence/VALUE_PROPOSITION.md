# Portfolio Intelligence - What It Does & Why It Matters

## The Problem It Solves

**Scenario:** You have positions spread across TradeStation (or manually entered). You want to:
- 📊 Track performance over time (not just current values)
- 📉 Understand risk (volatility, drawdowns)
- 🎯 Identify what's working (attribution)
- 📈 Compare different strategies
- 🔄 See impact of rebalancing

**Without Portfolio Intelligence:** You'd need to:
- Manually track positions daily
- Export data to Excel
- Calculate returns, volatility, Sharpe ratio manually
- Build charts yourself
- No historical comparison

**With Portfolio Intelligence:** Automatic, real-time portfolio analytics.

---

## What You Created vs. What You Should See

### What You Created ✅
A portfolio named "RBG Test 1" with:
- AAPL: 100 shares
- META: 100 shares
- NWL: 250 shares
- STLA: 275 shares

### What You're Currently Seeing 📊
- Holdings list with quantities
- Single data point (today's NAV)
- Empty chart (just created)

### What You SHOULD See (After Refresh) 💎

**1. Performance Chart - 90 Days of History**
```
NAV ($)
  65,000 ┤                                    ╭─╮
  63,000 ┤                          ╭────────╯  ╰─╮
  61,000 ┤                    ╭─────╯              ╰
  59,000 ┤              ╭─────╯
  57,000 ┤        ╭─────╯
  55,000 ┤   ╭────╯
  53,000 ┼───╯
         └───────────────────────────────────────────────
         Nov 8     Dec 1      Jan 1      Feb 1    Today
```

**2. Key Metrics**
- **Current NAV:** $63,036
- **90-Day Return:** +18.9%
- **Annualized Volatility:** 22.4%
- **Max Drawdown:** -8.3%
- **Sharpe Ratio:** 1.45

**3. Position Attribution**
```
Symbol  | Weight | Return | Contribution
--------|--------|--------|-------------
AAPL    | 29.3%  | +12.5% | +3.7%
META    | 76.8%  | +25.2% | +19.4%
NWL     |  3.4%  | -15.2% | -0.5%
STLA    |  6.2%  | +8.1%  | +0.5%
```
Shows: META is driving your returns (76% weight, strong performance)

**4. Risk Metrics Over Time**
- Volatility trending down (stabilizing)
- Drawdown recovered from -12% to -8%
- Rolling Sharpe improving

---

## How to See This Data

Your backend **already calculates** all this! The frontend needs to call:

### 1. Performance Time Series
```bash
GET /api/v1/analytics/portfolios/{portfolio_id}/performance
```

**Response:**
```json
{
  "portfolio_id": "...",
  "portfolio_name": "RBG Test 1",
  "dates": ["2025-11-08", "2025-11-09", ..., "2026-02-06"],
  "nav_values": [53000, 53150, ..., 63036],
  "returns": [null, 0.0028, 0.0015, ..., 0.0021]
}
```

**Use this to:**
- Plot NAV chart over time
- Show cumulative returns
- Calculate annualized return

### 2. Current Metrics (from latest day)
```bash
GET /api/v1/analytics/portfolios/{portfolio_id}/performance
# Take the last date's data
```

Shows:
- Latest NAV
- Latest return_1d
- Latest volatility_30d
- Latest max_drawdown

### 3. Compare Portfolios
```bash
GET /api/v1/analytics/portfolios/compare?ids={id1},{id2},{id3}
```

**Use case:** Compare:
- "Tech Growth" vs. "Balanced ETF" vs. SPY benchmark
- Your portfolio vs. market index
- Different strategies side-by-side

---

## Real-World Use Cases

### Use Case 1: Active Trader
**Scenario:** You actively trade and want to know if you're beating the market.

**Workflow:**
1. Create portfolio "My Active Trades" with current positions
2. Create benchmark portfolio "SPY" with 100% SPY
3. Compare performance over 90 days
4. See: "My Active Trades: +18.9%, SPY: +12.3% → Alpha: +6.6%"

**Value:** Know if your strategy is actually working.

### Use Case 2: Rebalancing Analysis
**Scenario:** You rebalanced on Jan 15. Did it help?

**Workflow:**
1. Portfolio v1: Original allocation (Nov - Jan 15)
2. Portfolio v2: Rebalanced (Jan 15 - present)
3. Compare versions using `/portfolios/{id}/diff?from=1&to=2`
4. See impact on volatility and returns

**Value:** Data-driven rebalancing decisions.

### Use Case 3: Risk Management
**Scenario:** Market volatility increased. Is your portfolio too risky?

**Workflow:**
1. View volatility_30d trend
2. Check max_drawdown
3. Compare to risk tolerance (e.g., "I'm OK with 20% vol, 15% max DD")
4. Adjust positions if needed

**Value:** Stay within risk limits.

---

## Current Status: What Works NOW

✅ **Backend Calculations:**
- Daily NAV computation
- Returns (1-day, MTD, YTD)
- 30-day rolling volatility
- Max drawdown from peak
- Position-level attribution

✅ **90 Days of Historical Data:**
- All seeded portfolios now have 3 months of history
- Your "RBG Test 1" has 65 trading days
- Charts will show trend lines

✅ **API Endpoints:**
- `/api/v1/analytics/portfolios/{id}/performance` - Time series
- `/api/v1/analytics/portfolios/compare` - Multi-portfolio comparison
- `/api/v1/portfolios/{id}` - Current holdings

## What the Frontend Should Display

### Portfolio Dashboard
```
┌─────────────────────────────────────────────────────┐
│ RBG Test 1                                    $63,036│
│ +18.9% (90d) │ Vol: 22.4% │ Max DD: -8.3%          │
├─────────────────────────────────────────────────────┤
│                                                       │
│  NAV Performance (90 days)                           │
│                                                       │
│  65k ┤                               ╭─────────      │
│  60k ┤                     ╭─────────╯               │
│  55k ┤           ╭─────────╯                         │
│  50k ┤   ╭───────╯                                   │
│      └───────────────────────────────────────────    │
│       Nov        Dec        Jan        Feb           │
│                                                       │
├─────────────────────────────────────────────────────┤
│ Holdings (v1)                                         │
│                                                       │
│ AAPL    100 shares    $18,550    29.3%    +12.5%    │
│ META    100 shares    $48,520    76.8%    +25.2%    │
│ NWL     250 shares     $2,125     3.4%    -15.2%    │
│ STLA    275 shares     $3,919     6.2%     +8.1%    │
│                                                       │
├─────────────────────────────────────────────────────┤
│ Risk Metrics                                          │
│                                                       │
│ 30-Day Volatility         22.4%   ▼ Decreasing      │
│ Max Drawdown              -8.3%   ▲ Recovering       │
│ Sharpe Ratio (90d)         1.45   ▲ Good             │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### Comparison View
```
Compare: RBG Test 1 vs. Tech Growth vs. SPY

      RBG Test 1    Tech Growth    SPY (Benchmark)
NAV   $63,036       $118,456       $51,075
90d   +18.9%        +22.3%         +12.3%
Vol   22.4%         28.1%          15.2%
DD    -8.3%         -12.1%         -5.4%

[Line chart showing all 3 overlaid]
```

---

## Summary: The Value

| Without PI | With PI |
|------------|---------|
| "My portfolio is worth $63k" | "My portfolio gained 18.9% in 90 days" |
| "I hold AAPL and META" | "META contributed 19.4% to returns" |
| "Markets are volatile" | "My 30-day vol is 22.4%, within my 25% limit" |
| "Should I rebalance?" | "Version 2 reduced vol by 4% with similar returns" |
| "Am I doing well?" | "I'm beating SPY by 6.6% (alpha generation)" |

## Next Steps

1. ✅ **Backend ready** - All analytics calculated
2. ✅ **90 days of data** - Charts will show trends
3. 🔲 **Frontend integration** - Call analytics endpoints
4. 🔲 **Visualize metrics** - Charts, KPIs, attribution tables
5. 🔲 **Compare features** - Side-by-side portfolio comparison

**Refresh your portfolio page** - with 90 days of backdated data, the chart should now show a line, not just a dot!

---

**TL;DR:** Portfolio Intelligence turns "I own these stocks" into "Here's how my portfolio has performed, where the returns came from, and how risky it is compared to benchmarks."
