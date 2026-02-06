# Technical Design Document

**Project:** Portfolio Analytics App (TradeStation-Integrated)
**Audience:** Engineering, Technical Stakeholders
**Scope:** MVP → Scalable v1
**Primary Goal:** Persistent, analyzable, versioned investment portfolios powered by TradeStation market data

---

## 1. System Overview

The system enables a client to:

* Create and manage **multiple portfolios**
* Track **portfolio evolution over time** (versions)
* View **historical performance and trends**
* Compare portfolios and portfolio versions
* Pull **authoritative market data** from TradeStation
* Rely on **locally persisted price history** for analytics stability

The system is **read-only** with respect to brokerage actions (no trading).

---

## 2. High-Level Architecture

```
┌──────────────┐
│   Frontend   │  Next.js (React)
│              │
└──────┬───────┘
       │ HTTPS (JWT)
┌──────▼────────────────────────────┐
│              API                   │  FastAPI
│  - Auth (OAuth)                    │
│  - Portfolio Management            │
│  - Analytics Endpoints             │
└──────┬───────────────┬────────────┘
       │               │
┌──────▼──────┐  ┌─────▼──────────┐
│ PostgreSQL  │  │ Ingestion Worker│  Celery
│ (Primary DB)│  │ + Redis Queue   │
└─────────────┘  └─────┬──────────┘
                       │
                ┌──────▼─────────┐
                │ TradeStation API│
                │ (SIM / LIVE)    │
                └────────────────┘
```

---

## 3. Preferred Tech Stack (Modern, Stable, Non-Conflicting)

### Backend

* **Python 3.12**
* **FastAPI 0.110+**
* **Pydantic v2**
* **SQLAlchemy 2.0 (async)**
* **Alembic** (migrations)
* **Celery 5.3+**
* **Redis 7**
* **HTTPX** (async HTTP client)
* **APScheduler** (complementary scheduler for cron-like triggers that dispatch Celery tasks)

Why this stack:

* Fully async
* Pydantic v2 + SQLAlchemy 2.0 are aligned
* No deprecated patterns
* Excellent for data-heavy services
* Redis serves triple duty: Celery task broker, quote caching, and session management
* APScheduler triggers Celery tasks on schedule (not running them in-process)

---

### Frontend

* **Next.js 14**
* **React 18**
* **TypeScript 5**
* **TanStack Query**
* **Recharts or ECharts**
* **Tailwind CSS**

Why:

* SSR for fast dashboards
* Query caching for analytics views
* Modern React without experimental features

---

### Database

* **PostgreSQL 15**
* Optional later: **TimescaleDB** (not required initially)

---

### 3.1 TradeStation API Specifics

| Property | Value |
|----------|-------|
| SIM Base URL | `https://sim-api.tradestation.com/v3` |
| LIVE Base URL | `https://api.tradestation.com/v3` |
| Token URL | `https://signin.tradestation.com/oauth/token` |
| Token Request Content-Type | `application/x-www-form-urlencoded` |
| Access Token TTL | 20 minutes |
| Refresh Token | Non-expiring (rotate on use) |
| Rate Limits | 5-minute rolling window |
| Daily Bars Endpoint | `GET /marketdata/barcharts/{symbol}` |

**Key implementation notes:**
- Access tokens must be cached in-memory keyed by `user_id` with expiry check
- Refresh tokens are encrypted at rest using Fernet symmetric encryption
- All API calls use `Authorization: Bearer {access_token}` header
- OAuth scopes: `MarketData ReadAccount offline_access openid profile`

---

### Authentication

* **TradeStation OAuth 2.0**
* Backend-managed tokens
* Encrypted refresh token storage

---

## 4. Authentication & Authorization Design

### OAuth Flow

* OAuth 2.0 Authorization Code Flow
* Backend owns client secret
* Frontend never touches TradeStation tokens

### Token Storage

* `access_token` (short-lived)
* `refresh_token` (encrypted at rest)
* Automatic refresh on expiry

### Scopes (Initial)

* `MarketData`
* `ReadAccount` (optional, future-proof)
* **No trading scope**

---

## 5. Data Model (Core Tables)

### Users

```
users
- id
- email
- created_at
```

---

### Portfolios (Logical Container)

```
portfolios
- id
- user_id
- name
- base_currency
- allocation_type ENUM('weight', 'quantity')
- created_at
```

**Notes:**
- `allocation_type` is set at portfolio creation and applies to ALL versions and positions
- Once set, cannot be changed (enforces consistency across portfolio history)

---

### Portfolio Versions (Critical Design Choice)

```
portfolio_versions
- id
- portfolio_id
- effective_at
- note
- created_at
```

**Why:**
Never overwrite portfolio state. Every edit creates a new version.

---

### Portfolio Positions

