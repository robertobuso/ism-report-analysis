# Technical Design Document — Company Intelligence

**Project:** Company Intelligence Page
**Audience:** Engineering, Technical Stakeholders
**Scope:** v1 Feature Addition to Portfolio Intelligence
**Primary Goal:** A portfolio-aware decision cockpit for individual securities — answering "What changed? Why does it matter? What are my options?"
**Status:** Approved — Ready for Implementation
**Date:** 2026-02-07

---

## 1. Feature Overview

The Company Intelligence page is the primary decision-support surface for individual securities within Portfolio Intelligence. It allows an investor to deeply understand why a specific holding is impacting their portfolio and what actions they might consider.

Core principles:

* **Decision-first, not data-first** — always answer what changed, why it matters, what the options are
* **Portfolio-aware at all times** — every view is contextualized by the user's actual portfolio
* **Progressive disclosure** — insights first, charts second, raw data only when expanded
* **Explainable intelligence** — any computed or AI-generated insight exposes its inputs
* **Non-prescriptive** — show impact, scenarios, and tradeoffs — never buy/sell recommendations

### Decisions Log

| # | Decision | Rationale |
|---|---|---|
| 1 | Alpha Vantage tier: grandfathered premium (30 req/min, no daily cap) | Plenty of headroom for ~12 calls per page load |
| 2 | Auto-detect portfolio context from navigation origin | Pass `portfolio_id` in URL; avoids ambiguity when ticker exists in multiple portfolios |
| 3 | Quick Actions v1: "Compare" + "Open SEC Filings" only | "Add Note", "Set Alert", "Export" stubbed as Coming Soon to avoid scope explosion |
| 4 | Simplified Scenario Explorer (v1) | Weight redistribution + scaled vol estimate. API designed for full covariance swap-in later |
| 5 | LLM-powered insights via GPT-5.2 | Structured outputs for typed insight cards. Rule-based fallback on failure |
| 6 | Position Health Score: equal weights (25% each) | Fundamentals, price trend, sentiment, portfolio impact — evenly balanced |

### Approved Spec Changes

* Add **loading skeletons** per tab (lazy-loaded data)
* Add **`lightweight-charts`** (TradingView) for candlestick charts
* Add **"Data Freshness" indicators** on all cached sections
* Define **mobile breakpoints** (panes stack, grids collapse)
* **"Export Company Brief"** = print-optimized HTML (browser save-as-PDF)

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js)                      │
│                                                            │
│  /company/[symbol]?portfolio_id=xxx                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐    │
│  │  Header   │  │ Insights │  │    Tab Content         │    │
│  │ (sticky)  │  │ (3 cards)│  │  (lazy-loaded per tab) │    │
│  └──────────┘  └──────────┘  └───────────────────────┘    │
│         │              │              │                     │
│         ▼              ▼              ▼                     │
│  ┌──────────────── React Query ───────────────────────┐    │
│  │  useCompanyHeader()    useCompanyInsights()         │    │
│  │  useCompanyOverview()  useNewsSentiment()           │    │
│  │  useFinancials()       useEarnings()                │    │
│  │  useTechnicals()       usePortfolioImpact()         │    │
│  └────────────────────────────────────────────────────┘    │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTPS (JWT)
┌───────────────────────────▼────────────────────────────────┐
│                   BACKEND (FastAPI)                          │
│                                                              │
│  /api/v1/company/{symbol}/...                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           Company Intelligence Router                 │    │
│  │  /header  /insights  /overview  /financials           │    │
│  │  /earnings  /news  /technicals  /portfolio-impact     │    │
│  │  /scenario                                            │    │
│  └─────────────────┬────────────────────────────────────┘    │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐    │
│  │      Company Intelligence Service                     │    │
│  │  - Orchestrates AV calls + Redis cache                │    │
│  │  - Calls GPT-5.2 for insights & narratives            │    │
│  │  - Computes quality badges & health scores            │    │
│  │  - Runs scenario simulations                          │    │
│  └──┬──────────────┬──────────────┬─────────────────────┘    │
│     │              │              │                           │
│     ▼              ▼              ▼                           │
│  ┌────────┐  ┌──────────┐  ┌───────────────┐                │
│  │ Alpha  │  │  Redis   │  │  OpenAI       │                │
│  │ Vantage│  │  Cache   │  │  GPT-5.2      │                │
│  │ Client │  │ (TTL)    │  │  (structured  │                │
│  │(extend)│  │          │  │   outputs)    │                │
│  └────────┘  └──────────┘  └───────────────┘                │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Existing Services (unchanged)                        │    │
│  │  - PortfolioAnalyticsEngine (attribution, metrics)    │    │
│  │  - PriceIngestionService (daily prices in DB)         │    │
│  │  - PortfolioService (holdings, versions)              │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. New Dependencies

