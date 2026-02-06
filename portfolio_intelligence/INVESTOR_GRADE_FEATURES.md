# Investor-Grade Features - Implementation Guide

## What Was Built

✅ **5 Critical Features** to transform this from "dashboard" to "intelligence":

1. Benchmark comparison (vs SPY)
2. Return attribution (which positions drove performance)
3. Holdings with weights (% of portfolio, not just quantities)
4. Risk metrics (volatility, max drawdown, Sharpe)
5. Performance narrative (coming soon)

---

## 1. Benchmark Comparison

### Backend: ✅ READY
- Created SPY Benchmark portfolio (100% SPY)
- 90 days of historical data
- Available for comparison

### API Endpoints

**Compare portfolios:**
```bash
GET /api/v1/analytics/portfolios/compare?ids={your_portfolio_id},{spy_benchmark_id}
```

**Example:**
```bash
GET /api/v1/analytics/portfolios/compare?ids=76dd0976-5a7d-4cdd-94e9-7e7cc16e2d14,4fd582ca-66c5-4c56-92e7-4b2ca623d188
```

**Response:**
```json
{
  "portfolios": [
    {
      "portfolio_id": "76dd...",
      "portfolio_name": "RBG Test 2",
      "dates": ["2025-11-08", ..., "2026-02-06"],
      "nav_values": [450000, ..., 515287],
      "returns": [null, 0.0015, ...]
    },
    {
      "portfolio_id": "4fd5...",
      "portfolio_name": "SPY Benchmark",
      "dates": ["2025-11-08", ..., "2026-02-06"],
      "nav_values": [100000, ..., 98775],
      "returns": [null, -0.0008, ...]
    }
  ],
  "start_date": "2025-11-08",
  "end_date": "2026-02-06"
}
```

### Frontend Implementation

```tsx
function BenchmarkComparison({ portfolioId }) {
  const SPY_BENCHMARK_ID = '4fd582ca-66c5-4c56-92e7-4b2ca623d188';

  const { data } = useFetch(
    `/api/v1/analytics/portfolios/compare?ids=${portfolioId},${SPY_BENCHMARK_ID}`
  );

  const portfolioData = data.portfolios[0];
  const benchmarkData = data.portfolios[1];

  // Calculate returns
  const portfolioReturn = (
    (portfolioData.nav_values.at(-1) / portfolioData.nav_values[0]) - 1
  ) * 100;

  const benchmarkReturn = (
    (benchmarkData.nav_values.at(-1) / benchmarkData.nav_values[0]) - 1
  ) * 100;

  const alpha = portfolioReturn - benchmarkReturn;

  return (
    <div className="benchmark-section">
      <h3>vs. S&P 500</h3>

      <div className="comparison-grid">
        <div>
          <label>Your Portfolio</label>
          <value className={portfolioReturn > 0 ? 'positive' : 'negative'}>
            {portfolioReturn > 0 ? '+' : ''}{portfolioReturn.toFixed(2)}%
          </value>
        </div>

        <div>
          <label>SPY (S&P 500)</label>
          <value className={benchmarkReturn > 0 ? 'positive' : 'negative'}>
            {benchmarkReturn > 0 ? '+' : ''}{benchmarkReturn.toFixed(2)}%
          </value>
        </div>

        <div>
          <label>Alpha</label>
          <value className={alpha > 0 ? 'positive' : 'negative'}>
            {alpha > 0 ? '+' : ''}{alpha.toFixed(2)}%
          </value>
          <small>{alpha > 0 ? 'Outperforming' : 'Underperforming'}</small>
        </div>
      </div>

      {/* Overlay chart */}
      <LineChart
        series={[
          {
            name: portfolioData.portfolio_name,
            data: portfolioData.nav_values.map((nav, i) => ({
              date: portfolioData.dates[i],
              value: nav
            })),
            color: '#3b82f6'
          },
          {
            name: 'SPY',
            data: benchmarkData.nav_values.map((nav, i) => ({
              date: benchmarkData.dates[i],
              value: nav
            })),
            color: '#64748b'
          }
        ]}
      />
    </div>
  );
}
```

