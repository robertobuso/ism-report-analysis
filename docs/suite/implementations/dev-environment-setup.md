# Dev Environment Setup

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Suite Integration

---

## Overview

Honcho-based dev environment that starts all services with a single command. Developers run `honcho start -f Procfile.dev` from the repo root and all four services start up with color-coded, interleaved log output. Ctrl+C cleanly kills everything.

---

## Procfile.dev

Located at the repository root. Defines 4 services:

```procfile
flask: .venv/bin/python app.py
api: sh -c 'cd portfolio_intelligence/backend && .venv/bin/uvicorn app.main:app --reload --port 8000'
worker: sh -c 'cd portfolio_intelligence/backend && .venv/bin/celery -A app.worker worker --loglevel=info --concurrency=2'
frontend: npm run dev --prefix portfolio_intelligence/frontend -- -p 3100
```

### Service Details

| Service | Command | Port | Virtual Environment |
|---------|---------|------|-------------------|
| `flask` | `.venv/bin/python app.py` | 5000 | `.venv/` (repo root) |
| `api` | `uvicorn app.main:app --reload` | 8000 | `portfolio_intelligence/backend/.venv/` |
| `worker` | `celery -A app.worker worker` | N/A | `portfolio_intelligence/backend/.venv/` |
| `frontend` | `npm run dev` | 3100 | N/A (Node.js) |

---

## Prerequisites

- **Redis** running via Homebrew (`brew services start redis`)
- **PostgreSQL** running with the required databases created
- **Two Python virtual environments** installed and dependencies resolved:
  - `.venv/` at the repo root for the Flask app
  - `portfolio_intelligence/backend/.venv/` for the FastAPI backend and Celery worker
- **Node.js dependencies** installed in `portfolio_intelligence/frontend/` (`npm install`)

---

## Port Assignments

| Service | Port |
|---------|------|
| Flask (ISM + News) | 5000 |
| FastAPI (PI backend) | 8000 |
| Next.js (PI frontend) | 3100 |

---

## Environment Files

Each service reads its own environment file:

| File | Used By |
|------|---------|
| `.env` (repo root) | Flask app -- database URLs, API keys, OAuth credentials, `PORTFOLIO_INTELLIGENCE_URL` |
| `portfolio_intelligence/backend/.env` | PI FastAPI backend -- database URLs, API keys, Redis URL |
| `portfolio_intelligence/frontend/.env.local` | PI Next.js frontend -- API base URL, auth configuration |

---

## Usage

Start all services from the repository root:

```bash
honcho start -f Procfile.dev
```

Stop all services:

```
Ctrl+C
```

Honcho sends SIGTERM to all child processes, ensuring a clean shutdown.
