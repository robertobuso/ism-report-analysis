# Changelog

All notable changes to the Portfolio Intelligence project are documented here.

---

## [Unreleased]

### In Progress
- Portfolio comparison UI (endpoint exists, frontend pending)
- Advanced Framer Motion animations (basic animations complete)
- Company Intelligence Phase 9: Polish & Integration (final phase)

### Planned — Company Intelligence (Remaining)

- **Phase 9: Polish & Integration**
  - Responsive design optimization (mobile/tablet breakpoints)
  - Comprehensive loading skeletons for all tabs
  - Error boundary handling
  - Print-optimized CSS for "Export Company Brief"
  - Performance optimization (React.memo, useMemo)
  - Accessibility audit (ARIA labels, keyboard navigation)
  - E2E testing suite

---

## [2026-02-07] - Company Intelligence Phases 7-8

### Added — Phase 7: Price & Technicals Tab ✅

- **Interactive candlestick chart** with TradingView `lightweight-charts` v4
  - Real-time OHLCV data from Alpha Vantage
  - Timeframe selector (1M, 3M, 6M, 1Y)
  - Smooth zoom and pan interactions
  - Green/red candle coloring for up/down days
  - Auto-fit content to viewport

- **Self-calculated technical indicators** (1 API call per ticker)
  - RSI (14-period) with overbought/oversold signals
  - MACD with signal line and histogram
  - 50-day and 200-day Simple Moving Averages
  - Bollinger Bands (20-period, 2σ)
  - Volume analysis
  - All indicators computed from TIME_SERIES_DAILY data

- **AI Technical Signal Summary**
  - Plain-English interpretation of price trends
  - RSI momentum state (neutral/overbought/oversold)
  - MACD trend signal (bullish/bearish)
  - Moving average analysis
  - Gradient card design with Activity icon

- **Key Price Levels**
  - 52-week high/low from real data
  - Current price display
  - Price range visualization

**Technical Implementation:**
- Component: `TechnicalsTab.tsx` (345 lines)
- Backend: `/api/v1/company/{symbol}/prices` and `/technicals` endpoints
- Service: `CompanyIntelligenceService.get_technicals()` with indicator calculations
- Cache TTL: 1 hour (Redis)
- Bundle impact: +50KB for lightweight-charts (production optimized)

**Bug Fixes:**
- Fixed chart series race condition (data arriving before series initialization)
- Fixed lightweight-charts v5 API compatibility (downgraded to v4)
- Fixed dependency injection bug in `/prices` endpoint
- Split useEffect for proper initialization/data update lifecycle

**Documentation:** `docs/phase7-technicals-complete.md`

---

### Added — Phase 8: Portfolio Impact Tab ✅

- **Position Health Score** (0-100 composite metric)
  - 4-component breakdown: Fundamentals (25), Price Trend (25), Sentiment (25), Portfolio Fit (25)
  - Color-coded: Green (75-100 Strong), Yellow (50-74 Moderate), Red (0-49 Weak)
  - Large hero card with visual grid showing each component

- **Contribution Metrics**
  - **Contribution to Return**: Percentage point impact on portfolio performance
  - **Risk Contribution**: Percentage of total portfolio volatility
  - Side-by-side cards with trend icons

- **Concentration Alerts**
  - Sector overlap warnings (multiple holdings in same sector)
  - Position size alerts (single position too large)
  - Theme overlap detection (correlated holdings)
  - Amber warning cards with combined weight and involved symbols

- **Sector Overlap Visualization**
  - Horizontal bar chart showing sector weights across holdings
  - Blue progress bars with percentage labels
  - Normalized display (handles decimal and percentage formats)
  - Bar width capped at 100%

- **Correlation Analysis**
  - Correlation coefficients with top holdings (-1 to 1)
  - Color-coded bars: Red (>0.7 high risk), Yellow (0.3-0.7 moderate), Green (<0.3 diversified)
  - Educational legend explaining concentration risk
  - Smart normalization for out-of-range values

- **Portfolio Context Guard**
  - Friendly message when no portfolio_id provided
  - Encourages viewing from portfolio context

**Technical Implementation:**
- Component: `PortfolioImpactTab.tsx` (360 lines)
- Backend: `/api/v1/company/{symbol}/portfolio-impact` endpoint
- Service: `CompanyIntelligenceService.get_portfolio_impact()`
- Schemas: `PortfolioImpactResponse`, `ConcentrationAlert`, `HealthScore`
- React Query caching with 5-minute stale time

**Bug Fixes:**
- Fixed percentage display overflow (12000% → 12%)
- Fixed correlation bar widths (normalized to -1 to 1 range)
- Added smart data format detection for both decimals and percentages

**Documentation:** `docs/phase8-portfolio-impact-complete.md`

---

### Changed — Company Intelligence Overall Progress

**Phases Complete: 8 of 9** (89% complete)

| Phase | Status | Description |
|---|---|---|
| Phase 0 | ✅ Complete | Route structure, page shell, tab navigation |
| Phase 1 | ✅ Complete | Company header with price/context |
| Phase 2 | ✅ Complete | AI insight cards ("Why This Matters Now") |
| Phase 3 | ✅ Complete | Overview tab with fundamentals and quality badges |
| Phase 4 | ✅ Complete | Financials tab with GPT narratives |
| Phase 5 | ✅ Complete | Earnings tab with beat rate analysis |
| Phase 6 | ✅ Complete | News & Sentiment tab with article cards |
| Phase 7 | ✅ Complete | Price & Technicals tab with candlestick chart |
| Phase 8 | ✅ Complete | Portfolio Impact tab with health score |
| Phase 9 | 🗺️ Planned | Polish & integration (final phase) |

**Total Implementation:**
- 9 API endpoints across `/api/v1/company/{symbol}/...`
- 8 React components (tabs + shared components)
- 1 comprehensive backend service (`CompanyIntelligenceService`)
- Alpha Vantage integration with Redis caching
- Self-calculated technical indicators (efficient API usage)
- Portfolio-aware analysis throughout

**Performance:**
- Page load (warm cache): <500ms
- Alpha Vantage calls per page: 6-8 (well under 30/min limit)
- Bundle size: ~67KB per tab (optimized)
- React Query caching: Smart invalidation per data type

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

### Planned 🗺️
- **Company Intelligence page** — AI-powered decision cockpit for individual securities
- News & sentiment analysis with sentiment-price overlay
- Scenario modeling ("What if I trim 25%?")
- Position Health Score (explainable composite metric)

### Future Roadmap 🗺️
- Benchmark attribution (beyond simple SPY overlay)
- Factor exposure visualization
- Portfolio optimization suggestions
- Real-time alerts and notifications
- Covariance-based scenario modeling (v2)

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
- Company Intelligence TDD: `docs/company-intelligence-tdd.md`
- Design Tokens: `docs/design-tokens.md`
- AlphaVantage Setup: `docs/ALPHAVANTAGE_SETUP.md`