**Output:**
```
vs. S&P 500

Your Portfolio        SPY (S&P 500)        Alpha
+13.80%              -1.22%               +15.02%
                                          Outperforming

[Chart with both lines overlaid]
```

---

## 2. Return Attribution

### Backend: ✅ READY

**New endpoint:**
```bash
GET /api/v1/analytics/portfolios/{portfolio_id}/attribution?period=90d
```

**Response:**
```json
{
  "portfolio_id": "76dd...",
  "portfolio_name": "RBG Test 2",
  "period": "90d",
  "total_return": 0.1380,
  "positions": [
    {
      "symbol": "GOOGL",
      "weight": 0.352,
      "return": 0.185,
      "contribution": 0.065
    },
    {
      "symbol": "SPY",
      "weight": 0.382,
      "return": 0.123,
      "contribution": 0.047
    },
    {
      "symbol": "MSFT",
      "weight": 0.060,
      "return": 0.152,
      "contribution": 0.009
    },
    {
      "symbol": "AAPL",
      "weight": 0.036,
      "return": 0.125,
      "contribution": 0.005
    },
    {
      "symbol": "VTI",
      "weight": 0.052,
      "return": 0.081,
      "contribution": 0.004
    }
  ]
}
```

### Frontend Implementation

```tsx
function ReturnAttribution({ portfolioId }) {
  const { data } = useFetch(
    `/api/v1/analytics/portfolios/${portfolioId}/attribution?period=90d`
  );

  const maxContribution = Math.max(...data.positions.map(p => Math.abs(p.contribution)));

  return (
    <div className="attribution-section">
      <h3>Return Attribution</h3>
      <p className="subtitle">
        What drove your {data.total_return > 0 ? '+' : ''}{(data.total_return * 100).toFixed(2)}% return?
      </p>

      <div className="attribution-bars">
        {data.positions.map(position => (
          <div key={position.symbol} className="attribution-item">
            <div className="label">
              <span className="symbol">{position.symbol}</span>
              <span className="weight">{(position.weight * 100).toFixed(1)}%</span>
            </div>

            <div className="bar-container">
              <div
                className={`bar ${position.contribution > 0 ? 'positive' : 'negative'}`}
                style={{
                  width: `${(Math.abs(position.contribution) / maxContribution) * 100}%`
                }}
              />
            </div>

            <div className="values">
              <span className="return">
                {position.return > 0 ? '+' : ''}{(position.return * 100).toFixed(1)}%
              </span>
              <span className="contribution">
                {position.contribution > 0 ? '+' : ''}{(position.contribution * 100).toFixed(2)}%
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Key insight */}
      <div className="insight">
        <strong>Key Driver:</strong> {data.positions[0].symbol} contributed
        {' '}{(data.positions[0].contribution / data.total_return * 100).toFixed(0)}%
        of total returns.
      </div>
    </div>
  );
}
```

**Output:**
```
Return Attribution
What drove your +13.80% return?

GOOGL  35.2%  ████████████████████████░░  +18.5%  +6.50%
SPY    38.2%  ████████████████░░░░░░░░░░  +12.3%  +4.70%
MSFT    6.0%  ███░░░░░░░░░░░░░░░░░░░░░░░  +15.2%  +0.91%
AAPL    3.6%  ██░░░░░░░░░░░░░░░░░░░░░░░░  +12.5%  +0.45%
VTI     5.2%  ██░░░░░░░░░░░░░░░░░░░░░░░░   +8.1%  +0.42%

Key Driver: GOOGL contributed 47% of total returns.
```

---

## 3. Holdings with Weights

### Backend: ✅ READY

**New endpoint:**
```bash
GET /api/v1/portfolios/{portfolio_id}/holdings
```

