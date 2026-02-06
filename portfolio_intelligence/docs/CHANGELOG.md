# Changelog

All notable changes to the Portfolio Intelligence project are documented here.

---

## [Unreleased]

### In Progress
- Portfolio comparison UI (endpoint exists, frontend pending)
- Advanced Framer Motion animations (basic animations complete)

---

## [2024-02-06] - Automatic Daily Price Refresh

### Added
- **APScheduler integration** for automatic daily price updates
  - Runs nightly at 6 PM ET (18:00 US/Eastern)
  - Works with AlphaVantage and Mock providers (no OAuth required)
  - Fetches latest close prices for all active portfolio symbols
  - Configurable via `ENABLE_NIGHTLY_UPDATES` environment variable

- **Updated nightly_price_update Celery task**
  - Now fully functional with AlphaVantage/Mock providers
  - Automatically updates all symbols in all portfolios
  - Returns detailed status (symbols updated, failed symbols, provider used)
  - Skips TradeStation (requires user OAuth, not suitable for automated jobs)

### Changed
- **FastAPI lifespan** now starts APScheduler on startup
  - Only enables scheduler if `ENABLE_NIGHTLY_UPDATES=true`
  - Only enables scheduler for AlphaVantage or Mock providers
  - Logs clear warnings if disabled or incompatible provider

### Configuration
- New environment variable: `ENABLE_NIGHTLY_UPDATES` (default: `true`)
- Scheduler timezone: US/Eastern (6 PM ET = after market close)

### Notes
- **Production ready**: Portfolios now auto-update overnight without manual intervention
- **TradeStation limitation**: Real TradeStation API requires user OAuth tokens, so automated updates are not supported. Use AlphaVantage for production deployments requiring automatic updates.

---

## [2024-02-06] - Attribution Fixes & Allocation Type Enforcement

### Added
- **Attribution display improvements**
  - Column headers now explicitly show units: "Avg Weight (%)", "Asset Return (%)", "Contribution (pp)"
  - Smart key driver logic handles edge cases (>100% contribution, negative returns, normal cases)
  - Breakdown calculation showing how contributions add up (e.g., "STLA (+564pp) + Others (-2.6pp) = Net (+561pp)")
  - Percentage points (pp) notation to eliminate confusion with percentages

- **Portfolio-level allocation type enforcement**
  - Moved `allocation_type` from position level to portfolio level
  - All positions in a portfolio now inherit the same allocation type
  - Cannot mix weight and quantity modes within a single portfolio
  - Database migration: `4f1d797939a2_add_allocation_type_to_portfolio.py`

- **Dynamic date handling**
  - Portfolio creation now finds earliest date where ALL symbols have complete price data
  - Sets `version.effective_at` to that date (no hardcoded lookbacks)
  - Price refresh calculates days from portfolio start to today dynamically
  - Works correctly for portfolios created today, tomorrow, or any future date

### Fixed
- **OAuth redirect loop** (clicking "Connect with TradeStation" 4 times to reach dashboard)
  - Replaced `useState` with `useRef` in callback handler
  - Fixed double-rendering in auth provider (React Strict Mode)
  - `frontend/src/app/auth/callback/page.tsx`
  - `frontend/src/providers/auth-provider.tsx`

- **Attribution calculations for quantity-based portfolios**
  - Was showing nonsensical percentages (77,700% weights, 601,260% returns)
  - Now correctly calculates market values and actual portfolio weights
  - Fixed in `app/services/analytics.py::get_contribution_by_holding()`

- **Portfolio metrics showing 72,673% daily returns**
  - Caused by portfolio effective_at being set to today with 90 days of price data
  - Fixed by dynamic effective_at calculation

- **Missing allocation_type in PortfolioRead response**
  - Added `allocation_type=portfolio.allocation_type` to response in `create_portfolio` endpoint
  - `app/api/v1/portfolios.py` line 147

- **Frontend features not visible**
  - Conditional rendering was hiding all features due to missing/null data
  - Fixed by ensuring complete price data from portfolio start