### Backend (Python)

| Package | Purpose |
|---------|---------|
| `openai>=2.17.0` | GPT-5.2 async client with structured output support |

`redis.asyncio` is already available in `redis>=5.0.0` (in requirements.txt). No new package needed for caching.

### Frontend (npm)

| Package | Purpose | Size |
|---------|---------|------|
| `lightweight-charts` | Candlestick charts (TradingView open-source) | ~40KB gzipped |

Why these choices:

* **OpenAI SDK** — native async support, Pydantic schema integration for guaranteed JSON conformance, retry built-in
* **lightweight-charts** — purpose-built for financial charts, used by TradingView itself, tiny footprint. Recharts does not support candlestick charts natively
* **Redis for caching** — already running for Celery; adding a cache layer is zero infrastructure cost

---

## 4. Alpha Vantage API Integration

**Rate budget:** 30 req/min (grandfathered premium). A full page load with empty cache = ~12 calls. Comfortable margin.

### Endpoint Mapping

| Spec Feature | AV Function | Cache TTL |
|---|---|---|
| Company name, description, sector, metrics | `OVERVIEW` | 24h |
| Real-time quote (price, change) | `GLOBAL_QUOTE` | 5 min |
| News articles with URLs, summaries, sentiment | `NEWS_SENTIMENT` | 15 min |
| Earnings history (actual vs estimate, surprise) | `EARNINGS` | 24h |
| Income statement (annual + quarterly) | `INCOME_STATEMENT` | 24h |
| Balance sheet (annual + quarterly) | `BALANCE_SHEET` | 24h |
| Cash flow (annual + quarterly) | `CASH_FLOW` | 24h |
| RSI (daily, 14-period) | `RSI` | 1h |
| MACD (daily) | `MACD` | 1h |
| Bollinger Bands (daily, 20-period) | `BBANDS` | 1h |
| 50-day / 200-day SMA | `SMA` | 1h |
| Daily prices (OHLCV) | `TIME_SERIES_DAILY_ADJUSTED` | Already in DB |

### New Client Methods

Added to `app/services/alphavantage.py`:

```python
async def get_company_overview(self, symbol: str) -> dict
async def get_global_quote(self, symbol: str) -> dict
async def get_news_sentiment(self, tickers: str, time_from: str = None,
                              time_to: str = None, sort: str = "LATEST",
                              limit: int = 50) -> dict
async def get_earnings(self, symbol: str) -> dict
async def get_income_statement(self, symbol: str) -> dict
async def get_balance_sheet(self, symbol: str) -> dict
async def get_cash_flow(self, symbol: str) -> dict
async def get_technical_indicator(self, symbol: str, indicator: str,
                                   interval: str = "daily",
                                   time_period: int = 14) -> dict
```

---

## 5. GPT-5.2 Integration

### Model Selection

* **Primary:** `gpt-5.2-chat-latest` (Instant variant — fast, lower latency)
* **Fallback:** Rule-based templates (pre-computed from same data, used on timeout or failure)
* **Reasoning effort:** `medium` for insight cards, `low` for financial narratives

### Use Cases

| Feature | GPT-5.2 Output | Cache TTL |
|---|---|---|
| "Why This Matters Now" insight cards | 3 typed `InsightCard` objects | 30 min |
| "Explain the Change" financial narrative | 2-3 sentence summary | 24h |
| "What they sell" business bullets | 3-5 bullet points | 24h |
| Signal Summary interpretation | Plain-English trend summary | 1h |

### Structured Outputs

GPT-5.2 guarantees JSON schema conformance via `response_format`. Pydantic models define the schema; model output always parses correctly.