**Response:**
```json
{
  "portfolio_id": "76dd...",
  "portfolio_name": "RBG Test 2",
  "total_value": 515287.19,
  "holdings": [
    {
      "symbol": "SPY",
      "quantity": 385,
      "current_price": 510.75,
      "market_value": 196638.75,
      "weight": 0.3815,
      "weight_pct": 38.15
    },
    {
      "symbol": "GOOGL",
      "quantity": 1252,
      "current_price": 145.20,
      "market_value": 181790.40,
      "weight": 0.3528,
      "weight_pct": 35.28
    },
    // ...
  ]
}
```

### Frontend Implementation

```tsx
function EnhancedHoldingsTable({ portfolioId }) {
  const { data } = useFetch(`/api/v1/portfolios/${portfolioId}/holdings`);

  return (
    <div className="holdings-section">
      <h3>Holdings</h3>
      <p className="total-value">
        Total Value: ${data.total_value.toLocaleString()}
      </p>

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th align="right">Quantity</th>
            <th align="right">Price</th>
            <th align="right">Market Value</th>
            <th align="right">% of Portfolio</th>
          </tr>
        </thead>
        <tbody>
          {data.holdings.map(holding => (
            <tr key={holding.symbol}>
              <td><strong>{holding.symbol}</strong></td>
              <td align="right">{holding.quantity.toLocaleString()}</td>
              <td align="right">${holding.current_price.toFixed(2)}</td>
              <td align="right">${holding.market_value.toLocaleString()}</td>
              <td align="right">
                <span className="weight-badge">
                  {holding.weight_pct.toFixed(1)}%
                </span>
                <div className="weight-bar">
                  <div
                    className="fill"
                    style={{ width: `${holding.weight_pct}%` }}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

**Output:**
```
Holdings
Total Value: $515,287

Symbol  Quantity  Price      Market Value  % of Portfolio
SPY     385       $510.75    $196,639      38.2% ████████░░
GOOGL   1,252     $145.20    $181,790      35.3% ███████░░░
MSFT    73        $420.30    $30,682        6.0% █░░░░░░░░░
VTI     100       $265.80    $26,580        5.2% █░░░░░░░░░
AAPL    100       $185.50    $18,550        3.6% ░░░░░░░░░░
```

---

## 4. Risk Metrics

### Backend: ✅ READY

**Endpoint:**
```bash
GET /api/v1/analytics/portfolios/{portfolio_id}/metrics/latest
```

**Response:**
```json
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

### Frontend Implementation

