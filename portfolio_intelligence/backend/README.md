# Portfolio Intelligence Backend

FastAPI backend for Bloomberg Terminal-grade portfolio analytics with flexible market data providers.

## Features

- 🔐 TradeStation OAuth authentication (JWT-based)
- 📊 Multi-provider market data (TradeStation, AlphaVantage, Mock)
- 📈 Investor-grade analytics (returns, volatility, Sharpe ratio, max drawdown)
- 🎯 Return attribution analysis
- 📉 Benchmark comparison (vs SPY)
- ⚡ Async PostgreSQL with SQLAlchemy 2.0
- 🔄 Celery + Redis for background tasks
- 📅 Daily portfolio metrics calculation

## Quick Start

### 1. Install Dependencies

```bash
cd portfolio_intelligence/backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/portfolio_intelligence

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Market Data Provider (choose one)
MARKET_DATA_PROVIDER=mock  # Options: "tradestation", "alphavantage", "mock"

# For AlphaVantage (if MARKET_DATA_PROVIDER=alphavantage)
ALPHAVANTAGE_API_KEY=your_api_key_here

# For TradeStation (if MARKET_DATA_PROVIDER=tradestation or using OAuth)
TRADESTATION_CLIENT_ID=your_client_id
TRADESTATION_CLIENT_SECRET=your_client_secret
TRADESTATION_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback
```

### 3. Setup Database

```bash
# Run migrations
alembic upgrade head

# (Optional) Seed with test data
python -m scripts.seed_db --days 90
```

### 4. Start Services

**Backend API:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Celery Worker (for background tasks):**
```bash
celery -A app.celery_app worker --loglevel=info
```

**Celery Beat (for scheduled jobs):**
```bash
celery -A app.celery_app beat --loglevel=info
```

## Market Data Providers

### Mock Provider (Default for Development)

**Use case:** Testing, development, demos

```bash
MARKET_DATA_PROVIDER=mock
```

- No API keys needed
- Generates realistic synthetic data
- 10 pre-configured symbols (AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META, JPM, V, WMT)
- Configurable volatility and trends

### AlphaVantage Provider (Recommended for Production)

**Use case:** Real market data without brokerage integration

```bash
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_key_here
```

**Features:**
- ✅ 20+ years of historical data
- ✅ Real-time quotes (paid tier)
- ✅ Adjusted close prices (splits/dividends)
- ✅ Reliable, well-documented API

**Limitations:**
- ❌ Cannot sync account positions (not a brokerage)
- 💰 Free tier: 25 calls/day, Paid: ~$50/month

**Setup guide:** See [`docs/ALPHAVANTAGE_SETUP.md`](../docs/ALPHAVANTAGE_SETUP.md)

### TradeStation Provider (For Real Account Sync)

**Use case:** Live trading, real portfolio sync

```bash
MARKET_DATA_PROVIDER=tradestation
TRADESTATION_CLIENT_ID=your_client_id
TRADESTATION_CLIENT_SECRET=your_secret
```

**Features:**
- ✅ Automatic position sync from brokerage
- ✅ Real-time market data
- ✅ Trade execution capabilities

**Limitations:**
- 🔐 Requires approved TradeStation developer account
- 📝 OAuth approval process

### Hybrid Approach (Best of Both Worlds)

Use TradeStation for position sync + AlphaVantage for market data:

```bash
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_av_key

# Still configure TradeStation for OAuth
TRADESTATION_CLIENT_ID=your_ts_client_id
TRADESTATION_CLIENT_SECRET=your_ts_secret
```

**Benefits:**
- Real positions from brokerage
- Reliable market data from AlphaVantage
- Best reliability and performance

## API Endpoints

### Authentication

- `GET /api/v1/auth/login` - Start OAuth flow
- `GET /api/v1/auth/callback` - OAuth callback
- `GET /api/v1/auth/me` - Get current user

### Portfolios

- `GET /api/v1/portfolios` - List user's portfolios
- `POST /api/v1/portfolios` - Create portfolio
- `GET /api/v1/portfolios/{id}` - Get portfolio details
- `DELETE /api/v1/portfolios/{id}` - Delete portfolio
- `GET /api/v1/portfolios/{id}/holdings` - Get holdings with weights

### Portfolio Versions

- `POST /api/v1/portfolios/{id}/versions` - Create new version
- `GET /api/v1/portfolios/{id}/versions` - List versions

### Analytics

- `GET /api/v1/analytics/portfolios/{id}/performance` - Time series performance
- `GET /api/v1/analytics/portfolios/{id}/metrics/latest` - Latest metrics (NAV, returns, volatility, Sharpe)
- `GET /api/v1/analytics/portfolios/{id}/attribution` - Return attribution by position
- `GET /api/v1/analytics/portfolios/compare` - Compare multiple portfolios (vs benchmark)

