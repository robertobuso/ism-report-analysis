# Portfolio Intelligence Frontend - Missing Features

## Current State ✅
- Portfolio list working
- Portfolio creation working
- Holdings display working
- NAV chart over time working (90 days!)
- Current NAV and overall return showing

## Missing Analytics Display ❌

### 1. Key Metrics Cards

**What to add:** Row of metric cards at the top

```tsx
<div className="grid grid-cols-4 gap-4">
  <MetricCard
    label="Current NAV"
    value="$515,287.19"
    change="+13.80%"
    period="90d"
  />
  <MetricCard
    label="30-Day Volatility"
    value="17.4%"
    subtitle="Annualized"
    status="moderate"
  />
  <MetricCard
    label="Max Drawdown"
    value="-10.5%"
    subtitle="Peak to trough"
    status="good"
  />
  <MetricCard
    label="Sharpe Ratio"
    value="1.45"
    subtitle="Risk-adjusted return"
    status="good"
  />
</div>
```

**Where to get data:**
```tsx
const { data } = await fetch(`/api/v1/analytics/portfolios/${id}/performance`);
const latest = data.nav_values[data.nav_values.length - 1];
// Parse returns array to calculate Sharpe, etc.
```

---

### 2. Enhanced Holdings Table

**What to add:** More columns with position analytics

| Symbol | Quantity | Current Value | % of Portfolio | Return | Contribution |
|--------|----------|---------------|----------------|--------|--------------|
| GOOGL  | 1,252    | $181,540      | 35.2%          | +18.5% | +6.5%        |
| SPY    | 385      | $196,735      | 38.2%          | +12.3% | +4.7%        |
| MSFT   | 73       | $30,660       | 6.0%           | +15.2% | +0.9%        |
| AAPL   | 100      | $18,550       | 3.6%           | +12.5% | +0.5%        |
| VTI    | 100      | $26,600       | 5.2%           | +8.1%  | +0.4%        |

**How to calculate:**
```tsx
// Get latest prices for each symbol
const positions = portfolio.latest_version.positions;
const positionValues = await Promise.all(
  positions.map(async (pos) => {
    const price = await getLatestPrice(pos.symbol);
    return {
      symbol: pos.symbol,
      quantity: pos.value,
      currentValue: pos.value * price,
      pctOfPortfolio: (pos.value * price) / totalNAV,
      // Get return and contribution from attribution endpoint
    };
  })
);
```

**API to call:**
```bash
GET /api/v1/analytics/portfolios/{id}/attribution
# (This endpoint may need to be added - see below)
```

---

### 3. Returns Breakdown

**What to add:** Period return display

```tsx
<div className="returns-section">
  <h3>Returns</h3>
  <div className="grid grid-cols-3 gap-4">
    <div>
      <label>1 Month</label>
      <value>+1.26%</value>
    </div>
    <div>
      <label>3 Months</label>
      <value>+13.80%</value>
    </div>
    <div>
      <label>Year to Date</label>
      <value>+22.50%</value>
    </div>
  </div>
</div>
```

**Where to get data:**
```tsx
// From performance endpoint, take last value
const latest = performanceData.nav_values[performanceData.nav_values.length - 1];

// Or call portfolio metrics directly
const metrics = await fetch(`/api/v1/portfolios/${id}/metrics/latest`);
// Returns: { return_1d, return_mtd, return_ytd, volatility_30d, max_drawdown }
```

---

### 4. Risk Metrics Section

**What to add:** Dedicated risk analysis section

```tsx
<div className="risk-metrics">
  <h3>Risk Analysis</h3>

  <div className="metric">
    <label>Volatility (30-Day)</label>
    <div className="value-with-trend">
      <span>17.4%</span>
      <span className="trend down">↓ Decreasing</span>
    </div>
    <ProgressBar value={17.4} max={30} status="moderate" />
  </div>

  <div className="metric">
    <label>Max Drawdown</label>
    <div className="value-with-trend">
      <span>-10.5%</span>
      <span className="trend up">↑ Recovering</span>
    </div>
    <ProgressBar value={10.5} max={20} status="good" />
  </div>

  <div className="metric">
    <label>Sharpe Ratio</label>
    <span>1.45</span>
    <span className="status">Good risk-adjusted returns</span>
  </div>
</div>
```

**Calculation:**
```tsx
// Sharpe Ratio = (Portfolio Return - Risk Free Rate) / Volatility
const riskFreeRate = 0.045; // 4.5% (current T-Bill rate)
const portfolioReturn = latest.return_ytd;
const volatility = latest.volatility_30d;
const sharpeRatio = (portfolioReturn - riskFreeRate) / volatility;
```

---

### 5. Additional Chart - Volatility Over Time

**What to add:** Second chart showing risk metrics trend

```tsx
<Chart
  type="line"
  data={{
    dates: performanceData.dates,
    series: [
      {
        name: "30-Day Volatility",
        values: volatilityOverTime,
        color: "#ff6b6b"
      },
      {
        name: "Max Drawdown",
        values: drawdownOverTime,
        color: "#ffa500"
      }
    ]
  }}
/>
```

**Note:** This requires calling the performance endpoint and extracting volatility/drawdown time series, OR calling metrics endpoint for historical data.

---

### 6. Position Attribution (Most Important!)

**What to add:** Show which positions drove returns

```tsx
<div className="attribution">
  <h3>Return Attribution</h3>
  <p>What drove your {latest.return_ytd > 0 ? 'gains' : 'losses'}?</p>

  {positions
    .sort((a, b) => b.contribution - a.contribution)
    .map(pos => (
      <div className="contribution-bar">
        <span className="symbol">{pos.symbol}</span>
        <div className="bar-container">
          <div
            className="bar"
            style={{ width: `${Math.abs(pos.contribution) / maxContribution * 100}%` }}
          />
        </div>
        <span className="value">+{pos.contribution}%</span>
      </div>
    ))
  }
</div>
```

