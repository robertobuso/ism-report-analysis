Below is a **full Product Requirements Document (PRD)** with **heavy emphasis on user journeys, UX quality, and design excellence**, written at the level you’d expect for a serious, premium financial product — not a scrappy internal tool.

This assumes:

* **Single sophisticated investor initially**
* **High trust / high polish**
* **Design is a feature**
* **Scales to multi-portfolio, multi-year analytics**

---

# Product Requirements Document (PRD)

**Product Name (Working):** Portfolio Intelligence
**Audience:** Semi-serious to serious individual investors
**Primary Value:** Replace fragmented, manual portfolio research with a persistent, beautiful, analytical workspace

---

## 1. Product Vision

**Portfolio Intelligence** is a calm, precise, and trustworthy portfolio analytics workspace.

It allows an investor to:

* Define portfolios intentionally
* Observe how they evolve over time
* Understand performance, risk, and trends visually
* Compare strategies and changes
* Build conviction — without spreadsheets, tabs, or mental overhead

The product should feel:

* **Quietly powerful**
* **Institutional in rigor**
* **Consumer-grade in polish**

No noise. No clutter. No “trading dopamine.”

---

## 2. Design Principles (Non-Negotiable)

1. **Clarity over density**
   Every screen answers one primary question.

2. **Progressive disclosure**
   Surface insights only when the user asks for them.

3. **Time as a first-class dimension**
   Every view respects that portfolios change.

4. **Motion communicates state**
   Animations explain transitions, not decorate them.

5. **Trust through restraint**
   Conservative typography, restrained color, precise numbers.

---

## 3. Target User

### Primary Persona

**Experienced self-directed investor**

* Invests for years
* Maintains multiple conceptual portfolios
* Cares about strategy, not day trading
* Currently uses:

  * brokerage UI
  * spreadsheets
  * ad-hoc research

### Key Pain Points

* Manual aggregation
* No historical memory of portfolio decisions
* Hard to compare “what I changed” vs outcomes
* Broker tools optimize for trading, not thinking

---

## 4. Core User Journeys

---

## Journey 1: First-Time Entry (Trust Establishment)

### Goal

User understands what the product does **without friction** and feels safe connecting data.

### Flow

1. **Landing → OAuth Connection**

   * Clear explanation:

     * “Read-only”
     * “No trades”
     * “Your data stays yours”
2. **Post-auth empty state**

   * Elegant onboarding message:

     > “Let’s define your first portfolio.”

### UX Requirements

* Calm loading transitions
* Skeleton states instead of spinners
* Micro-copy explaining what’s happening

---

## Journey 2: Create a Portfolio (Intentional Setup)

### Goal

User defines a portfolio as a **concept**, not a transaction.

### Flow

1. Create Portfolio

   * Name
   * Optional description ("Long-term growth", "Dividend focus")
   * **Allocation mode** — chosen **per-portfolio** (not per-position):
     * **Weight mode:** each holding has a target weight (percentage)
     * **Quantity mode:** each holding has a share quantity
     * **Once set, this cannot be changed** — ensures consistency across portfolio history
2. Add holdings

   * Type ticker
   * Autocomplete with logo + name
   * Enter value (weight % or share quantity, based on portfolio allocation mode)
3. Save → creates **Version 1**
   * System automatically sets effective_at to earliest date where ALL symbols have complete price data
   * Ensures analytics work from day one without hardcoded dates

### UX Requirements

* Inline validation
* Soft animations when adding/removing holdings
* **Weight/quantity toggle** at portfolio level — clearly communicates which mode is active
* Weight bar visualization updating live (weight mode)
* Subtle warning if weights ≠ 100% (weight mode only)

### Implementation Status

✅ **Completed (2024-02-06)**
- Portfolio-level allocation type enforcement
- Dynamic effective_at calculation based on available data
- Automatic price fetching for new symbols (90 days lookback)

---

## Journey 3: Portfolio Overview (Daily Home)

### Goal

User instantly understands **how the portfolio is doing**.

### Primary Screen

**Portfolio Dashboard**

### Key Elements

1. **Performance Header**

   * NAV
   * Total return
   * Time range selector (1M / YTD / 1Y / All)
   * Smooth animated chart transitions

2. **Key Metrics Cards**

   * Current NAV with YTD return
   * 30-Day Volatility (annualized)
   * Max Drawdown (peak to trough)
   * Sharpe Ratio (with quality indicator)

3. **Return Attribution Section**

   * Clear column headers with units:
     * "Avg Weight (%)"
     * "Asset Return (%)"
     * "Contribution (pp)" ← percentage points notation
   * Visual contribution bars (positive/negative)
   * **Key Driver Analysis** with accurate language:
     * Handles edge cases (>100% contribution, negative returns)
     * Shows breakdown calculation for transparency
     * Example: "STLA (+564pp) + Others (-2.6pp) = Net (+561pp)"

4. **Holdings Table**

   * Symbol, quantity, price, market value
   * Portfolio weight percentage with visual bars
   * Sorted by market value (largest first)

5. **Benchmark Comparison** (SPY)

   * Overlay chart showing portfolio vs benchmark
   * Relative performance indicator

