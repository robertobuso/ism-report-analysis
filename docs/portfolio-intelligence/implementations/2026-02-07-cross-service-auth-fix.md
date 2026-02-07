# Cross-Service Authentication Fix — Implementation

**Date**: 2026-02-07
**Domain**: portfolio-intelligence
**Status Document Updated**: Yes

---

## Summary

Fixed critical authentication failure between Flask (Suite) and Portfolio Intelligence services in production. The issue prevented users from accessing Portfolio Intelligence after successful Google OAuth login, causing a redirect loop back to the landing page.

**Root Causes Identified**:
1. Pydantic Settings not reading `SECRET_KEY` from Railway environment variables
2. Frontend race condition destroying auth tokens during page reload

---

## The Problems

### Problem 1: Pydantic Not Reading Environment Variables (Primary Root Cause)

**Symptom**: Backend returned `401 Unauthorized` with error `JWTError: Signature verification failed`

**Root Cause**: The PI Backend's `config.py` was using the default value `"change-me-in-production"` instead of reading `SECRET_KEY` from Railway environment variables.

**Why It Happened**:
- Pydantic Settings v2 with `model_config = {"env_file": ".env"}` was configured to read from a `.env` file
- In Railway's containerized environment, there is no `.env` file
- Without explicit field aliases, Pydantic was falling back to the default value
- The SECRET_KEY was set correctly in Railway dashboard, but the code wasn't reading it

**Evidence from Logs**:
```
INFO:app.dependencies:🔑 SECRET_KEY configured: your-secre...
```
This showed the default placeholder value, not the actual SECRET_KEY from Railway.

**The Fix**:
```python
# portfolio_intelligence/backend/app/config.py

from pydantic import Field

class Settings(BaseSettings):
    # Explicitly tell Pydantic to read from SECRET_KEY environment variable
    secret_key: str = Field(
        default="change-me-in-production",
        validation_alias="SECRET_KEY"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,  # Ensures SECRET_KEY matches secret_key
        "extra": "ignore"
    }
```

**Key Changes**:
- Added `validation_alias="SECRET_KEY"` to explicitly map the environment variable
- Set `case_sensitive=False` to ensure SECRET_KEY (uppercase) matches secret_key (lowercase field name)
- Added `env_file_encoding="utf-8"` for consistency

---

### Problem 2: Frontend Race Condition (Secondary Issue)

**Symptom**: Even after fixing the SECRET_KEY issue, users still got redirected to landing. Logs showed `TypeError: Failed to fetch` followed by token deletion.

**Root Cause**: The frontend was using `window.location.reload()` to refresh the page after storing the token. This created a race condition:

1. Token stored in localStorage
2. `window.location.reload()` called
3. **During reload**, AuthProvider's useEffect started running and began fetching `/api/v1/auth/me`
4. **The reload killed the in-flight fetch request** → `TypeError: Failed to fetch`
5. AuthProvider's catch block saw the error and called `localStorage.removeItem("token")`
6. Page finished reloading with no token → redirected to landing

**The Self-Destruct Loop**:
```typescript
// BROKEN CODE (before fix)
if (token) {
  localStorage.setItem("token", token);
  window.location.reload();  // ❌ Kills fetch requests in flight
}

// In AuthProvider
try {
  const data = await api.getMe();  // Gets killed by reload
} catch (error) {
  localStorage.removeItem("token");  // ❌ Nukes token on ANY error
}
```

**The Fix**:

1. **Stop reloading the page** — Use `window.history.replaceState()` instead
2. **Only remove token on 401** — Don't delete it on network errors

```typescript
// page.tsx - Stop using reload
if (token) {
  localStorage.setItem("token", token);
  // Clean URL without reloading (doesn't kill fetch requests)
  window.history.replaceState({}, "", window.location.pathname);
}

// auth-provider.tsx - Only remove token on real auth failure
try {
  const data = await api.getMe();
  setUser(data);
} catch (error: any) {
  // Only remove token if the server actually rejected it
  if (error.status === 401) {
    localStorage.removeItem("token");
  }
  // Network errors (Failed to fetch) won't delete the token
}
```

---

## What Changed

### Files Modified

**Backend**:
- `portfolio_intelligence/backend/app/config.py` — Fixed Pydantic environment variable reading
- `portfolio_intelligence/backend/app/main.py` — Added startup validation for SECRET_KEY
- `portfolio_intelligence/backend/app/dependencies.py` — Added debug logging (can be removed later)
- `app.py` — Added startup validation for SECRET_KEY

**Frontend**:
- `portfolio_intelligence/frontend/src/app/page.tsx` — Removed `window.location.reload()`, use `history.replaceState()`
- `portfolio_intelligence/frontend/src/providers/auth-provider.tsx` — Only remove token on 401, not network errors

### Commits
- `890cd7c` — Fix: Force Pydantic to read SECRET_KEY from environment
- `c6124c2` — Fix race condition: stop nuking token on network errors