```python
from openai import AsyncOpenAI

class InsightCard(BaseModel):
    type: Literal["market_narrative", "portfolio_impact", "earnings_signal"]
    severity: Literal["positive", "neutral", "negative"]
    summary: str
    tab_target: str
    data_inputs: dict[str, Any]

class InsightCardsResponse(BaseModel):
    cards: list[InsightCard]

response = await client.chat.completions.create(
    model="gpt-5.2-chat-latest",
    messages=[
        {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(structured_data)}
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "insight_cards",
            "strict": True,
            "schema": InsightCardsResponse.model_json_schema()
        }
    },
    reasoning_effort="medium"
)
```

### Prompt Design Principles

1. **Portfolio-aware context** — always include position size, weight, contribution
2. **Non-prescriptive guardrail** — system prompt forbids buy/sell recommendations
3. **Explainability mandate** — every insight references its data inputs
4. **Severity calibration** — clear thresholds (e.g., sentiment delta > 0.3 = negative)
5. **One-sentence constraint** — each insight card is exactly 1 sentence

### Cost Estimate

* ~$0.005 per call ($1.75/M input + $14/M output)
* With 30-min cache: ~48 calls/day per active ticker = ~$0.24/day/ticker
* 90% prompt caching discount after first call per system prompt

### Error Handling

* 10-second timeout on all GPT-5.2 calls
* Rule-based fallback on timeout or failure
* 1 retry with exponential backoff on 5xx errors

---

## 6. Caching Strategy

Using **Redis** (already running for Celery). The `redis>=5.0.0` package includes `redis.asyncio` built-in.

### Cache Key Patterns

```python
CACHE_KEYS = {
    "overview":    "ci:{symbol}:overview",            # TTL: 24h
    "quote":       "ci:{symbol}:quote",               # TTL: 5min
    "financials":  "ci:{symbol}:financials",           # TTL: 24h
    "earnings":    "ci:{symbol}:earnings",             # TTL: 24h
    "news":        "ci:{symbol}:news:{params_hash}",   # TTL: 15min
    "technicals":  "ci:{symbol}:tech:{indicator}",     # TTL: 1h
    "insights":    "ci:{symbol}:insights:{port_id}",   # TTL: 30min
    "narrative":   "ci:{symbol}:narrative:{period}",    # TTL: 24h
}
```

### Behavior

* **Read-through:** Redis check → miss → call AV/GPT → store with TTL → return
* **On-demand population:** No background refresh
* **TTL-based expiry:** No manual invalidation needed
* **Data freshness:** Each cached response stores `fetched_at` timestamp, returned to frontend for "Updated X min ago" display

Why Redis over PostgreSQL tables:

* Zero infrastructure cost (already running)
* TTL-based expiry is native
* JSON storage is natural
* Transient data — doesn't belong in the relational schema

---

## 7. Backend: New Services

### New Files

| File | Purpose |
|---|---|
| `app/services/company_intelligence.py` | Orchestration: AV calls + Redis cache + GPT-5.2 + computed metrics |
| `app/services/redis_cache.py` | Generic async Redis wrapper (get/set with TTL) |
| `app/services/scenario.py` | Scenario Explorer computations (weight redistribution, vol estimation) |
| `app/services/llm.py` | OpenAI GPT-5.2 wrapper (structured outputs, prompts, retry, fallback) |

### Modified Files

| File | Change |
|---|---|
| `app/services/alphavantage.py` | Add 8 new methods (overview, news, earnings, 3x financials, technicals, quote) |
| `app/api/v1/router.py` | Register `company_router` |
| `app/dependencies.py` | Add `get_redis()`, `get_llm_client()`, `get_company_intelligence_service()` |
| `app/config.py` | Add `openai_api_key`, `openai_model`, cache TTL settings |
| `app/main.py` | Initialize Redis pool + OpenAI client in lifespan |
| `requirements.txt` | Add `openai>=2.17.0` |

### Company Intelligence Service

The orchestration service handles:

* Cache-through reads for all AV data
* GPT-5.2 calls for insight generation (with rule-based fallback)
* Quality badge computation from financial statement trends
* Position Health Score computation (equal-weighted composite)
* Concentration alert detection (sector grouping, theme overlap)

### Scenario Service

Simplified v1 approach:

* Accept action: `trim_25`, `trim_50`, `exit`, `add_10`
* Recalculate weights after action
* Estimate new volatility by scaling historical portfolio vol by weight change
* Simulate max drawdown by replaying historical returns with new weights
* Re-rank holdings by risk contribution

The API contract is designed so a full covariance-based engine can replace this without frontend changes.

---

## 8. Backend: API Endpoints

All endpoints under `/api/v1/company/{symbol}/`.

### Endpoint Summary

| Method | Path | Sources | Returns |
|---|---|---|---|
| GET | `/header?portfolio_id={uuid}` | GLOBAL_QUOTE + OVERVIEW + portfolio holdings | CompanyHeader |
| GET | `/insights?portfolio_id={uuid}` | NEWS_SENTIMENT + attribution + EARNINGS + prices → GPT-5.2 | list[InsightCard] |
| GET | `/overview` | OVERVIEW → GPT-5.2 (business bullets) | CompanyOverview |
| GET | `/financials?period=quarterly\|annual` | INCOME_STATEMENT + BALANCE_SHEET + CASH_FLOW → GPT-5.2 (narrative) | FinancialsResponse |
| GET | `/earnings` | EARNINGS | EarningsResponse |
| GET | `/news?time_range=&sort=&limit=&sentiment=&topic=` | NEWS_SENTIMENT | NewsSentimentResponse |
| GET | `/technicals?indicators=RSI,MACD,...` | RSI + MACD + BBANDS + SMA → GPT-5.2 (signal summary) | TechnicalsResponse |
| GET | `/portfolio-impact?portfolio_id={uuid}` | Existing analytics + OVERVIEW (sector) | PortfolioImpactResponse |
| GET | `/scenario?portfolio_id={uuid}&action=trim_25` | Existing price data + analytics | ScenarioResult |

### Data Fetching Sequence

```
Page Load (immediate, parallel):
  ├── /header           → sticky header
  ├── /insights         → "Why This Matters Now" cards
  └── /overview         → overview tab (default tab)

On Tab Switch (lazy):
  Tab 2 → /financials
  Tab 3 → /earnings
  Tab 4 → /news
  Tab 5 → /technicals
  Tab 6 → /portfolio-impact

User Action:
  Scenario button → /scenario
```

---

## 9. Backend: Data Schemas

No database migrations required. All new data is transient (Redis-cached AV responses, GPT-5.2 output) or computed from existing tables (prices, holdings, analytics).

### Key Pydantic Models

