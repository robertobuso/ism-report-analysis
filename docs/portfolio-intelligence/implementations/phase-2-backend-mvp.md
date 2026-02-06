# Phase 2 - Backend MVP

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Portfolio Intelligence

---

## Overview

Implemented portfolio CRUD operations, the analytics engine for NAV computation and risk metrics, additional API endpoints for instruments and performance data, and the Celery worker for background price updates. This phase completes the backend functionality required for the MVP.

---

## Technical Implementation

### Portfolio CRUD

**`app/api/v1/portfolios.py`** -- Portfolio router.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/portfolios` | POST | Create portfolio with initial version and positions |
| `/portfolios` | GET | List all portfolios for the authenticated user |
| `/portfolios/{id}` | GET | Get portfolio with latest version and positions |
| `/portfolios/{id}` | DELETE | Soft-delete a portfolio |

All queries are scoped to the authenticated user via the `get_current_user` dependency. Creating a portfolio automatically creates the first version (v1) with the provided positions.

**`app/services/portfolio.py`** -- Portfolio business logic.

- Version lookup: resolves the effective version for a given date by finding the latest version with `effective_at <= date`.
- Weight validation: for weight-mode portfolios, warns (but does not reject) if position weights do not sum to 100%.
- Position snapshot: each version stores a full copy of all positions, enabling point-in-time reconstruction.

### Analytics Engine

**`app/services/analytics.py`** -- `PortfolioAnalyticsEngine` class.

**NAV Computation (Weight Mode)**:

```
NAV_0 = 100
NAV_n = NAV_{n-1} * (1 + sum(w_i * r_i))
```

Where `w_i` is the weight of holding `i` and `r_i` is its daily return `(close_i,n / close_i,n-1) - 1`.

**NAV Computation (Quantity Mode)**:

```
NAV_n = sum(q_i * close_i,n)
```

Where `q_i` is the number of shares and `close_i,n` is the closing price on day `n`.

**Risk Metrics**:

| Metric | Calculation |
|--------|------------|
| Rolling 30-day volatility | Standard deviation of daily returns over 30 trading days, annualized by multiplying by sqrt(252) |
| Max drawdown | Maximum peak-to-trough decline in NAV over the requested period |
| Per-holding contribution | Daily return attribution: `w_i * r_i / sum(w_j * r_j)` for each holding |

**Version Boundary Rules**:

- When a new version is created, its `effective_at` timestamp is set to the next market open (9:30 AM ET).
- Weekends and US market holidays are excluded. If a version is created on Friday evening, it becomes effective on Monday's open.
- Analytics computation switches position sets at version boundaries seamlessly.

### API Endpoints

**`app/api/v1/analytics.py`** -- Analytics router.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/analytics/portfolios/{id}/performance` | GET | Returns daily NAV series with optional date range and period (1M/3M/YTD/1Y/All) |
| `/analytics/portfolios/compare` | POST | Accepts list of portfolio IDs, returns overlaid performance series |

**`app/api/v1/instruments.py`** -- Instruments router.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/instruments/search` | GET | ILIKE search on symbol and name, returns top 20 matches |
| `/instruments/{symbol}` | GET | Lookup a single instrument by symbol |
| `/instruments/{symbol}/prices` | GET | Historical price data with date range filtering |

### Celery Worker

**`app/worker.py`** -- Celery application configuration.

- Broker: Redis (configured via `REDIS_URL`).
- Result backend: Redis.
- Timezone: `US/Eastern`.

**`app/tasks/ingestion.py`** -- Background tasks.

| Task | Schedule | Behavior |
|------|----------|----------|
| `nightly_price_update` | 6:00 PM ET daily | Fetches latest daily bars for all symbols referenced in active portfolios. Max 3 retries with exponential backoff. |
| `backfill_symbol` | On demand | Backfills historical price data for a newly added symbol. Triggered when a portfolio is created with a symbol that has no price history. |

The worker runs as a separate process: `celery -A app.worker worker --loglevel=info`.

### Router Aggregation

**`app/api/v1/router.py`** -- Aggregates all v1 routers.

Includes: `auth`, `portfolios`, `instruments`, `analytics` routers, all mounted under the `/api/v1` prefix.

---

## Testing

Verified portfolio CRUD operations return correct responses and enforce user scoping. Confirmed NAV computation produces expected values for known test inputs in both weight and quantity modes. Celery worker starts and connects to Redis successfully. Task scheduling was verified in development with manual triggers via the admin endpoints.