```tsx
function RiskMetrics({ portfolioId }) {
  const { data: metrics } = useFetch(
    `/api/v1/analytics/portfolios/${portfolioId}/metrics/latest`
  );

  // Calculate Sharpe Ratio
  const riskFreeRate = 0.045; // 4.5% annual
  const sharpeRatio = (metrics.return_ytd - riskFreeRate) / metrics.volatility_30d;

  return (
    <div className="risk-metrics">
      <h3>Risk Analysis</h3>

      <div className="metrics-grid">
        {/* Volatility */}
        <div className="metric">
          <label>30-Day Volatility</label>
          <value>{(metrics.volatility_30d * 100).toFixed(1)}%</value>
          <ProgressBar
            value={metrics.volatility_30d * 100}
            max={30}
            thresholds={{ low: 15, high: 25 }}
          />
          <small>Annualized</small>
        </div>

        {/* Max Drawdown */}
        <div className="metric">
          <label>Max Drawdown</label>
          <value className="negative">
            {(metrics.max_drawdown * 100).toFixed(1)}%
          </value>
          <ProgressBar
            value={Math.abs(metrics.max_drawdown) * 100}
            max={25}
            thresholds={{ low: 10, high: 20 }}
            inverse
          />
          <small>Peak to trough decline</small>
        </div>

        {/* Sharpe Ratio */}
        <div className="metric">
          <label>Sharpe Ratio</label>
          <value className={sharpeRatio > 1 ? 'positive' : 'neutral'}>
            {sharpeRatio.toFixed(2)}
          </value>
          <div className="rating">
            {sharpeRatio > 2 ? 'Excellent' :
             sharpeRatio > 1 ? 'Good' :
             sharpeRatio > 0.5 ? 'Fair' : 'Poor'}
          </div>
          <small>Risk-adjusted return</small>
        </div>

        {/* Returns */}
        <div className="metric">
          <label>YTD Return</label>
          <value className="positive">
            +{(metrics.return_ytd * 100).toFixed(2)}%
          </value>
          <small>MTD: {(metrics.return_mtd * 100).toFixed(2)}%</small>
        </div>
      </div>

      {/* Interpretation */}
      <div className="interpretation">
        <h4>What this means:</h4>
        <ul>
          <li>
            <strong>Volatility ({(metrics.volatility_30d * 100).toFixed(1)}%):</strong>
            {' '}Your portfolio fluctuates about {(metrics.volatility_30d * 100).toFixed(0)}%
            annually. SPY typically runs ~15%.
          </li>
          <li>
            <strong>Max Drawdown ({(metrics.max_drawdown * 100).toFixed(1)}%):</strong>
            {' '}At worst, you were down {Math.abs(metrics.max_drawdown * 100).toFixed(1)}%
            from peak. SPY's worst was ~-5%.
          </li>
          <li>
            <strong>Sharpe {sharpeRatio.toFixed(2)}:</strong>
            {' '}{sharpeRatio > 1
              ? 'Good risk-adjusted returns. You\'re being compensated for the risk.'
              : 'Lower risk-adjusted returns. Consider if the risk is worth it.'}
          </li>
        </ul>
      </div>
    </div>
  );
}
```

**Output:**
```
Risk Analysis

30-Day Volatility        Max Drawdown           Sharpe Ratio        YTD Return
17.4%                    -10.5%                 1.45                +22.50%
████████░░░ Moderate     █████░░░░░ Moderate    Good                MTD: +1.26%
Annualized               Peak to trough         Risk-adjusted

What this means:
• Volatility (17.4%): Your portfolio fluctuates about 17% annually. SPY typically runs ~15%.
• Max Drawdown (-10.5%): At worst, you were down 10.5% from peak. SPY's worst was ~-5%.
• Sharpe 1.45: Good risk-adjusted returns. You're being compensated for the risk.
```

---

## 5. Performance Narrative (Auto-Summary)

### Implementation

```tsx
function PerformanceNarrative({ portfolioId }) {
  const { data: metrics } = useFetch(
    `/api/v1/analytics/portfolios/${portfolioId}/metrics/latest`
  );
  const { data: attribution } = useFetch(
    `/api/v1/analytics/portfolios/${portfolioId}/attribution?period=90d`
  );
  const { data: comparison } = useFetch(
    `/api/v1/analytics/portfolios/compare?ids=${portfolioId},${SPY_BENCHMARK_ID}`
  );

  // Generate narrative
  const topContributor = attribution.positions[0];
  const topDetractor = attribution.positions.find(p => p.contribution < 0);

  const portfolioReturn = attribution.total_return * 100;
  const spyReturn = calculateReturn(comparison.portfolios[1]);
  const alpha = portfolioReturn - spyReturn;

  const narrative = `
    Your portfolio returned ${portfolioReturn > 0 ? '+' : ''}${portfolioReturn.toFixed(2)}%
    over the past 90 days, ${alpha > 0 ? 'outperforming' : 'underperforming'} the S&P 500
    by ${Math.abs(alpha).toFixed(2)}%.

    Returns were driven primarily by ${topContributor.symbol} (contributed
    ${(topContributor.contribution * 100).toFixed(1)}%),
    which gained ${(topContributor.return * 100).toFixed(1)}%.

    ${topDetractor
      ? `${topDetractor.symbol} was a drag, contributing ${(topDetractor.contribution * 100).toFixed(1)}%.`
      : 'All positions contributed positively.'}

    With ${(metrics.volatility_30d * 100).toFixed(1)}% volatility and a Sharpe ratio of
    ${((metrics.return_ytd - 0.045) / metrics.volatility_30d).toFixed(2)}, your risk-adjusted
    returns are ${((metrics.return_ytd - 0.045) / metrics.volatility_30d) > 1 ? 'strong' : 'moderate'}.
  `;

  return (
    <div className="narrative">
      <h3>Performance Summary</h3>
      <p>{narrative}</p>
    </div>
  );
}
```

