# Suite Landing Page

**Date**: 2026-02-06
**Status**: Complete
**Domain**: Suite Integration

---

## Overview

Built the suite landing page as the unified entry point for all tools after login. Users see a card for each tool and can navigate directly to the one they need.

---

## Technical Implementation

### Template

`templates/suite_landing.html` extends `base.html`. It renders 3 responsive tool cards in a grid layout.

### Route

```python
@app.route('/suite')
@login_required
def suite():
    ...
```

The route requires authentication and sets `active_page='suite'` for navbar highlighting.

### Tool Cards

| Tool | Color | Hex |
|------|-------|-----|
| ISM Report Analysis | Green | `#28a745` |
| Financial News Analysis | Purple | `#764ba2` |
| Portfolio Intelligence | Blue | `#3b82f6` |

Each card includes the tool name, a brief description, and a link to the tool's main page.

### Portfolio Intelligence Availability

The PI card's behavior depends on the `PORTFOLIO_INTELLIGENCE_URL` environment variable:

- **Not set**: The card displays a "Coming Soon" badge and no active link.
- **Set**: The card renders an active link pointing to the PI frontend URL.

This allows the suite to be deployed before PI is production-ready without showing broken links.

### Redirect Behavior

- **Root route (`/`)**: Redirects authenticated users to `/suite`. Unauthenticated users see the landing/login page.
- **Post-OAuth callback**: After successful authentication, the OAuth callback redirects to `/suite`.

### Navigation

The route passes `active_page='suite'` to the template context, which highlights the "Suite Home" link in the shared navbar.