```
portfolio_positions
- id
- portfolio_version_id
- symbol
- allocation_type ENUM('weight', 'quantity')
- value DECIMAL(18,8)
```

**Notes:**
- `allocation_type` is **inherited from portfolio level** (all positions in a portfolio share the same type)
- Cannot mix allocation types within a single portfolio
- `value` represents target weight (0.0–1.0) in weight mode, or share quantity in quantity mode
- Migration completed (2024-02-06): moved allocation_type from position-level to portfolio-level

---

### Instruments

```
instruments
- id
- symbol
- name
- exchange
- sector
- industry
- logo_url
```

---

### Daily Prices

```
prices_daily
- instrument_id
- date
- open
- high
- low
- close
- adj_close
- volume
- source
```

Unique constraint:

```
(instrument_id, date)
```

---

### Portfolio Analytics (Materialized)

```
portfolio_metrics_daily
- portfolio_id
- date
- nav
- return_1d
- return_mtd
- return_ytd
- volatility_30d
- max_drawdown
```

---

## 6. Market Data Ingestion Strategy

### Ingestion Principles

* External APIs = **ingestion only**
* Analytics always run on **local data**
* Deterministic, repeatable results

---

### Initial Backfill

Triggered when:

* New symbol added to any portfolio

Process:

1. Fetch max available daily history
2. Store in `prices_daily`
3. Normalize symbols and metadata

---

### Daily Update Job

Runs nightly:

* Pull latest daily bar for all active instruments
* Insert/update
* Recompute analytics for affected portfolios

---

### Intraday (Optional, Phase 2)

* Streaming quotes for UI only
* **Never** used for analytics calculations

---

## 7. Portfolio Analytics Engine

### MVP Calculations

* Daily NAV
* Cumulative return
* Rolling volatility
* Max drawdown
* Contribution by holding

### Assumptions (Explicit)

* Weight-based portfolios
* Rebalanced at version effective date
* Price-return using adjusted close
* Dividends implicitly included via adjusted prices

These assumptions are documented and surfaced in UI.

---

### 7.1 Analytics Time Assumptions

These rules are **non-negotiable** for analytics correctness:

1. **`version.effective_at` is interpreted as next market open** — the new version applies starting the following trading day. A version created on Wednesday at 3pm takes effect Thursday at market open.

2. **`version.effective_at` is set dynamically based on available price data** — when creating a portfolio, the system finds the earliest date where ALL symbols have complete price data and sets that as effective_at. This ensures analytics always have complete data from day one. No hardcoded dates.

3. **All analytics are computed on daily close prices only** — no intraday calculations, ever. This ensures deterministic, reproducible results.

4. **Dividends are implicitly included via adjusted close prices** — no separate dividend tracking or reinvestment modeling in MVP.

5. **Weekends and market holidays are excluded from return calculations** — only trading days contribute to returns, volatility, and drawdown metrics.

6. **Price refreshes are dynamic** — when refreshing prices, the system calculates days from portfolio.effective_at to today (not hardcoded lookback periods). This ensures complete price history regardless of when the refresh occurs.

---

## 8. API Design (Representative)

### Portfolio

* `POST /portfolios`
* `POST /portfolios/{id}/versions`
* `GET /portfolios/{id}`
* `GET /portfolios/{id}/versions`

### Analytics

* `GET /portfolios/{id}/performance?start=&end=`
* `GET /portfolios/compare?ids=...`
* `GET /portfolios/{id}/diff?from=&to=`

### Instruments

* `GET /instruments/search?q=`
* `GET /instruments/{symbol}`
* `GET /instruments/{symbol}/prices`

---

## 9. Caching Strategy

### Redis

* Quote snapshots (TTL: 15–60s)
* Symbol metadata (TTL: 24h)
* Portfolio analytics (TTL: per market close)

### Why

* Avoid TradeStation rate limits
* Fast dashboards
* Deterministic analytics

---

## 10. Environments

| Environment | TradeStation Endpoint |
| ----------- | --------------------- |
| Local / Dev | SIM API               |
| Staging     | SIM API               |
| Production  | LIVE API              |

Environment variable driven:

```
TRADESTATION_BASE_URL
```

---

## 11. Security Considerations

* OAuth secrets server-side only
* Encrypted refresh tokens
* Read-only scopes
* No redistribution of raw market data
* Portfolio access strictly user-scoped

---

## 12. MVP Delivery Scope (Real, Non-Toy)

### Included

* OAuth integration
* Multi-portfolio support
* Portfolio versioning
* Daily performance charts
* Portfolio comparison
* Historical persistence

### Explicitly Excluded (for now)

* Trade execution
* Intraday analytics
* Tax modeling
* Real-time alerts

---

## 13. Why This Design Will Hold Up

* No data loss on edits
* No recomputation drift
* Clear audit trail
* Analytics scale linearly
* Easy to extend (benchmarks, factors, AI insights)