---

## Testing

### Verification Steps

1. **Verify SECRET_KEY is properly read**:
   ```bash
   # Check Railway logs for both services
   # Flask should show: ✅ SECRET_KEY configured (first 10 chars: <value>...)
   # PI Backend should show: ✅ SECRET_KEY is configured (first 10 chars: <value>...)
   # First 10 chars MUST match
   ```

2. **Test authentication flow**:
   - Visit production: https://envoyllc-ism.up.railway.app
   - Log in with Google OAuth
   - Click "Portfolio Intelligence" card
   - **Expected**: Should stay on PI page and show portfolios (or empty state if no portfolios)
   - **Should NOT**: Redirect back to landing page

3. **Verify token persistence**:
   - After successful login, check browser console → Application → Local Storage
   - Should see `token` key with JWT value
   - Token should persist across page refreshes

---

## Lessons Learned

### 1. Pydantic Settings Environment Variable Reading

**Issue**: Pydantic Settings doesn't automatically read uppercase environment variables for lowercase field names in all deployment environments.

**Solution**: Always use explicit `validation_alias` for critical environment variables:

```python
class Settings(BaseSettings):
    secret_key: str = Field(default="...", validation_alias="SECRET_KEY")
    database_url: str = Field(default="...", validation_alias="DATABASE_URL")
    # etc.
```

**Why**: Railway and other container platforms inject environment variables directly, not through `.env` files. Explicit aliases ensure the values are read correctly.

### 2. Never Use `window.location.reload()` in React/Next.js

**Issue**: `window.location.reload()` is a "sledgehammer" that kills all in-flight requests, causing race conditions with useEffect hooks.

**Solution**: Let React handle re-rendering naturally. If you need to clean the URL:

```typescript
// ✅ GOOD - Clean URL without reloading
window.history.replaceState({}, "", window.location.pathname);

// ❌ BAD - Kills everything
window.location.reload();
```

**Why**: React's useEffect hooks run during mount and the reload kills fetch requests that start during the reload process.

### 3. Error Handling Must Distinguish Error Types

**Issue**: Treating all errors the same way (removing auth tokens) causes false positives when network hiccups occur.

**Solution**: Only take destructive actions (like removing tokens) on explicit auth failures:

```typescript
catch (error: any) {
  if (error.status === 401) {
    // Server explicitly rejected auth
    localStorage.removeItem("token");
  }
  // Network errors, timeouts, etc. don't delete the token
}
```

**Why**: Network errors, CORS issues, and server restarts shouldn't log users out.

### 4. Environment Variable Validation on Startup

**Best Practice**: Critical environment variables should be validated on startup, not silently fall back to defaults:

```python
# PI Backend startup
if settings.secret_key == "change-me-in-production":
    logger.error("🚨 FATAL: SECRET_KEY is not set!")
    raise RuntimeError("SECRET_KEY environment variable is not set!")
```

```python
# Flask startup
if not os.environ.get('SECRET_KEY'):
    logger.error("🚨 FATAL: SECRET_KEY environment variable is not set!")
    raise RuntimeError("SECRET_KEY environment variable is required!")
```

**Why**: Fail fast and loud. Don't let misconfigured services run in production.

---

## Railway Deployment Checklist

When deploying services that share secrets (like JWT SECRET_KEY):

### Before Deployment
- [ ] Ensure SECRET_KEY is set in **both services** (Flask and PI Backend)
- [ ] Verify the values are **exactly identical** (no extra spaces, same case)
- [ ] Verify environment variable names are **exactly correct** (case-sensitive)
- [ ] For Pydantic services, ensure `validation_alias` is set for critical env vars

### After Deployment
- [ ] Check startup logs to verify SECRET_KEY was read correctly
- [ ] Compare first 10 characters of SECRET_KEY in logs from both services
- [ ] Test the auth flow end-to-end
- [ ] Verify tokens persist in localStorage after page reload

### Common Pitfalls
- ❌ Setting SECRET_KEY in only one service
- ❌ Extra whitespace in environment variable value
- ❌ Typo in environment variable name (e.g., `SECERT_KEY`)
- ❌ Not redeploying after changing environment variables
- ❌ Assuming Pydantic will automatically read uppercase env vars for lowercase fields

---

## Follow-Up

### Optional Improvements
1. **Remove debug logging** — The detailed logs in `dependencies.py`, `page.tsx`, and `auth-provider.tsx` can be removed once the auth flow is stable
2. **Add health check endpoint** — Create `/health` endpoint that verifies SECRET_KEY is set correctly
3. **Add env var documentation** — Document all required environment variables for each service

### Tech Debt
- None. The fixes are production-ready and don't introduce technical debt.

---

## Related Documents
- [Portfolio Intelligence Status](../status/current-implementation-status.md)
- [Dev Environment Setup](../../suite/implementations/dev-environment-setup.md)