### UX Requirements

* Chart animations on range change
* Hover reveals additional context
* No full page reloads
* State preserved across navigation
* Conditional rendering based on data availability
* Graceful loading states with skeletons

### Implementation Status

✅ **Completed (2024-02-06)**
- All metrics cards with proper calculations
- Attribution with percentage points (pp) notation
- Smart key driver logic handling edge cases
- Holdings table with weights and market values
- Benchmark comparison (SPY integration)
- Refresh data button with background processing
- Delete portfolio with confirmation modal

---

## Journey 4: Portfolio History (Time Awareness)

### Goal

User understands **how decisions evolved**.

### Flow

1. Open “Versions”
2. Timeline view:

   * Version markers
   * Notes (“Reduced tech exposure”)
3. Click a version → snapshot view

### UX Requirements

* Horizontal timeline with motion
* Diff highlighting between versions
* “This change resulted in…” messaging (future AI hook)

---

## Journey 5: Comparison (Strategic Thinking)

### Goal

User compares strategies without mental gymnastics.

### Flow

1. Select 2–3 portfolios
2. Choose date range
3. View:

   * Overlay performance chart
   * Risk vs return scatter
   * Correlation heatmap

### UX Requirements

* Color-consistent portfolio identity
* Animated chart layering
* Toggle metrics without losing context

---

## Journey 6: Edit Portfolio (Without Losing History)

### Goal

User changes strategy confidently.

### Flow

1. “Edit Portfolio”
2. UI clearly says:

   > “This creates a new version”
3. Make changes
4. Save → Version N+1

### UX Requirements

* Version diff preview before saving
* Explicit “effective date”
* Gentle confirmation animation

---

## 5. UI / UX Tech Stack (Modern, Elegant, Scalable)

### Framework

* **Next.js 14**
* **React 18**
* **TypeScript 5**

### Rendering Strategy

Authenticated pages use **client-side data fetching** via TanStack Query, but retain Next.js App Router **layouts** for structure, navigation, and page transitions. Shell UI (nav, sidebar, skeletons) is server-rendered for instant paint; data is fetched client-side after auth.

### Styling

* **Tailwind CSS**
* Design tokens for:

  * spacing
  * typography
  * color
* Dark mode ready (future)

### Animation

* **Framer Motion**

  * Page transitions
  * Chart state changes
  * Timeline animations

### Data & State

* **TanStack Query**
* Optimistic updates
* Background refetching
* Caching by portfolio/version

### Charts

* **Recharts**
* Custom theming
* Canvas-based for performance

### Icons

* **Lucide**
* Minimal, consistent stroke weight

---

## 6. Visual Language

### Typography

* Inter / Source Sans 3
* Numerical alignment for financial data
* Tabular numerals

### Color

* Neutral base
* Muted accent per portfolio
* Red/green used sparingly and consistently

### Layout

* Card-based
* Generous whitespace
* Clear visual hierarchy

---

## 7. Non-Functional UX Requirements

* <200ms UI interactions
* No blocking spinners
* Graceful loading skeletons
* Offline-safe navigation
* Accessibility AA minimum

---

## 8. MVP Scope (Design-First)

### Completed Features ✅

* **OAuth flow** - TradeStation integration with mock mode support
* **Market Data Integration** - AlphaVantage, TradeStation, and Mock providers
* **Portfolio creation** - With dynamic effective_at and allocation type enforcement
* **Portfolio versioning** - Create new versions with historical snapshots
* **Performance visualization** - NAV charts with time range selection (1M/YTD/1Y/All)
* **Key Metrics** - NAV, volatility, drawdown, Sharpe ratio
* **Return Attribution** - Contribution analysis with percentage points notation
* **Holdings Management** - Add/remove positions, view weights and market values
* **Benchmark Comparison** - SPY integration with overlay charts
* **Price Refresh** - Manual refresh with background processing
* **Automatic Daily Updates** - Scheduled nightly price refresh at 6 PM ET (AlphaVantage/Mock)
* **Delete Portfolio** - With confirmation modal

### In Progress 🚧

* Polished animations (basic animations complete, advanced Framer Motion integration pending)
* Portfolio comparison view (comparison endpoint exists, UI pending)

### Excluded (Explicit) ❌

* Trading
* Alerts
* News feeds
* Social features

### Known Issues & Tech Debt

* **React Strict Mode conflicts** - Resolved with useRef pattern (2024-02-06)
* **Attribution calculations for quantity portfolios** - Fixed (2024-02-06)
* **Hardcoded date lookbacks** - Removed, now fully dynamic (2024-02-06)
* **Missing allocation_type in responses** - Fixed (2024-02-06)

---

## 9. Success Criteria

* User stops using spreadsheets
* User returns weekly
* User can explain *why* a portfolio performed a certain way
* User trusts the numbers

---

## 10. Future-Facing Hooks (Not Implemented Yet)

* AI insights (“What changed mattered most?”)
* Scenario modeling
* Benchmark attribution
* Factor exposure visualization

---

## Final Note (Important)

This product should feel like:

> **“A private investment research terminal — not a brokerage UI.”**

