# Phase 0 - Foundation

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Portfolio Intelligence

---

## Overview

Foundation work for the Portfolio Intelligence domain. Updated the PRD and TDD with allocation mode, rendering strategy, and analytics time assumptions. Locked design tokens for the brand identity. Scaffolded the full backend and frontend directory structure. The shared `base.html` template (covered in the Suite Integration docs) was also created during this phase.

---

## Technical Implementation

### PRD Updates

- **Allocation mode** is now per-portfolio rather than global. Each portfolio specifies either `weight` (percentage-based) or `quantity` (share count) mode at creation time.
- **Rendering strategy** clarified: the frontend is a separate Next.js application, not embedded in Flask templates.

### TDD Updates

- Added `allocation_type` ENUM column to the `portfolios` table (values: `weight`, `quantity`).
- Replaced APScheduler references with Celery for background task scheduling.
- Updated Section 3.1 to document TradeStation API integration details (OAuth scopes, daily bars endpoint, rate limits).
- Added Section 7.1 covering Analytics Time Assumptions: market hours, timezone handling (ET), weekend/holiday exclusion rules.

### Design Tokens

Created `portfolio_intelligence/docs/design-tokens.md` with the full brand identity:

| Token | Value |
|-------|-------|
| Primary color | `#1E3A5F` (deep navy) |
| Accent color | `#38BDF8` (sky blue) |
| Font family | Inter |
| Border radius | 8px |

The tokens are consumed by the Tailwind CSS configuration in the Next.js frontend and referenced by CSS variables in the shared base template.

### Directory Scaffold

Full project structure created:

```
portfolio_intelligence/
  backend/
    app/
      __init__.py
      main.py
      config.py
      dependencies.py
      worker.py
      api/
        __init__.py
        v1/
          __init__.py
          auth.py
          portfolios.py
          instruments.py
          analytics.py
          router.py
      models/
        __init__.py
        user.py
        portfolio.py
        instrument.py
        price.py
        analytics.py
      schemas/
        __init__.py
        user.py
        portfolio.py
        instrument.py
        analytics.py
      services/
        __init__.py
        tradestation.py
        token_manager.py
        ingestion.py
        portfolio.py
        analytics.py
      tasks/
        __init__.py
        ingestion.py
      db/
        __init__.py
        database.py
        migrations/
          env.py
    tests/
      __init__.py
      conftest.py
    requirements.txt
    .env.example
    Dockerfile
  frontend/
    (initialized with .gitkeep, populated in Phase 3)
  docs/
    design-tokens.md
```

### Additional Files

- **`requirements.txt`** -- FastAPI, uvicorn, SQLAlchemy[asyncio], asyncpg, alembic, pydantic-settings, httpx, python-jose, cryptography, celery, redis.
- **`.env.example`** -- Template for all required environment variables (database URL, Redis URL, TradeStation credentials, JWT secret, Fernet key).
- **`Dockerfile`** -- Multi-stage build for the FastAPI application.
- **`.gitignore`** -- Updated with Portfolio Intelligence entries: `.venv/`, `__pycache__/`, `.env`, `alembic/versions/*.pyc`.

---

## Testing

Verified that the directory scaffold matches the planned structure. Confirmed all `__init__.py` files are in place. Validated that `requirements.txt` installs cleanly in a fresh virtual environment.