```python
class CompanyHeader(BaseModel):
    symbol: str
    name: str
    exchange: str
    sector: str | None
    industry: str | None
    current_price: float
    change_amount: float
    change_percent: float
    sparkline: list[float]           # last 30 closing prices
    shares_held: float | None        # None if not in portfolio
    cost_basis: float | None
    unrealized_pl: float | None
    portfolio_weight: float | None
    contribution_to_return: float | None
    fetched_at: datetime

class InsightCard(BaseModel):
    type: Literal["market_narrative", "portfolio_impact", "earnings_signal"]
    severity: Literal["positive", "neutral", "negative"]
    summary: str
    tab_target: str
    data_inputs: dict[str, Any]

class CompanyOverview(BaseModel):
    description: str
    business_bullets: list[str]      # GPT-5.2 generated
    sector: str | None
    industry: str | None
    country: str | None
    market_cap: float | None
    pe_ratio: float | None
    forward_pe: float | None
    eps: float | None
    dividend_yield: float | None
    week_52_high: float | None
    week_52_low: float | None
    avg_volume: int | None
    beta: float | None
    profit_margin: float | None
    book_value: float | None
    price_to_book: float | None
    price_to_sales: float | None
    shares_outstanding: int | None
    sec_filings_url: str | None
    profitability_trend: Literal["improving", "stable", "declining"] | None
    leverage_risk: Literal["low", "moderate", "high"] | None
    dilution_risk: Literal["low", "moderate", "high"] | None
    fetched_at: datetime

class NewsArticle(BaseModel):
    title: str
    url: str
    summary: str
    source: str
    banner_image: str | None
    time_published: datetime
    overall_sentiment_score: float
    overall_sentiment_label: str
    ticker_relevance_score: float
    ticker_sentiment_score: float
    ticker_sentiment_label: str
    topics: list[str]

class SentimentDataPoint(BaseModel):
    date: str
    score: float
    article_count: int

class NewsSentimentResponse(BaseModel):
    articles: list[NewsArticle]
    sentiment_trend: list[SentimentDataPoint]
    topic_distribution: dict[str, int]
    total_articles: int
    fetched_at: datetime

class EarningsQuarter(BaseModel):
    fiscal_date: str
    reported_date: str | None
    reported_eps: float
    estimated_eps: float
    surprise: float
    surprise_pct: float

class EarningsResponse(BaseModel):
    quarterly: list[EarningsQuarter]
    annual: list[dict]
    beat_rate: float
    analyst_count: int | None
    next_earnings_date: str | None
    fetched_at: datetime

class FinancialStatement(BaseModel):
    fiscal_date: str
    reported_currency: str
    data: dict[str, Any]

class FinancialsResponse(BaseModel):
    period: Literal["quarterly", "annual"]
    income_statement: list[FinancialStatement]
    balance_sheet: list[FinancialStatement]
    cash_flow: list[FinancialStatement]
    narrative: str                    # GPT-5.2 generated
    chart_data: dict[str, list]      # pre-computed for frontend charts
    fetched_at: datetime

class TechnicalIndicatorData(BaseModel):
    indicator: str
    values: list[dict[str, Any]]

class SignalSummary(BaseModel):
    trend_vs_50dma: str
    trend_vs_200dma: str
    rsi_state: str
    macd_signal: str
    volatility_percentile: float
    interpretation: str              # GPT-5.2 generated

class TechnicalsResponse(BaseModel):
    indicators: list[TechnicalIndicatorData]
    signal_summary: SignalSummary
    fetched_at: datetime

class ConcentrationAlert(BaseModel):
    alert_type: str
    message: str
    holdings_involved: list[str]
    combined_weight: float

class HealthScore(BaseModel):
    total: float                     # 0-100
    fundamentals: float              # 0-25
    price_trend: float               # 0-25
    sentiment: float                 # 0-25
    portfolio_impact: float          # 0-25
    breakdown: dict[str, Any]

class PortfolioImpactResponse(BaseModel):
    contribution_to_return: float
    risk_contribution: float
    correlation_with_top_holdings: dict[str, float]
    sector_overlap: dict[str, float]
    concentration_alerts: list[ConcentrationAlert]
    health_score: HealthScore
    fetched_at: datetime

class ScenarioResult(BaseModel):
    action: str
    new_weights: dict[str, float]
    current_volatility: float
    new_volatility: float
    current_max_drawdown: float
    new_max_drawdown: float
    concentration_change: float
    risk_ranking_changes: list[dict]
```

---

## 10. Frontend: Page Structure

### Route

```
/company/[symbol]?portfolio_id=xxx
```

**Entry points:** Clicking a ticker anywhere in the app (portfolio table, attribution, charts).

**Navigation:** Breadcrumb "Portfolio > {name} > {TICKER}" with "Back to Portfolio" link. Portfolio context preserved via URL param.

### Page Layout

1. **Sticky Company Header** — identity, price + sparkline, portfolio context, quick actions
2. **"Why This Matters Now"** — 3 color-coded insight cards (green/amber/red), clickable to navigate to relevant tab
3. **Tab Navigation** (sticky below header) — 6 tabs
4. **Tab Content** — lazy-loaded per tab

### Tab Structure

| Tab | Purpose | Key Components |
|---|---|---|
| 1. Overview | Rapid orientation | Business description, metrics grid, quality badges |
| 2. Financials | Understand fundamentals | Revenue/margin/income charts, GPT narrative, collapsible statements, CSV download |
| 3. Earnings | Consistency and surprise analysis | Actual vs estimate timeline, beat rate, analyst count |
| 4. News & Sentiment | Connect narrative to price (differentiator) | Split pane: article feed + sentiment insights, sentiment-price overlay |
| 5. Price & Technicals | Timing and risk context | Candlestick chart (lightweight-charts), indicator panels, GPT signal summary |
| 6. Portfolio Impact | "What should I do?" (differentiator) | Impact metrics, concentration alerts, scenario explorer, health score |

### Responsive Breakpoints

