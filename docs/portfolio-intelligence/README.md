# Portfolio Intelligence

**Domain**: Persistent, analyzable, versioned investment portfolios powered by TradeStation market data

## Current State Summary

Phases 0-3 are implemented. The FastAPI backend includes TradeStation OAuth 2.0 authentication, a PostgreSQL schema with 7 tables, an analytics engine for NAV computation and risk metrics, and a Celery worker for nightly price updates. The Next.js 14 frontend provides an auth flow, portfolio creation with allocation mode selection, and a performance dashboard with interactive charts. Not yet deployed to production.

## Quick Links

- [Current Implementation Status](status/current-implementation-status.md)
- [Phase 0 - Foundation](implementations/phase-0-foundation.md)
- [Phase 1 - Backend Foundation](implementations/phase-1-backend-foundation.md)
- [Phase 2 - Backend MVP](implementations/phase-2-backend-mvp.md)
- [Phase 3 - Next.js Frontend](implementations/phase-3-nextjs-frontend.md)
- [Design Tokens](../../portfolio_intelligence/docs/design-tokens.md)
- [Archive](archive/README.md)

## Architecture

Portfolio Intelligence is deployed as separate services, distinct from the Flask monolith:

| Service | Technology | Port (Dev) |
|---------|-----------|------------|
| API Server | FastAPI (Python 3.11) | 8000 |
| Frontend | Next.js 14 (TypeScript) | 3100 |
| Worker | Celery (Redis broker) | -- |
| Database | PostgreSQL | 5432 |
| Cache/Broker | Redis | 6379 |

Production deployment targets Railway with 4 services: flask, portfolio-api, portfolio-worker, and portfolio-frontend, plus PostgreSQL and Redis addons.

---

**Last Updated**: 2026-02-06
