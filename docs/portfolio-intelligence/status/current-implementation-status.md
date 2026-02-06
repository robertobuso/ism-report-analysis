# Portfolio Intelligence - Current Implementation Status

**Last Updated**: 2026-02-06
**Status**: In Progress (MVP Development)

---

## What's Working

All items completed on 2026-02-06.

### Phase 0 - Foundation

- **PRD & TDD Updated** -- Allocation mode is now per-portfolio (weight vs. quantity), rendering strategy clarified, analytics time assumptions documented.
- **Design Tokens Locked** -- Full brand identity defined in `portfolio_intelligence/docs/design-tokens.md`.
- **Directory Scaffold** -- Complete project structure under `portfolio_intelligence/backend/` (app/, models/, schemas/, services/, tasks/, api/, db/, tests/) and `portfolio_intelligence/frontend/`.

### Phase 1 - Backend Foundation

- **FastAPI Skeleton** -- Application entry point at `portfolio_intelligence/backend/app/main.py` with health check, CORS middleware, lifespan handler, and v1 router mount.
- **Configuration** -- Pydantic BaseSettings at `app/config.py` loading all environment variables with validation.
- **PostgreSQL Schema** -- 7 tables defined via SQLAlchemy async models with Alembic migrations: `users`, `portfolios`, `portfolio_versions`, `portfolio_positions`, `instruments`, `prices_daily`, `portfolio_metrics_daily`.
- **TradeStation OAuth 2.0** -- Full auth flow: login redirect, callback token exchange, JWT issuance, token refresh endpoint, `/me` user info. Refresh tokens encrypted with Fernet.
- **TradeStation API Client** -- httpx async client at `app/services/tradestation.py` with `build_auth_url`, `exchange_code`, `refresh`, `daily_bars`, `get_user_profile`. In-memory token caching with 20-minute TTL.
- **Market Data Ingestion** -- Backfill and daily update service at `app/services/ingestion.py` with `INSERT ... ON CONFLICT` upsert and 1-second rate limiting between API calls.

### Phase 2 - Backend MVP

- **Portfolio CRUD** -- Full API at `app/api/v1/portfolios.py`: create, list, get, and delete portfolios. Version management with position snapshots. All queries scoped to the authenticated user.
- **Analytics Engine** -- `PortfolioAnalyticsEngine` class at `app/services/analytics.py`. Weight mode: NAV_0 = 100, NAV_n = NAV_{n-1} * (1 + sum(w_i * r_i)). Quantity mode: NAV = sum(q_i * close_i). Rolling 30-day volatility (sigma * sqrt(252)), max drawdown, per-holding contribution, version boundary handling (effective_at = next market open, weekends/holidays excluded).
- **API Endpoints** -- Performance series and portfolio comparison at `app/api/v1/analytics.py`. Instrument search (ILIKE), symbol lookup, and price history at `app/api/v1/instruments.py`.
- **Celery Worker** -- `app/worker.py` with Redis broker. Tasks at `app/tasks/ingestion.py`: `nightly_price_update` (6 PM ET, max 3 retries) and `backfill_symbol`. Runs as a separate process.

### Phase 3 - Frontend MVP

- **Next.js 14 Setup** -- TypeScript, Tailwind CSS (with design tokens), TanStack Query, Framer Motion, Recharts, Lucide icons. App Router.
- **Auth Flow** -- Login page redirects to TradeStation OAuth. Callback page stores JWT in localStorage. React auth context provides user state and logout.
- **Portfolio Creation** -- Full form at `src/app/portfolios/new/page.tsx`: name, description, allocation mode toggle (weight/quantity), holdings input with add/remove. Animated weight bar and position list via Framer Motion AnimatePresence. Weight warning badge when allocations do not sum to 100%.
- **Portfolio Overview** -- Performance dashboard at `src/app/portfolios/[id]/page.tsx`: NAV and total return header, time range selector (1M/3M/YTD/1Y/All), Recharts AreaChart with gradient fill, holdings table.
- **Home Page** -- `src/app/page.tsx` with 3 states: loading skeleton, unauthenticated CTA, and portfolio grid with cards plus empty-state CTA.
- **Shared Header** -- `src/components/layout/header.tsx` with nav links to Suite Home, ISM Analysis, and News Analysis (external via `NEXT_PUBLIC_SUITE_URL`) plus Portfolio Intelligence (internal).

---

## What's Remaining

### TradeStation API Testing

OAuth flow needs real TradeStation credentials for end-to-end testing. Currently using placeholder client_id and client_secret values.

- **Status**: BLOCKED -- need TradeStation developer account
- **Priority**: HIGH

### Symbol Autocomplete

Portfolio creation form needs instrument search integration. The backend endpoint exists at `/api/v1/instruments/search`, but the frontend is not yet wired to call it during holding entry.

- **Status**: NOT STARTED
- **Priority**: MEDIUM

### Holdings Enrichment

Holdings table in the portfolio overview is missing: last price, 30-day change, sparkline mini-chart, and per-holding contribution percentage.

- **Status**: NOT STARTED
- **Priority**: MEDIUM

### Key Metrics Sidebar

Portfolio overview page is missing: annualized volatility card, max drawdown card, best contributor card, and worst contributor card.

- **Status**: NOT STARTED
- **Priority**: MEDIUM

---

## What's Planned (Phase 4)

### Portfolio Comparison (Journey 5)

Multi-select portfolios from the home page, overlay their performance on a single chart, display side-by-side metric cards.

- **Priority**: Important
- **Effort**: 2-3 days

### Version History (Journey 4)

Timeline view of portfolio versions, version diff showing added/removed/changed positions.

- **Priority**: Important
- **Effort**: 2-3 days

### HTTP-only Cookie Auth

Migrate JWT storage from localStorage to HTTP-only secure cookies. This is a security upgrade required before production deployment.

- **Priority**: Important (pre-production)
- **Effort**: 1 day

### Railway Deployment

Deploy 4 services to Railway: flask (existing), portfolio-api, portfolio-worker, portfolio-frontend. Add PostgreSQL and Redis as Railway addons. Configure environment variables and inter-service networking.

- **Priority**: Critical (for launch)
- **Effort**: 1-2 days

### Cross-Linking Polish

Remove the "Coming Soon" badge from the Portfolio Intelligence card on the suite landing page. Verify all nav links work correctly in the production environment.

- **Priority**: Important
- **Effort**: 0.5 day

---

**Last Review**: 2026-02-06