### Changed
- **Analytics engine now reads allocation_type from portfolio level**
  - `app/services/analytics.py::compute_daily_metrics()`
  - `app/services/analytics.py::get_contribution_by_holding()`
  - Properly handles both weight-based and quantity-based portfolios

- **Frontend attribution section complete rewrite**
  - `frontend/src/app/portfolios/[id]/page.tsx` (attribution section)
  - Added proper column headers with units
  - Implemented three-case key driver logic
  - Added breakdown calculation for transparency

### Documentation
- Updated `docs/tdd.md`:
  - Section 5: Added allocation_type to portfolios table schema
  - Section 5: Updated portfolio_positions notes to clarify inheritance
  - Section 7.1: Added dynamic effective_at and refresh calculations

- Updated `docs/prd.md`:
  - Journey 2: Added implementation status and allocation type details
  - Journey 3: Expanded with all implemented features and attribution improvements
  - Section 8: Added completed features, in-progress items, and known issues resolved

---

## [2024-02-06] - AlphaVantage Integration

### Added
- **AlphaVantage market data provider**
  - Full adapter implementing TradeStation interface
  - `app/services/alphavantage.py` - AlphaVantageClient and AlphaVantageAdapter
  - Supports daily bars, quotes, intraday data
  - Rate limit handling (free tier: 5 calls/min, paid tier: higher limits)
  - Environment variable: `MARKET_DATA_PROVIDER=alphavantage`

- **Factory pattern for data providers**
  - Separated OAuth client from market data client
  - `get_auth_client()` - Always returns TradeStation or Mock for OAuth
  - `get_tradestation_client()` - Returns provider based on MARKET_DATA_PROVIDER setting
  - Supports: "tradestation", "alphavantage", "mock"

- **Comprehensive documentation**
  - `docs/ALPHAVANTAGE_SETUP.md` - Complete setup and usage guide
  - Configuration examples for pure AlphaVantage and hybrid modes
  - Rate limit recommendations and troubleshooting

### Changed
- **API endpoints now use provider-agnostic client**
  - `app/dependencies.py` - Dual client functions
  - All market data calls go through factory pattern
  - OAuth operations isolated from market data operations

### Fixed
- `AttributeError: 'AlphaVantageAdapter' object has no attribute 'build_auth_url'`
  - OAuth endpoints now use `get_auth_client()` instead of `get_tradestation_client()`
  - Separation of concerns: auth vs market data

---

## Project Status

### Production Ready ✅
- OAuth authentication (TradeStation + Mock)
- Portfolio CRUD operations
- Version management with snapshots
- Daily price ingestion (TradeStation, AlphaVantage, Mock)
- Analytics engine (NAV, returns, volatility, drawdown)
- Return attribution with proper calculations
- Holdings with weights and market values
- Benchmark comparison (SPY)
- Frontend dashboard with all investor-grade features

### Testing Phase 🧪
- Multi-portfolio comparison UI
- Advanced animations

### Future Roadmap 🗺️
- AI insights ("What changed mattered most?")
- Scenario modeling
- Benchmark attribution (beyond simple SPY overlay)
- Factor exposure visualization
- Portfolio optimization suggestions

---

## Migration Notes

### Database Migrations Applied
1. `4f1d797939a2_add_allocation_type_to_portfolio.py` (2024-02-06)
   - Adds `allocation_type` column to `portfolios` table
   - Migrates existing data from position-level to portfolio-level
   - Sets NOT NULL constraint with default 'quantity'

### Breaking Changes
- **Allocation type is now portfolio-level** (not position-level)
  - API clients must send `allocation_type` in `POST /portfolios` (PortfolioCreate schema)
  - API clients should NOT send `allocation_type` per position (removed from PositionCreate schema)
  - Existing portfolios migrated automatically

---

## Contributors
- Claude Sonnet 4.5 (AI Assistant)
- Roberto Buso-Garcia (Product Owner)

---

## References
- PRD: `docs/prd.md`
- TDD: `docs/tdd.md`
- Design Tokens: `docs/design-tokens.md`
- AlphaVantage Setup: `docs/ALPHAVANTAGE_SETUP.md`