| Breakpoint | Layout Changes |
|---|---|
| Desktop (1280px+) | Full layout: sticky header, side-by-side panes, 4-col metric grids |
| Tablet (768-1279px) | News panes stack, 2-col grids, condensed header |
| Mobile (<768px) | Single column, ticker+price header only (portfolio context expandable), 1-col grids |

---

## 11. Frontend: Component Tree

```
src/components/company/
├── company-header.tsx                # Sticky header
├── insight-cards.tsx                 # "Why This Matters Now"
├── tab-navigation.tsx                # Sticky tab bar
├── quick-actions.tsx                 # Header action buttons
├── tabs/
│   ├── overview-tab.tsx
│   ├── financials-tab.tsx
│   ├── earnings-tab.tsx
│   ├── news-sentiment-tab.tsx
│   ├── price-technicals-tab.tsx
│   └── portfolio-impact-tab.tsx
├── charts/
│   ├── sparkline.tsx                 # Mini price chart for header
│   ├── sentiment-price-overlay.tsx   # Dual-axis: sentiment + price
│   ├── earnings-timeline.tsx         # Grouped bar: actual vs estimate
│   ├── financial-charts.tsx          # Revenue, margins, income, FCF
│   ├── candlestick-chart.tsx         # TradingView lightweight-charts
│   └── technical-indicators.tsx      # RSI, MACD, BB panels
├── widgets/
│   ├── metrics-grid.tsx
│   ├── quality-badges.tsx
│   ├── news-article-card.tsx
│   ├── scenario-explorer.tsx
│   ├── concentration-alerts.tsx
│   ├── signal-summary.tsx
│   ├── health-score.tsx
│   └── data-freshness.tsx
└── skeletons/
    ├── header-skeleton.tsx
    ├── tab-skeleton.tsx
    └── chart-skeleton.tsx
```

### Modified Files

| File | Change |
|---|---|
| `src/lib/api.ts` | Add 9 new API methods for company endpoints |
| `src/lib/types.ts` | Add ~15 new TypeScript interfaces |
| `src/app/portfolios/[id]/page.tsx` | Make ticker symbols clickable → `/company/[symbol]?portfolio_id=X` |

### Candlestick Chart Integration

lightweight-charts is client-side only — requires dynamic import with SSR disabled:

```typescript
import dynamic from 'next/dynamic'

const CandlestickChart = dynamic(
  () => import('@/components/company/charts/candlestick-chart'),
  { ssr: false, loading: () => <ChartSkeleton /> }
)
```

---

## 12. Delivery Phases

### Phase 1: Backend Foundation

**Deliverable:** All data sources accessible, cached, testable via `/docs`

* Create `services/redis_cache.py` — async get/set/TTL wrapper
* Extend `AlphaVantageClient` with 8 new methods
* Create `services/llm.py` — AsyncOpenAI wrapper with structured outputs and fallback
* Create `schemas/company.py` — all Pydantic models
* Update `config.py`, `main.py`, `dependencies.py`
* Add `openai>=2.17.0` to `requirements.txt`

### Phase 2: Backend API + Intelligence Layer

**Deliverable:** All 9 endpoints working in Swagger UI

* Create `services/company_intelligence.py` — orchestration + caching + GPT-5.2
* Create `services/scenario.py` — simplified scenario computations
* Create `api/v1/company.py` — all endpoint handlers
* Register router in `api/v1/router.py`
* Implement GPT-5.2 insight generation, narratives, business bullets, signal summaries
* Implement quality badge and health score computation
* Implement concentration alert logic
* Implement rule-based fallbacks for all GPT features

### Phase 3: Frontend Shell + Header

**Deliverable:** Page renders with real header data, tab skeleton, breadcrumbs

* Add TypeScript interfaces and API methods
* Create page route `app/company/[symbol]/page.tsx`
* Build company-header, sparkline, tab-navigation, quick-actions, data-freshness
* Build skeleton components
* Make ticker symbols clickable in portfolio detail page

### Phase 4: Overview + Insight Cards

**Deliverable:** First fully functional tab with LLM-powered insights

* Build insight-cards (3 color-coded, clickable)
* Build overview-tab (description, bullets, metrics, badges)
* Build metrics-grid, quality-badges

### Phase 5: Financials + Earnings Tabs

**Deliverable:** Full fundamental analysis with GPT narratives

