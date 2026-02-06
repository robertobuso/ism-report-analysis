# Base Template Migration

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Suite Integration

---

## Overview

Extracted shared boilerplate from 5 existing Flask templates into a single `base.html` template. This enables consistent navigation and styling across all tools in the Envoy Financial Intelligence Suite without duplicating HTML structure, stylesheets, or navbar markup in every template.

---

## Technical Implementation

### `templates/base.html`

Created a Jinja2 base template with the following overridable blocks:

| Block | Purpose |
|-------|---------|
| `title` | Page title in the `<title>` tag |
| `head` | Additional `<head>` content (meta tags, etc.) |
| `extra_styles` | Template-specific CSS |
| `navbar` | Full navbar markup (overridable for templates that need a custom navbar) |
| `content` | Main page content |
| `scripts` | Template-specific JavaScript |

### Design Tokens

CSS variables defined in `:root` matching the suite's design tokens:

```css
:root {
    --primary-color: midnightblue;
    /* additional tokens */
}
```

### External Dependencies

- **Inter font** via Google Fonts CDN
- **Bootstrap 5.3.0** for layout and component styling

### Navbar

The shared navbar includes links to:

1. Suite Home
2. ISM Analysis
3. News Analysis
4. Portfolio Intelligence
5. Logout

### Navigation Highlighting

An `active_page` context variable is set per route and used in the navbar to highlight the current tool's link. This is injected via a context processor in `app.py`.

### Context Processor

A context processor in `app.py` injects two values into every template context:

- `portfolio_intelligence_url` -- read from the `PORTFOLIO_INTELLIGENCE_URL` environment variable, used to build the PI nav link
- `active_page` -- identifies which tool is currently active for navbar highlighting

---

## Templates Migrated

1. **`dashboard.html`** -- ISM dashboard (approximately 3900 lines). Extracted head section and navbar, wrapped existing content in `{% block content %}`.
2. **`index.html`** -- Upload page for ISM report files. Extends `base.html` with standard blocks.
3. **`news_simple.html`** -- News analysis input page. Overrides `{% block navbar %}` to render a gradient dark navbar that matches the news tool's visual identity.
4. **`news_results.html`** -- News analysis results page. Includes Font Awesome for icons alongside the shared base.
5. **`monitoring_dashboard.html`** -- Quality monitoring dashboard. Extends `base.html` with standard blocks.

### NOT Migrated

- **`landing.html`** -- Pre-authentication landing page. This is a standalone page shown before login and intentionally does not share the suite navbar or template structure.

---

## Testing

Each migrated template was verified to render correctly with the shared navbar. Active link highlighting was confirmed to work for each tool's routes. No visual regressions were introduced by the migration.
