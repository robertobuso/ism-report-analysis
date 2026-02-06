# Design Tokens — Envoy Financial Intelligence Suite

**Locked:** 2026-02-06
**Applies to:** All suite applications (Flask + Next.js)

---

## Suite Identity

**Name:** Envoy Financial Intelligence Suite
**Tagline:** Institutional rigor. Consumer polish.

---

## Color Palette

### Brand Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--primary` | `#191970` (midnightblue) | Primary buttons, active nav, headings |
| `--primary-hover` | `#10104D` | Hover states on primary elements |
| `--background` | `#f8fafc` | Page backgrounds |
| `--foreground` | `#333333` | Body text |
| `--muted` | `#6c757d` | Secondary text, captions |
| `--card-shadow` | `rgba(0, 0, 0, 0.05)` | Default card elevation |

### Accent Colors (Per Tool)

| Tool | Accent | Value | Usage |
|------|--------|-------|-------|
| ISM Report Analysis | Green | `#28a745` | Tool card border, badges |
| Financial News Analysis | Purple | `#764ba2` | Tool card border, badges |
| Portfolio Intelligence | Blue | `#3b82f6` | Tool card border, badges |

### Semantic Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--accent-green` | `#28a745` | Positive returns, growing |
| `--accent-red` | `#dc3545` | Negative returns, contracting |
| `--accent-warning` | `#ffc107` | Warnings, neutral alerts |
| `--accent-info` | `#17a2b8` | Informational badges |

---

## Typography

| Property | Value |
|----------|-------|
| Font Family | `Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` |
| Font Source | Google Fonts CDN |
| Body Weight | 400 |
| Semibold | 600 |
| Bold | 700 |
| Body Line Height | 1.6 |
| Letter Spacing | -0.01em (body), -0.02em (headings) |
| Numerical Display | Tabular numerals (`font-variant-numeric: tabular-nums`) |

---

## Spacing & Radius

| Token | Value | Usage |
|-------|-------|-------|
| Card Radius | 16px | Content cards |
| Button Radius | 8px | Buttons, inputs |
| Badge Radius | 20px | Pills, tags |
| Container Max Width | 1200px (landing), 1900px (dashboard) |
| Section Padding | 2rem | Content sections |

---

## Elevation

| Level | Shadow | Usage |
|-------|--------|-------|
| 1 (subtle) | `0 2px 10px rgba(0,0,0,0.05)` | Navbar, flat cards |
| 2 (default) | `0 4px 20px rgba(0,0,0,0.05)` | Content cards |
| 3 (hover) | `0 8px 30px rgba(0,0,0,0.1)` | Hover state, modals |
| 4 (hero) | `0 10px 30px rgba(0,86,179,0.08)` | Hero sections |

---

## Animation

| Property | Value |
|----------|-------|
| Default Transition | `all 0.3s ease` |
| Hover Lift | `translateY(-2px)` |
| Card Hover Lift | `translateY(-5px)` |

---

## Cross-App Consistency Notes

- Flask app uses Bootstrap 5.3.0 + CSS variables
- Portfolio Intelligence uses Tailwind CSS + `tailwind.config.ts` tokens
- Both apps share the same brand tokens above
- Goal: "same brand, different vintage" — not "different products"
- Medium-term: converge Flask templates toward these tokens