* Build financials-tab (quarterly/annual toggle, GPT narrative, charts, collapsible tables)
* Build financial-charts (5 Recharts: revenue, margins, income, FCF, cash vs debt)
* Build earnings-tab (timeline, beat rate, analyst count)
* Build earnings-timeline (grouped bar chart with surprise % labels)
* Build CSV download for financial statements

### Phase 6: News & Sentiment Tab

**Deliverable:** Full news intelligence with sentiment-price overlay

* Build news-sentiment-tab (split pane layout)
* Build news-article-card (banner, source, summary, sentiment badge, relevance)
* Build sentiment trend chart (7D/30D/90D toggle)
* Build topic distribution visualization
* Build filters and sorting controls
* Build sentiment-price-overlay (dual Y-axis — killer feature)
* Implement click-to-scroll: sentiment spike → causative articles

### Phase 7: Price & Technicals Tab

**Deliverable:** TradingView-quality candlestick chart with technical analysis

* Install `lightweight-charts`
* Build candlestick-chart (dynamic import, volume bars, timeframe selector)
* Add earnings + news event markers on chart
* Build technical-indicators (RSI, MACD, BB panels)
* Build signal-summary (trend, momentum, volatility + GPT interpretation)

### Phase 8: Portfolio Impact Tab

**Deliverable:** Portfolio-aware analysis with scenario explorer

* Build portfolio-impact-tab (metrics dashboard)
* Build concentration-alerts (sector/theme overlap warnings)
* Build scenario-explorer (trim 25%/50%, exit, add 10% controls + animated results)
* Build health-score (circular visualization with 4-component breakdown + explainability toggle)

### Phase 9: Polish & Integration

**Deliverable:** Production-ready page

* Global time-range selector
* Responsive design (desktop/tablet/mobile)
* Loading skeletons and error states for all sections
* Explainability toggles on AI insights
* Data freshness indicators
* Personalized portfolio language ("More volatile than 83% of your holdings")
* Print-optimized CSS for "Export Company Brief"
* Performance optimization (React.memo, useMemo)

---

## 13. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| GPT-5.2 latency on insights | Medium | Use Instant variant. 30-min cache. Rule-based fallback on timeout. |
| GPT-5.2 output quality variance | Medium | Strict JSON schema enforcement. Clear system prompt. Prompt iteration. |
| OpenAI API cost at scale | Low | ~$0.005/call. 30-min cache. 90% prompt caching discount. |
| AV rate limits (30 req/min) | Low | 12 calls per page load. Aggressive Redis caching. Lazy tab loading. |
| AV data gaps for small-cap tickers | Medium | Graceful degradation per section. "Data not available" messaging. |
| Financial statement normalization | Medium | AV normalizes to GAAP/IFRS. Parse defensively, handle null values. |
| Candlestick library + Next.js SSR | Low | Dynamic import with `ssr: false`. Well-tested pattern. |
| Scenario accuracy (simplified v1) | Low | Clearly labeled "estimated". API designed for covariance v2 swap-in. |
| Scope creep (Quick Actions) | Low | Stubbed as "Coming Soon". Clear phase boundaries. |

---

## 14. Why This Design Will Hold Up

* **No new database tables** — all transient data lives in Redis with TTL. The relational schema stays clean.
* **Provider-agnostic caching** — the Redis cache layer sits between the service and any data source. Swapping AV for another provider requires only client changes.
* **LLM-replaceable** — GPT-5.2 is behind an interface with rule-based fallback. Swapping models or switching to on-device inference changes one file.
* **Scenario API contract** — the simplified v1 engine returns the same schema as a full covariance-based engine would. Frontend never knows the difference.
* **Lazy-loading by design** — each tab fetches independently. Adding new tabs or data sources doesn't affect page load time.
* **Portfolio context flows naturally** — `portfolio_id` in the URL means every component can access portfolio-specific data without global state management.

---

## File Count Summary

| Category | New | Modified |
|---|---|---|
| Backend services | 4 | 1 |
| Backend API | 1 | 1 |
| Backend schemas | 1 | 0 |
| Backend config | 0 | 3 |
| Backend deps | 0 | 1 |
| Frontend page | 1 | 0 |
| Frontend components | ~23 | 3 |
| **Total** | **~30** | **~9** |

No database migrations required.
