# UI/UX Consolidation Plan: Unifying the Envoy Financial Intelligence Suite

> **ARCHIVED**: 2026-02-06 — Phases 3-7 completed. See [Implementation Doc](../implementations/2026-02-06-ui-ux-consolidation.md) for results. Phases 1-2 were completed earlier.

> **Goal**: Make the Flask app (ISM Analysis, News Analysis) visually match the Portfolio Intelligence (PI) Next.js frontend so the entire suite feels like one cohesive product.

> **Design Principle**: "Same brand, different vintage" — shared visual DNA, tool-specific accents.

---

## Current State Assessment

### Portfolio Intelligence (Target Design)
- **Framework**: Next.js + Tailwind CSS with custom design tokens
- **Nav**: White bg, `shadow-subtle`, Lucide icons (16px), clean `text-sm font-medium` links, active = `border-b-2 border-primary`
- **Cards**: `bg-white rounded-card(16px) shadow-card p-5/p-6`, hover = `-translate-y-0.5 shadow-hover`
- **Buttons**: `bg-primary text-white rounded-button(8px) font-semibold`, border-style for secondary
- **Inputs**: `border border-gray-200 rounded-button px-4 py-2.5`, focus = `ring-2 ring-primary/20`
- **Typography**: Inter, `text-sm` nav, tight letter-spacing, `tabular-nums` for numbers
- **Motion**: 0.3s ease, subtle translateY hover lifts, Framer Motion for lists
- **Loading**: `animate-pulse` skeleton rectangles (not spinners)

### Flask App (Current State — Gaps)
| Area | Gap Description |
|------|----------------|
| **CSS Architecture** | No external CSS file — all styles inline in `<style>` blocks per template, duplicated `:root` vars |
| **Navigation** | `news_simple.html` overrides navbar with purple gradient; inconsistent with PI |
| **News Form** | Full gradient background (`#667eea → #764ba2`), frosted glass card, Font Awesome icons — looks like a different app |
| **News Results** | Gradient header card, `backdrop-filter`, inconsistent badge system, different color palette |
| **Monitoring Dashboard** | Gradient metric cards, doesn't match design tokens |
| **ISM Dashboard** | ~3900 lines, heavy inline CSS, redeclares `:root` vars, custom tab/heatmap styling |
| **Upload/Index** | Redeclares `:root` vars and navbar styles already in base.html |
| **Landing Page** | Standalone (not extending base.html), ISM-only branding, different btn hover color (`#004494` vs `#10104D`) |
| **Results Page** | Standalone (not extending base.html), raw spinner animation, no design system |
| **Icons** | Bootstrap Icons in base/suite/dashboard, Font Awesome in news pages — should be Lucide for PI parity |
| **Loading States** | Spinners everywhere — PI uses skeleton pulse animations |

---

## Implementation Plan

### Phase 1: Design System CSS Foundation

**Create `static/css/design-system.css`** — the single source of truth for all Flask visual styling.

