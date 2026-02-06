# Phase 3 - Next.js Frontend

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Portfolio Intelligence

---

## Overview

Built the Next.js 14 frontend with TypeScript, providing TradeStation OAuth authentication, portfolio creation with allocation mode selection, and an interactive performance dashboard. The frontend communicates with the FastAPI backend via a typed API client and runs as a separate service on port 3100 in development.

---

## Technical Implementation

### Project Setup

Initialized with `create-next-app@14` using the following options: TypeScript, Tailwind CSS, ESLint, App Router (no `src/` directory -- uses `src/` convention).

**Dependencies**:

| Package | Purpose |
|---------|---------|
| `@tanstack/react-query` | Server state management, caching, mutations |
| `framer-motion` | Animations for position list, weight bar, page transitions |
| `recharts` | AreaChart for portfolio performance visualization |
| `lucide-react` | Icon library (consistent, tree-shakeable) |

**Tailwind Configuration** -- Extends the default theme with design tokens from `portfolio_intelligence/docs/design-tokens.md`:

- Custom colors: `navy` (`#1E3A5F`), `sky-accent` (`#38BDF8`)
- Font family: Inter via Google Fonts
- Border radius: 8px default

### Core Infrastructure

**`src/lib/api.ts`** -- API client.

- Wraps `fetch` with automatic JWT injection from localStorage.
- Adds `Authorization: Bearer <token>` header to all requests.
- On 401 response: clears stored token and redirects to `/login`.
- Base URL configured via `NEXT_PUBLIC_API_URL` environment variable.

**`src/lib/types.ts`** -- TypeScript interfaces.

- Mirrors backend Pydantic schemas: `User`, `Portfolio`, `PortfolioVersion`, `Position`, `Instrument`, `PerformancePoint`, `PortfolioMetrics`.
- Ensures type safety across the frontend.

**`src/providers/auth-provider.tsx`** -- Authentication context.

- React context providing: `user`, `isAuthenticated`, `isLoading`, `login()`, `logout()`.
- Stores JWT in localStorage. On mount, validates the stored token by calling `/auth/me`.
- `logout()` clears localStorage and redirects to `/login`.

**`src/providers/query-provider.tsx`** -- TanStack Query provider.

- `QueryClientProvider` wrapping the application.
- Default `staleTime` of 5 minutes to reduce redundant API calls.

### Layout

**`src/app/layout.tsx`** -- Root layout.

- Wraps all pages with `QueryProvider` and `AuthProvider`.
- Renders the shared `Header` component.
- Applies Inter font globally via `next/font/google`.

**`src/components/layout/header.tsx`** -- Navigation header.

- Links to Suite Home, ISM Analysis, and News Analysis use `NEXT_PUBLIC_SUITE_URL` as the base URL (external navigation to the Flask app).
- Portfolio Intelligence link is an internal Next.js `Link` component.
- Displays user email and logout button when authenticated.
- Responsive: collapses to hamburger menu on mobile.

### Auth Pages

**`src/app/login/page.tsx`** -- Login page.

- "Connect with TradeStation" primary button that redirects to the backend's `/auth/login` endpoint.
- Trust badges: "Read-only access" and "No trades executed" to reassure users about OAuth scopes.
- Redirects to home page if already authenticated.

**`src/app/auth/callback/page.tsx`** -- OAuth callback handler.

- Extracts JWT token from URL query parameters (set by the backend callback redirect).
- Stores the token in localStorage.
- Redirects to the home page.
- Wrapped in React `Suspense` boundary (required by Next.js 14 for `useSearchParams`).
- Shows a loading spinner during the token exchange.

### Portfolio Creation

**`src/app/portfolios/new/page.tsx`** -- Portfolio creation form.

**Form Fields**:

| Field | Type | Details |
|-------|------|---------|
| Name | Text input | Required, max 100 characters |
| Description | Textarea | Optional |
| Allocation Mode | Toggle | "Weight (%)" or "Quantity (shares)" -- sets the portfolio's allocation_type |
| Holdings | Dynamic list | Add/remove rows. Each row: symbol (text input), weight or quantity (number input) |

**Interactions**:

- **Add Holding** button appends a new empty row with Framer Motion `AnimatePresence` enter animation.
- **Remove Holding** button on each row triggers exit animation.
- **Animated Weight Bar** -- For weight-mode portfolios, a horizontal bar fills proportionally as weights are entered. Changes animate smoothly.
- **Weight Warning Badge** -- Appears when total weight does not equal 100%, showing the current sum.
- **Submit** -- Uses TanStack Query `useMutation`. On success, redirects to the new portfolio's overview page.

### Portfolio Overview

**`src/app/portfolios/[id]/page.tsx`** -- Portfolio detail page.

**Performance Header**:
- Current NAV value (large text).
- Total return percentage with color coding (green for positive, red for negative).

**Time Range Selector**:
- Buttons for 1M, 3M, YTD, 1Y, All.
- Selecting a range re-fetches the performance series via TanStack Query with the corresponding date filter.

**Performance Chart**:
- Recharts `AreaChart` with gradient fill (navy to transparent).
- Responsive container that fills available width.
- Tooltip showing date and NAV value on hover.
- X-axis: dates. Y-axis: NAV value with auto-scaling.

**Holdings Table**:
- Columns: Symbol, Weight/Quantity (depending on allocation mode).
- Currently displays the data available from the portfolio version. Further enrichment (last price, 30-day change, sparkline, contribution) is planned for a future phase.

### Home Page

**`src/app/page.tsx`** -- Application home page with 3 states:

1. **Loading** -- Skeleton cards with pulse animation while auth state resolves.
2. **Unauthenticated** -- Hero section with "Connect with TradeStation" CTA button.
3. **Authenticated** -- Portfolio grid displaying cards for each portfolio. Each card shows: name, description (truncated), allocation mode badge, position count. Click navigates to the portfolio overview page. If no portfolios exist, displays an empty-state card with "Create Your First Portfolio" CTA linking to `/portfolios/new`.

### Security Note

JWT storage in localStorage is a conscious MVP tradeoff. The risks are mitigated by:

- Short-lived JWT tokens (15-minute expiry).
- Refresh token rotation on each use.
- No sensitive financial operations (read-only TradeStation access, no trade execution).

The upgrade path to HTTP-only cookies is documented and scheduled for Phase 4, prior to production deployment.

---

## Testing

Verified all pages render correctly in development. Auth flow tested end-to-end with mock JWT tokens. Portfolio creation form validates inputs and submits successfully. Performance chart renders with sample data. Responsive layout confirmed on desktop and mobile viewports. Full end-to-end testing with real TradeStation OAuth is blocked pending developer credentials.