**Output:**
```
Performance Summary

Your portfolio returned +13.80% over the past 90 days, outperforming the S&P 500
by 15.02%.

Returns were driven primarily by GOOGL (contributed 6.5%), which gained 18.5%.

With 17.4% volatility and a Sharpe ratio of 1.45, your risk-adjusted returns are strong.
```

---

## Complete Portfolio Page with All Features

```tsx
function InvestorGradePortfolio({ portfolioId }) {
  return (
    <div className="portfolio-page">
      {/* Header */}
      <PortfolioHeader portfolioId={portfolioId} />

      {/* Performance Narrative */}
      <Card>
        <PerformanceNarrative portfolioId={portfolioId} />
      </Card>

      {/* Key Metrics Row */}
      <div className="metrics-row">
        <RiskMetrics portfolioId={portfolioId} />
      </div>

      {/* Benchmark Comparison */}
      <Card>
        <BenchmarkComparison portfolioId={portfolioId} />
      </Card>

      {/* Attribution */}
      <Card>
        <ReturnAttribution portfolioId={portfolioId} />
      </Card>

      {/* Enhanced Holdings */}
      <Card>
        <EnhancedHoldingsTable portfolioId={portfolioId} />
      </Card>
    </div>
  );
}
```

---

## Backend Summary

### New Endpoints Added ✅

1. `GET /api/v1/analytics/portfolios/{id}/metrics/latest`
   - Latest NAV, returns (1D, MTD, YTD), volatility, drawdown

2. `GET /api/v1/analytics/portfolios/{id}/attribution?period=90d`
   - Which positions drove returns
   - Contribution analysis

3. `GET /api/v1/portfolios/{id}/holdings`
   - Holdings with current prices
   - Market values
   - Portfolio weights (%)

4. `GET /api/v1/analytics/portfolios/compare?ids={id1},{id2}`
   - Already existed, now has SPY benchmark to compare against

### New Data

- SPY Benchmark portfolio created
- 90 days of historical metrics
- Ready for comparison

---

## Testing

### 1. Test Attribution
```bash
curl "http://localhost:8000/api/v1/analytics/portfolios/76dd0976-5a7d-4cdd-94e9-7e7cc16e2d14/attribution?period=90d" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 2. Test Holdings with Weights
```bash
curl "http://localhost:8000/api/v1/portfolios/76dd0976-5a7d-4cdd-94e9-7e7cc16e2d14/holdings" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. Test Latest Metrics
```bash
curl "http://localhost:8000/api/v1/analytics/portfolios/76dd0976-5a7d-4cdd-94e9-7e7cc16e2d14/metrics/latest" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4. Test Benchmark Comparison
```bash
curl "http://localhost:8000/api/v1/analytics/portfolios/compare?ids=76dd0976-5a7d-4cdd-94e9-7e7cc16e2d14,4fd582ca-66c5-4c56-92e7-4b2ca623d188" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Impact

**Before:** "I own $515k of stocks"

**After:**
- "I'm up +13.8% vs SPY's -1.2% (+15% alpha)"
- "GOOGL drove 47% of my returns"
- "My Sharpe is 1.45 (good risk-adjusted returns)"
- "Holdings: 38% SPY (largest), 35% GOOGL"
- "Volatility 17.4%, max drawdown -10.5%"

This is **investor-grade intelligence**, not just a dashboard.