**1.1 CSS Custom Properties (matching PI's `tailwind.config.ts` exactly)**
```css
:root {
  /* Brand */
  --color-primary: #191970;
  --color-primary-hover: #10104D;

  /* Surfaces */
  --color-background: #f8fafc;
  --color-foreground: #333333;
  --color-muted: #6c757d;
  --color-border: #e2e8f0;
  --color-border-light: #f0f0f0;

  /* Tool Accents */
  --color-accent-green: #28a745;
  --color-accent-red: #dc3545;
  --color-accent-blue: #3b82f6;
  --color-accent-purple: #764ba2;
  --color-accent-warning: #ffc107;

  /* Semantic (ISM-specific) */
  --color-growing: #34A853;
  --color-contracting: #EA4335;

  /* Shadows (matching PI exactly) */
  --shadow-subtle: 0 2px 10px rgba(0, 0, 0, 0.05);
  --shadow-card: 0 4px 20px rgba(0, 0, 0, 0.05);
  --shadow-hover: 0 8px 30px rgba(0, 0, 0, 0.1);
  --shadow-hero: 0 10px 30px rgba(0, 86, 179, 0.08);

  /* Radius (matching PI exactly) */
  --radius-card: 16px;
  --radius-button: 8px;
  --radius-badge: 20px;

  /* Typography */
  --font-sans: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
  --letter-spacing-body: -0.01em;
  --letter-spacing-heading: -0.02em;

  /* Transitions */
  --transition-default: all 0.3s ease;
  --transition-fast: all 0.15s ease;
}
```

**1.2 Component Classes** (prefixed `ds-` to avoid Bootstrap conflicts)

| Class | Purpose | Matches PI Pattern |
|-------|---------|-------------------|
| `.ds-card` | Base card: white bg, card radius, card shadow, padding | `bg-white rounded-card shadow-card p-5` |
| `.ds-card-hover` | Add hover lift + shadow increase | `hover:shadow-hover hover:-translate-y-0.5` |
| `.ds-card-accent-{color}` | 4px top border in accent color | Tool card pattern |
| `.ds-btn-primary` | Primary button matching PI | `bg-primary text-white rounded-button font-semibold` |
| `.ds-btn-secondary` | Secondary/outline button | `border border-gray-200 text-muted` |
| `.ds-input` | Form input styling | `border border-gray-200 rounded-button px-4 py-2.5` |
| `.ds-select` | Select dropdown styling | Same as input |
| `.ds-badge` | Pill badge base | `rounded-badge text-xs font-semibold` |
| `.ds-badge-{color}` | Colored badge variants | Per-tool colors |
| `.ds-table` | Table with PI styling | Subtle borders, hover rows, muted headers |
| `.ds-page-title` | Page title typography | `text-2xl font-bold letter-spacing-heading` |
| `.ds-section-title` | Section header | `text-xl font-bold` |
| `.ds-muted` | Muted text | `text-muted text-sm` |
| `.ds-skeleton` | Pulse loading placeholder | `animate-pulse bg-gray-200 rounded` |
| `.ds-kpi-card` | KPI display card | Compact card with large number + label |
| `.ds-nav-link` | Navigation link | PI's nav link pattern |

**1.3 Utility Classes**
- `.ds-tabular-nums` — `font-variant-numeric: tabular-nums`
- `.ds-accent-border-left-{color}` — Left border accent (for sections)
- `.ds-accent-border-top-{color}` — Top border accent (for cards)

**Files changed:**
- **New**: `static/css/design-system.css`

---

### Phase 2: Base Template & Navigation Overhaul

**Goal**: Update `base.html` to link the design system CSS, switch to Lucide icons, and make the navbar match PI's header component exactly.

**2.1 Update `<head>` in `base.html`**
- Add `<link>` to `static/css/design-system.css`
- Add Lucide icons CDN: `<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>`
- Keep Bootstrap Icons CDN during transition (remove in Phase 7)
- Remove inline `:root` vars and shared styles from `<style>` block (now in CSS file)

**2.2 Rebuild Navbar to match PI's `header.tsx`**

Target structure (matching PI):
```html
<header class="ds-header">
  <div class="ds-header-inner">
    <div class="ds-header-left">
      <a href="/suite" class="ds-brand">Envoy LLC</a>
      <nav class="ds-nav">
        <a href="/suite" class="ds-nav-link {active}">
          <i data-lucide="layout-grid" class="ds-nav-icon"></i>
          Suite Home
        </a>
        <!-- ... other nav items ... -->
      </nav>
    </div>
    <div class="ds-header-right">
      <a href="/logout" class="ds-btn-secondary ds-btn-sm">
        <i data-lucide="log-out" class="ds-nav-icon"></i>
        Logout
      </a>
    </div>
  </div>
</header>
```

Key changes:
- Replace `<nav class="navbar navbar-expand-lg">` with semantic `<header>` + custom classes
- Replace Bootstrap Icons (`bi bi-*`) with Lucide (`data-lucide="*"`)
- Match PI's sizing: `text-sm font-medium`, icons at 16px
- Active state: bottom border on active link (matching PI's `border-b-2 border-primary`)
- Responsive: nav links hidden on mobile (matching PI's `hidden md:flex`)
- Call `lucide.createIcons()` in scripts block

**2.3 Fix `news_simple.html`**
- **Remove** the entire `{% block navbar %}` override — it will now inherit the standard navbar from base.html
- This is the single biggest visual consistency win

**Files changed:**
- `templates/base.html` — major update
- `templates/news_simple.html` — remove navbar override

---

### Phase 3: News Analysis Redesign

**Goal**: Transform the news pages from gradient-heavy standalone design to clean, PI-matching cards.

**3.1 `news_simple.html` — Form Page Redesign**

Remove:
- Gradient body background (`linear-gradient(135deg, #667eea, #764ba2)`)
- Frosted glass card (`backdrop-filter: blur(10px)`)
- Font Awesome icons
- Gradient analyze button
- Segoe UI font override

Replace with:
- Standard `bg-background` body (inherited from base.html)
- Clean `.ds-card` centered on page
- Purple accent: subtle top border on form card (`.ds-card-accent-purple`)
- Standard `.ds-btn-primary` submit button
- Lucide icons throughout
- PI-matching input styles (`.ds-input`, `.ds-select`)
- Ticker badges using `.ds-badge` classes
- Feature icons in bottom section: same rounded square pattern as suite landing tool icons

Loading overlay redesign:
- Replace the dark overlay + Bootstrap spinner with a cleaner modal matching PI's aesthetic
- Use design system card + skeleton animations instead

**3.2 `news_results.html` — Results Page Redesign**

Remove:
- Gradient source breakdown card
- `backdrop-filter` effects
- Font Awesome icons
- Inconsistent badge colors

Replace with:
- Standard `.ds-card` for each analysis section
- Left border accents per section type:
  - Executive Summary: `.ds-accent-border-left-green`
  - Investor Analysis: `.ds-accent-border-left-blue`
  - Catalysts/Risks: `.ds-accent-border-left-red`
- Source badges: `.ds-badge-green` (premium), `.ds-badge-purple` (AlphaVantage), etc.
- Standard `.ds-table` for article listings
- Clean, white-background metric cards
- AI assistant section: `.ds-card` with primary accent

**3.3 `monitoring_dashboard.html` — Monitoring Page**

Remove:
- Gradient metric cards

Replace with:
- `.ds-kpi-card` components
- Standard chart theming

**Files changed:**
- `templates/news_simple.html` — major redesign
- `templates/news_results.html` — major redesign
- `templates/monitoring_dashboard.html` — moderate update

---

### Phase 4: Suite Landing Page Polish

**Goal**: Refine the already-decent suite landing to perfectly match PI quality.

**4.1 Update Tool Cards**
- Switch icons from Bootstrap Icons to Lucide
- Match PI's nav icon sizing pattern
- Tighten typography to match PI: `text-sm` descriptions, `font-bold text-lg` titles
- Ensure hover animation exactly matches PI: `translateY(-2px)` (not -5px)

**4.2 Improve Responsive Grid**
- Add `gap-4` matching PI's portfolio grid
- Ensure single-column on mobile

**4.3 Polish Header Section**
- Match PI's page title pattern: `text-2xl font-bold`
- Tighten subtitle styling

**Files changed:**
- `templates/suite_landing.html` — moderate update

---

### Phase 5: ISM Dashboard Modernization

**Goal**: Incrementally bring the ~3900-line dashboard in line with the design system. This is the largest and most careful phase.

**5.1 Remove Duplicated Styles**
- Remove the redeclared `:root` vars (now in design-system.css)
- Remove redeclared navbar styles (now in base.html)
- Remove redeclared body styles (now in design-system.css)
- This alone could remove ~80 lines

**5.2 Update Dashboard Header**
- Use `.ds-page-title` for the h1
- Standardize the report selector/controls area

**5.3 Modernize Tab Navigation**
- Replace custom tab styling with PI-matching pattern
- Active tab: `border-b-2 border-primary text-primary` (matching nav pattern)
- Inactive: `text-muted hover:text-foreground`

**5.4 Modernize Cards**
- Replace inline card styles with `.ds-card` classes
- KPI cards: use `.ds-kpi-card`
- Chart containers: use `.ds-card` with appropriate padding
- Add `.ds-tabular-nums` to all numeric displays

**5.5 Modernize Tables (Heatmaps)**
- Apply `.ds-table` base styling
- Keep the heatmap color logic (Growing green / Contracting red) but update cells to use design tokens
- Ensure sticky header styling works with new design

**5.6 Chart Theming**
- Update Chart.js options to match PI's Recharts aesthetic:
  - Grid: `strokeDasharray: "3 3"`, color `#f0f0f0`
  - Axes: tick font size 11, color `#6c757d`, no tick lines
  - Tooltips: `borderRadius: 8px`, border `#e2e8f0`

**5.7 Switch Icons**
- Replace Bootstrap Icons with Lucide equivalents throughout dashboard

**Files changed:**
- `templates/dashboard.html` — incremental, careful updates across multiple sub-phases

---

### Phase 6: Upload & Landing Pages

**Goal**: Bring remaining standalone/semi-standalone pages into the design system.

**6.1 `index.html` (Upload Page)**
- Remove redeclared `:root` vars, navbar styles, body styles (already in base/design-system)
- Replace inline card styles with `.ds-card` classes
- Update upload area to use design tokens
- Replace footer with shared footer pattern (or remove — other pages don't have footers)
- Switch icons to Lucide

**6.2 `landing.html` (Pre-Auth Page)**
- Convert from standalone to extending `base.html` (or a minimal `base_public.html`)
- Update branding: "Envoy Financial Intelligence Suite" (not just ISM)
- Showcase all 3 tools in feature cards (not just ISM features)
- Use design system classes for hero, cards, buttons
- Fix hover color: `#004494` → `#10104D` (match design tokens)
- Switch icons to Lucide
- Update copyright year to 2026

**6.3 `results.html` (ISM Processing Results)**
- Convert from standalone to extending `base.html`
- Apply design system loading animation (skeleton pulse, not raw spinner)
- Use `.ds-card` for result containers

**Files changed:**
- `templates/index.html` — moderate cleanup
- `templates/landing.html` — significant redesign
- `templates/results.html` — moderate update

---

### Phase 7: Animation, Polish & Cleanup

**Goal**: Final consistency pass and polish.

**7.1 Animation Consistency**
- Ensure all hover transitions are `0.3s ease` (matching PI)
- Card hover lift: standardize to `translateY(-2px)` + `shadow-hover` (PI uses -0.5 which is -2px)
- Button hover lift: `translateY(-2px)`
- Add subtle focus ring to interactive elements: `0 0 0 2px rgba(25, 25, 112, 0.2)`

**7.2 Loading State Improvements**
- Replace Bootstrap spinners with skeleton pulse animations where appropriate
- Standardize the processing overlay across News and ISM upload

**7.3 Icon Migration Completion**
- Remove Bootstrap Icons CDN from `base.html`
- Remove Font Awesome CDN from news templates
- Audit all templates for remaining Bootstrap Icon / Font Awesome usage
- Ensure `lucide.createIcons()` is called after any dynamic content insertion

**7.4 Typography Audit**
- Ensure all headings use `letter-spacing: -0.02em`
- Ensure all body text uses `letter-spacing: -0.01em`
- Ensure all financial numbers use `font-variant-numeric: tabular-nums`

**7.5 Final Visual Audit**
- Side-by-side comparison of each Flask page with PI
- Check responsive behavior at all breakpoints
- Verify color consistency across all pages
- Test all interactive states (hover, focus, active, disabled)

**7.6 Cleanup**
- Remove any remaining inline style duplicates
- Remove commented-out old CSS
- Ensure no template has leftover `:root` declarations (all in design-system.css)

**Files changed:**
- Multiple templates — minor tweaks
- `templates/base.html` — remove Bootstrap Icons CDN

---

## File Impact Summary

| File | Phase | Change Scope |
|------|-------|-------------|
| `static/css/design-system.css` | 1 | **New file** — design system foundation |
| `templates/base.html` | 2 | **Major** — new CSS link, Lucide CDN, rebuilt navbar |
| `templates/news_simple.html` | 2, 3 | **Major** — remove navbar override, complete visual redesign |
| `templates/news_results.html` | 3 | **Major** — remove gradients, standardize cards/badges |
| `templates/monitoring_dashboard.html` | 3 | **Moderate** — remove gradient cards, apply design system |
| `templates/suite_landing.html` | 4 | **Moderate** — polish cards, switch icons |
| `templates/dashboard.html` | 5 | **Major** — incremental modernization (most complex) |
| `templates/index.html` | 6 | **Moderate** — remove duplicated styles, apply design system |
| `templates/landing.html` | 6 | **Significant** — rebrand, extend base, apply design system |
| `templates/results.html` | 6 | **Moderate** — extend base, apply design system |

---

## Design Reference: PI's Tailwind Config → CSS Vars Mapping

| PI Tailwind Token | CSS Variable | Value |
|-------------------|-------------|-------|
| `colors.primary.DEFAULT` | `--color-primary` | `#191970` |
| `colors.primary.hover` | `--color-primary-hover` | `#10104D` |
| `colors.background` | `--color-background` | `#f8fafc` |
| `colors.foreground` | `--color-foreground` | `#333333` |
| `colors.muted` | `--color-muted` | `#6c757d` |
| `colors.accent.green` | `--color-accent-green` | `#28a745` |
| `colors.accent.red` | `--color-accent-red` | `#dc3545` |
| `colors.accent.blue` | `--color-accent-blue` | `#3b82f6` |
| `colors.accent.purple` | `--color-accent-purple` | `#764ba2` |
| `colors.accent.warning` | `--color-accent-warning` | `#ffc107` |
| `borderRadius.card` | `--radius-card` | `16px` |
| `borderRadius.button` | `--radius-button` | `8px` |
| `boxShadow.subtle` | `--shadow-subtle` | `0 2px 10px rgba(0,0,0,0.05)` |
| `boxShadow.card` | `--shadow-card` | `0 4px 20px rgba(0,0,0,0.05)` |
| `boxShadow.hover` | `--shadow-hover` | `0 8px 30px rgba(0,0,0,0.1)` |

---

## Execution Notes

1. **Each phase can be tested independently** — no phase creates breaking changes for others
2. **Phase 1 must complete first** — all other phases depend on `design-system.css`
3. **Phase 2 should come second** — the navbar unification affects all pages
4. **Phases 3-6 can be parallelized** if multiple developers are working
5. **Phase 7 is a sweep** — should come last after all pages are updated
6. **Dashboard (Phase 5)** is highest risk due to complexity — test heatmaps and charts carefully
7. **Keep Bootstrap** for grid layout (`col-*`, `container`, `row`, `g-*`) — only replace its visual styling