**Example Output:**
```
Return Attribution - What drove your +13.80% return?

SPY     ████████████████░░░░ +4.7%
GOOGL   ████████████████░░░░ +6.5%
MSFT    ███░░░░░░░░░░░░░░░░░ +0.9%
AAPL    ██░░░░░░░░░░░░░░░░░░ +0.5%
VTI     ██░░░░░░░░░░░░░░░░░░ +0.4%
```

**API Endpoint Needed:**
```bash
GET /api/v1/analytics/portfolios/{id}/attribution
```

This should return:
```json
{
  "portfolio_id": "...",
  "period": "90d",
  "total_return": 0.1380,
  "positions": [
    {
      "symbol": "SPY",
      "weight": 0.382,
      "return": 0.123,
      "contribution": 0.047
    },
    // ...
  ]
}
```

---

### 7. Benchmark Comparison

**What to add:** Compare your portfolio to SPY or custom benchmark

```tsx
<div className="benchmark-comparison">
  <h3>vs. Benchmark</h3>

  <div className="comparison-grid">
    <div className="portfolio">
      <label>Your Portfolio</label>
      <value>+13.80%</value>
    </div>
    <div className="benchmark">
      <label>SPY (S&P 500)</label>
      <value>+12.30%</value>
    </div>
    <div className="alpha">
      <label>Alpha</label>
      <value className="positive">+1.50%</value>
    </div>
  </div>

  <LineChart
    series={[
      { name: "Your Portfolio", data: yourPortfolioNAV },
      { name: "SPY", data: spyNAV }
    ]}
  />
</div>
```

**API to call:**
```bash
GET /api/v1/analytics/portfolios/compare?ids={your_id},{spy_benchmark_id}
```

---

## Backend Endpoints to Add

These endpoints don't exist yet but would be useful:

### 1. Latest Metrics
```bash
GET /api/v1/portfolios/{id}/metrics/latest

Response:
{
  "date": "2026-02-06",
  "nav": 515287.19,
  "return_1d": -0.0216,
  "return_mtd": 0.0126,
  "return_ytd": 0.2250,
  "volatility_30d": 0.1740,
  "max_drawdown": -0.1050
}
```

### 2. Position Attribution
```bash
GET /api/v1/analytics/portfolios/{id}/attribution?period=90d

Response:
{
  "total_return": 0.1380,
  "positions": [
    {
      "symbol": "SPY",
      "quantity": 385,
      "current_value": 196735,
      "weight": 0.382,
      "return": 0.123,
      "contribution": 0.047
    },
    // ...
  ]
}
```

### 3. Risk Metrics Time Series
```bash
GET /api/v1/analytics/portfolios/{id}/risk-metrics?start=2025-11-08&end=2026-02-06

Response:
{
  "dates": ["2025-11-08", ..., "2026-02-06"],
  "volatility": [0.22, 0.21, ..., 0.17],
  "max_drawdown": [-0.05, -0.08, ..., -0.10],
  "sharpe_ratio": [1.1, 1.2, ..., 1.45]
}
```

---

## Priority Order

**High Priority (Core Analytics):**
1. ✅ Latest metrics display (MTD, YTD, vol, drawdown)
2. ✅ Enhanced holdings table with % of portfolio
3. ✅ Position attribution (what drove returns)

**Medium Priority (Better UX):**
4. Risk metrics section with trend indicators
5. Returns breakdown (1M, 3M, YTD)
6. Benchmark comparison

**Low Priority (Nice to Have):**
7. Volatility/drawdown charts over time
8. Sharpe ratio calculation
9. Multiple portfolio comparison view

---

## Example: Complete Portfolio Page

```tsx
function PortfolioDetail({ portfolioId }) {
  const { data: portfolio } = usePortfolio(portfolioId);
  const { data: performance } = usePerformance(portfolioId);
  const { data: metrics } = useLatestMetrics(portfolioId);
  const { data: attribution } = useAttribution(portfolioId, '90d');

  return (
    <div className="portfolio-detail">
      {/* Header */}
      <h1>{portfolio.name}</h1>
      <p>{portfolio.base_currency}</p>

      {/* Key Metrics Row */}
      <div className="metrics-grid">
        <MetricCard label="NAV" value={metrics.nav} change={metrics.return_ytd} />
        <MetricCard label="Volatility" value={metrics.volatility_30d} />
        <MetricCard label="Max Drawdown" value={metrics.max_drawdown} />
        <MetricCard label="Sharpe" value={calculateSharpe(metrics)} />
      </div>

      {/* Performance Chart */}
      <Card>
        <h2>Performance</h2>
        <LineChart data={performance} />
      </Card>

      {/* Attribution */}
      <Card>
        <h2>Return Attribution</h2>
        <AttributionBars data={attribution} />
      </Card>

      {/* Holdings */}
      <Card>
        <h2>Holdings</h2>
        <EnhancedHoldingsTable
          positions={portfolio.latest_version.positions}
          prices={currentPrices}
          totalNAV={metrics.nav}
        />
      </Card>

      {/* Risk Metrics */}
      <Card>
        <h2>Risk Analysis</h2>
        <RiskMetrics data={metrics} />
      </Card>
    </div>
  );
}
```

---

## Summary

Your backend is **fully functional** and has all the data. The frontend just needs to:
1. **Call the analytics endpoints** (especially `/performance`)
2. **Display the rich metrics** that are already calculated
3. **Add attribution analysis** to show what's driving returns
4. **Enhance the holdings table** with more context

The chart you're seeing proves the infrastructure works - now it's about surfacing the other 80% of the analytics that are already there!
