# Envoy Financial Intelligence Suite — Documentation

**Last Updated**: 2026-02-06

---

## Suite Overview

The Envoy Financial Intelligence Suite is a collection of financial analysis tools:

| Tool | Status | Tech Stack | Port (Dev) |
|------|--------|-----------|------------|
| ISM Report Analysis | 🟢 Production | Flask + CrewAI + OpenAI | 5000 |
| Financial News Analysis | 🟢 Production | Flask + Anthropic Claude | 5000 |
| Portfolio Intelligence | 🟡 MVP Development | FastAPI + Next.js 14 | 8000 / 3100 |

**Architecture**: Same repo, directory-based separation. Flask app serves ISM and News. Portfolio Intelligence deploys as separate services (FastAPI API, Celery worker, Next.js frontend).

---

## Documentation Map

### Cross-Cutting
- [Documentation Guidelines](./documentation-guidelines.md) — How we write and maintain docs
- [Design Tokens](../portfolio_intelligence/docs/design-tokens.md) — Shared brand identity

### Domains

| Domain | README | Status Doc |
|--------|--------|-----------|
| Suite Integration | [README](./suite/README.md) | [Status](./suite/status/current-implementation-status.md) |
| ISM Report Analysis | [README](./ism/README.md) | [Status](./ism/status/current-implementation-status.md) |
| Financial News Analysis | [README](./news/README.md) | [Status](./news/status/current-implementation-status.md) |
| Portfolio Intelligence | [README](./portfolio-intelligence/README.md) | [Status](./portfolio-intelligence/status/current-implementation-status.md) |

### Portfolio Intelligence Planning
- [PRD](../portfolio_intelligence/docs/prd.md) — Product Requirements Document
- [TDD](../portfolio_intelligence/docs/tdd.md) — Technical Design Document

---

## Quick Start (Development)

```bash
# From repo root:
honcho start -f Procfile.dev
```

This starts all services: Flask (:5000), FastAPI (:8000), Celery worker, Next.js (:3100).

Prerequisites:
- Redis running (`brew services start redis`)
- PostgreSQL running with `portfolio_intelligence` database
- Flask venv: `.venv/` (run `pip install -r requirements.txt`)
- PI backend venv: `portfolio_intelligence/backend/.venv/` (run `pip install -r requirements.txt`)
- PI frontend deps: `portfolio_intelligence/frontend/node_modules/` (run `npm install`)

---

## Documentation Standards

All documentation follows the [Documentation Guidelines](./documentation-guidelines.md). Key rules:
1. Every domain has ONE canonical status document that is ALWAYS current
2. Update status docs when completing features
3. Archive completed planning docs
4. Single source of truth — no duplicate status information

**Last Review**: 2026-02-06