### Instruments

- `GET /api/v1/instruments/search?q={query}` - Search instruments
- `GET /api/v1/instruments/{symbol}` - Get instrument details
- `GET /api/v1/instruments/{symbol}/prices` - Get price history

## Database Schema

### Core Tables

- **users** - User accounts (from OAuth)
- **portfolios** - Portfolio metadata
- **portfolio_versions** - Point-in-time portfolio snapshots
- **portfolio_positions** - Holdings within a version
- **instruments** - Security master (symbols, names, types)
- **prices_daily** - End-of-day OHLCV data
- **portfolio_metrics_daily** - Calculated portfolio metrics

### Key Relationships

```
users (1) ──→ (N) portfolios
portfolios (1) ──→ (N) portfolio_versions
portfolio_versions (1) ──→ (N) portfolio_positions
instruments (1) ──→ (N) prices_daily
portfolios (1) ──→ (N) portfolio_metrics_daily
```

## Analytics Engine

The `PortfolioAnalyticsEngine` calculates:

### Performance Metrics

- **NAV** - Net Asset Value (Σ quantity × price)
- **Returns** - 1D, MTD, YTD percentage returns
- **Volatility** - 30-day rolling standard deviation (annualized)
- **Max Drawdown** - Peak-to-trough decline
- **Sharpe Ratio** - Risk-adjusted returns (assuming 4.5% risk-free rate)

### Attribution Analysis

- **Position Contribution** = Weight × Position Return
- Identifies which holdings drove performance
- Sorted by contribution (largest impact first)

### Benchmark Comparison

- Default benchmark: SPY (S&P 500 ETF)
- **Alpha** = Portfolio Return - Benchmark Return
- Overlay charts for visual comparison

## Background Jobs (Celery)

### Daily Jobs (Scheduled via Celery Beat)

- **Update prices** - Fetch latest EOD data for all instruments
- **Calculate metrics** - Compute daily portfolio metrics
- **Sync positions** - Update holdings from brokerage (if TradeStation)

### On-Demand Jobs

- Portfolio creation/update
- Historical data backfill
- Attribution recalculation

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Code Quality

```bash
# Format code
black app/

# Lint
flake8 app/

# Type checking
mypy app/
```

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py          # OAuth endpoints
│   │       ├── portfolios.py    # Portfolio CRUD
│   │       ├── analytics.py     # Performance analytics
│   │       └── instruments.py   # Instrument search
│   ├── db/
│   │   └── database.py          # Async SQLAlchemy setup
│   ├── models/                  # SQLAlchemy models
│   ├── services/
│   │   ├── tradestation.py      # TradeStation client
│   │   ├── alphavantage.py      # AlphaVantage client
│   │   ├── mock_tradestation.py # Mock data client
│   │   └── analytics.py         # Analytics engine
│   ├── config.py                # Settings (Pydantic)
│   ├── dependencies.py          # FastAPI dependencies
│   ├── main.py                  # FastAPI app
│   └── celery_app.py            # Celery config
├── alembic/                     # Database migrations
├── scripts/
│   └── seed_db.py               # Database seeding
├── tests/                       # Unit tests
└── requirements.txt
```

## Deployment

### Environment Variables (Production)

```bash
# Database (use connection pooling for production)
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/portfolio_intelligence

# Redis
REDIS_URL=redis://prod-redis:6379/0

# Security (use strong keys!)
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Market Data
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_production_key

# CORS (adjust for your frontend domain)
FRONTEND_URL=https://your-frontend-domain.com
```

### Railway Deployment

1. Create new Railway project
2. Add PostgreSQL and Redis services
3. Deploy backend with auto-detected Dockerfile or Nixpacks
4. Set environment variables in Railway dashboard
5. Run migrations: `railway run alembic upgrade head`

## Troubleshooting

### Database Connection Issues

```bash
# Test connection
psql $DATABASE_URL

# Check SQLAlchemy URL format
# Must use: postgresql+asyncpg://... (not postgresql://)
```

### Celery Not Running

```bash
# Check Redis connection
redis-cli ping

# Verify Celery can connect
celery -A app.celery_app inspect ping
```

### Market Data Provider Issues

See provider-specific guides:
- Mock: Always works (no external dependencies)
- AlphaVantage: [`docs/ALPHAVANTAGE_SETUP.md`](../docs/ALPHAVANTAGE_SETUP.md)
- TradeStation: Verify OAuth credentials and API permissions

## Contributing

1. Create feature branch from `main`
2. Write tests for new features
3. Run code quality checks
4. Submit PR with clear description

## License

Proprietary - Envoy Financial Intelligence Suite

## Support

For issues or questions, contact the development team or open a GitHub issue.
