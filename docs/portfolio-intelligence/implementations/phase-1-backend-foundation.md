# Phase 1 - Backend Foundation

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Portfolio Intelligence

---

## Overview

Built the FastAPI application skeleton, TradeStation OAuth 2.0 authentication, PostgreSQL database schema with 7 tables, and the market data ingestion service. This phase establishes the complete backend infrastructure that Phases 2 and 3 build upon.

---

## Technical Implementation

### FastAPI Application

**`app/main.py`** -- Application entry point.

- CORS middleware configured to allow the Next.js frontend origin.
- Async lifespan handler for startup/shutdown hooks.
- Health check endpoint at `GET /health`.
- Admin endpoints for manual ingestion triggers (development only).
- Mounts the v1 router under `/api/v1`.

**`app/config.py`** -- Centralized configuration.

- Pydantic `BaseSettings` class loading from environment variables.
- Fields: `DATABASE_URL`, `REDIS_URL`, `TS_CLIENT_ID`, `TS_CLIENT_SECRET`, `TS_REDIRECT_URI`, `JWT_SECRET`, `FERNET_KEY`, `FRONTEND_URL`.
- Validation ensures all required values are present at startup.

### Database

**`app/db/database.py`** -- Async database engine and session factory.

- `create_async_engine` with asyncpg driver.
- `async_sessionmaker` for dependency injection.

**Model files** (5 files, 7 tables):

| File | Tables | Key Columns |
|------|--------|------------|
| `models/user.py` | `users` | id, ts_user_id, email, ts_refresh_token_enc, created_at |
| `models/portfolio.py` | `portfolios`, `portfolio_versions`, `portfolio_positions` | Foreign keys linking user -> portfolio -> version -> positions. `allocation_type` ENUM (weight/quantity). |
| `models/instrument.py` | `instruments` | id, symbol, name, exchange, asset_type |
| `models/price.py` | `prices_daily` | instrument_id, date, open, high, low, close, volume. Unique constraint on (instrument_id, date). |
| `models/analytics.py` | `portfolio_metrics_daily` | portfolio_id, date, nav, daily_return, cumulative_return, volatility_30d, max_drawdown |

**Alembic** -- Configured for async migrations via `app/db/migrations/env.py`. Uses the same async engine as the application.

### Authentication

**`app/api/v1/auth.py`** -- Auth router with 4 endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/login` | GET | Builds TradeStation OAuth URL and returns redirect URI |
| `/auth/callback` | GET | Exchanges authorization code for tokens, creates/updates user, issues JWT |
| `/auth/refresh` | POST | Accepts refresh token, exchanges with TradeStation, issues new JWT |
| `/auth/me` | GET | Returns current user profile (requires valid JWT) |

**`app/services/tradestation.py`** -- TradeStation API client.

- `build_auth_url()` -- Constructs OAuth authorization URL with scopes.
- `exchange_code(code)` -- Exchanges authorization code for access + refresh tokens.
- `refresh_access_token(refresh_token)` -- Refreshes an expired access token.
- `get_daily_bars(symbol, start, end, access_token)` -- Fetches OHLCV daily bars.
- `get_user_profile(access_token)` -- Fetches TradeStation user profile.
- In-memory token cache with 20-minute TTL to reduce redundant token exchanges.
- All HTTP calls use httpx async client.

**`app/services/token_manager.py`** -- Token encryption service.

- Fernet symmetric encryption for refresh tokens stored in the database.
- `encrypt(plaintext)` and `decrypt(ciphertext)` methods using the `FERNET_KEY` from configuration.

### Market Data Ingestion

**`app/services/ingestion.py`** -- Ingestion service.

- `backfill_symbol(symbol, start_date, end_date)` -- Fetches historical daily bars from TradeStation and inserts into `prices_daily` using `INSERT ... ON CONFLICT (instrument_id, date) DO UPDATE`.
- `update_daily_prices(symbols)` -- Fetches the latest day's data for a list of symbols.
- 1-second delay between API calls to respect TradeStation rate limits.

### Dependencies

**`app/dependencies.py`** -- FastAPI dependency injection.

- `get_db()` -- Yields an async database session.
- `get_current_user(token)` -- Decodes JWT from `HTTPBearer` header, looks up user, raises 401 if invalid or expired.

### Schemas

Pydantic v2 models for request/response serialization:

- `schemas/user.py` -- `UserResponse`, `TokenResponse`
- `schemas/portfolio.py` -- `PortfolioCreate`, `PortfolioResponse`, `PositionCreate`, `VersionResponse`
- `schemas/instrument.py` -- `InstrumentResponse`, `PriceResponse`
- `schemas/analytics.py` -- `PerformancePoint`, `PerformanceSeries`, `PortfolioMetrics`

---

## Testing

Verified FastAPI application starts and the health check returns 200. Confirmed Alembic migrations create all 7 tables. Auth endpoints return correct HTTP status codes with mock TradeStation responses. End-to-end OAuth testing is blocked pending real TradeStation developer credentials.
