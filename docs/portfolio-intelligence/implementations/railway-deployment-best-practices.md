# Railway Deployment Best Practices

**Date**: 2026-02-07
**Domain**: portfolio-intelligence
**Applies To**: All services in the Envoy Financial Intelligence Suite

---

## Overview

This document captures deployment best practices learned from production issues, particularly around environment variable configuration and cross-service authentication.

**Key Principle**: Fail fast, fail loud. Misconfigured services should refuse to start, not run with broken defaults.

---

## Environment Variables

### 1. Always Use Explicit Aliases in Pydantic

❌ **WRONG** — Relying on implicit mapping:
```python
class Settings(BaseSettings):
    secret_key: str = "change-me-in-production"
```

✅ **CORRECT** — Explicit validation alias:
```python
from pydantic import Field

class Settings(BaseSettings):
    secret_key: str = Field(
        default="change-me-in-production",
        validation_alias="SECRET_KEY"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }
```

**Why**: Railway injects environment variables directly (no `.env` file). Without explicit aliases, Pydantic may silently use default values in containerized environments.

**When This Matters**:
- Any environment variable used across multiple services (SECRET_KEY, DATABASE_URL, etc.)
- Critical configuration that shouldn't fall back to defaults in production

---

### 2. Validate Critical Variables on Startup

❌ **WRONG** — Silent fallback to defaults:
```python
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
```

✅ **CORRECT** — Explicit validation with failure:
```python
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    logger.error("🚨 FATAL: SECRET_KEY environment variable is not set!")
    raise RuntimeError("SECRET_KEY is required for production")

app.secret_key = secret_key
logger.info(f"✅ SECRET_KEY configured (first 10 chars: {secret_key[:10]}...)")
```

**Benefits**:
- Service won't start if misconfigured
- Logs clearly show the first 10 chars of the key for verification
- No silent failures in production

**Apply This Pattern To**:
- `SECRET_KEY` (for JWT signing)
- `DATABASE_URL` (for database connection)
- `REDIS_URL` (for Celery broker)
- Any inter-service authentication credentials

---

### 3. Railway Environment Variable Checklist

Before deploying services that share secrets:

- [ ] Verify variable name is **exactly correct** (case-sensitive)
- [ ] Verify value has **no extra whitespace** (leading/trailing spaces break things)
- [ ] Verify value has **no quotes** unless quotes are part of the actual value
- [ ] Set variable in **all services** that need it
- [ ] Verify values are **identical** across services (for shared secrets like SECRET_KEY)
- [ ] **Redeploy all services** after setting variables (changes don't auto-apply)
- [ ] Check startup logs to confirm variables were read correctly

**Common Mistakes**:
- Setting `SECERT_KEY` instead of `SECRET_KEY` (typo)
- Setting variable in one service but forgetting another
- Not redeploying after changing the variable
- Copy-pasting values with hidden unicode characters

---

### 4. Log Verification, Not Full Values

✅ **GOOD** — Log first 10 characters for verification:
```python
logger.info(f"✅ SECRET_KEY configured: {settings.secret_key[:10]}...")
```

❌ **BAD** — Log full secret values:
```python
logger.info(f"SECRET_KEY: {settings.secret_key}")  # ⚠️ Security risk!
```

**Why**: Logs may be sent to third-party services or viewed by multiple team members. First 10 chars is enough to verify keys match without exposing the full secret.

---

## Frontend Environment Variables (Next.js)

### 1. Next.js Variables Are Baked at Build Time

**Critical Rule**: `NEXT_PUBLIC_*` variables are embedded in the JavaScript bundle during build, not read at runtime.

**Implications**:
- If you change `NEXT_PUBLIC_API_URL` in Railway, you MUST redeploy (rebuild) the frontend
- The variable value is whatever it was when the bundle was built
- Restarting the service doesn't help — you need a full rebuild

**Verification**:
```bash
# Check the compiled bundle to see what value was baked in
curl https://your-frontend.railway.app/_next/static/chunks/app/layout-*.js | grep -o 'API_BASE.*' | head -1
```

---

### 2. Always Provide Fallback for Local Dev

✅ **GOOD** — Explicit fallback for local development:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
```

❌ **BAD** — No fallback (breaks local dev):
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL!;
```

**Why**: Local development shouldn't require `.env.local` file to be set up. The fallback makes it work out of the box.

---

## React/Next.js Best Practices

### 1. Never Use `window.location.reload()`

❌ **WRONG** — Kills in-flight requests:
```typescript
if (token) {
  localStorage.setItem("token", token);
  window.location.reload();  // ⚠️ Destroys everything
}
```

✅ **CORRECT** — Let React handle re-rendering:
```typescript
if (token) {
  localStorage.setItem("token", token);
  window.history.replaceState({}, "", window.location.pathname);
  // React will naturally re-render with the new token
}
```

**Why**: `window.location.reload()` kills all active fetch requests, causing race conditions when useEffect hooks are running during the reload.

**Exception**: Never. There's always a better way.

---

### 2. Distinguish Between Error Types

❌ **WRONG** — All errors are treated the same:
```typescript
try {
  const user = await api.getMe();
} catch (error) {
  localStorage.removeItem("token");  // ⚠️ Deletes token on network hiccups
}
```

✅ **CORRECT** — Only remove token on auth failure:
```typescript
try {
  const user = await api.getMe();
} catch (error: any) {
  if (error.status === 401) {
    // Server explicitly rejected the token
    localStorage.removeItem("token");
  }
  // Network errors, timeouts, CORS issues don't delete the token
}
```

**Error Types to Handle Differently**:
- `401 Unauthorized` → Remove token, redirect to login
- `403 Forbidden` → Show access denied message, keep token
- `TypeError: Failed to fetch` → Network error, retry or show error, keep token
- `500 Internal Server Error` → Server issue, show error, keep token

---

## Cross-Service Authentication

### 1. Shared Secret Requirements

When multiple services share a secret (like SECRET_KEY for JWT):

**Requirements**:
- Values MUST be byte-for-byte identical
- Set in **all services** that use it
- Validated on startup in **all services**
- Logged (first 10 chars) for verification in **all services**

**Verification**:
```bash
# Compare startup logs from both services
# Flask: ✅ SECRET_KEY configured (first 10 chars: of0lU-OfeW...)
# PI Backend: ✅ SECRET_KEY is configured (first 10 chars: of0lU-OfeW...)
# First 10 chars MUST match
```

---

### 2. JWT Token Standards

When passing JWTs between services:

**Required Claims**:
- `iat` (issued at) → Unix timestamp (integer, not datetime object)
- `exp` (expiration) → Unix timestamp (integer, not datetime object)
- User identifier → `email` or `sub` (one is required)

**Python Implementation**:
```python
import time
from datetime import datetime, timedelta

now = datetime.utcnow()
payload = {
    'email': user_email,
    'iat': int(now.timestamp()),  # ✅ Convert to int
    'exp': int((now + timedelta(hours=24)).timestamp())  # ✅ Convert to int
}

token = jwt.encode(payload, secret_key, algorithm='HS256')
```

❌ **WRONG** — Passing datetime objects:
```python
payload = {
    'email': user_email,
    'iat': datetime.utcnow(),  # ❌ Will serialize incorrectly
    'exp': datetime.utcnow() + timedelta(hours=24)  # ❌ Will serialize incorrectly
}
```

---

## Debugging Checklist

When authentication fails in production:

### Step 1: Verify Environment Variables
- [ ] Check Railway dashboard → Each service → Variables tab
- [ ] Verify SECRET_KEY is set in all services
- [ ] Verify first 10 chars match across services (check logs)
- [ ] Verify no typos in variable names

### Step 2: Check Startup Logs
- [ ] Verify services started successfully (no crashes)
- [ ] Look for validation errors or warnings
- [ ] Confirm SECRET_KEY was read (not using default)

### Step 3: Test JWT Decode
Create a debug endpoint to test JWT validation:
```python
@router.get("/debug/jwt")
async def debug_jwt(token: str = Query(...)):
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
        return {"status": "success", "payload": payload}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

### Step 4: Check Frontend Network Tab
- [ ] Verify token is in URL when redirecting to PI
- [ ] Verify token is stored in localStorage
- [ ] Check /api/v1/auth/me request status code
- [ ] Check request/response headers

### Step 5: Compare JWT Libraries
If using different JWT libraries (PyJWT vs python-jose):
- [ ] Verify both libraries are compatible
- [ ] Test cross-decode (PyJWT encode → python-jose decode)

---

## Summary

**Golden Rules**:
1. ✅ Use explicit `validation_alias` in Pydantic for all critical env vars
2. ✅ Validate env vars on startup, fail fast if missing
3. ✅ Log first 10 chars of secrets for verification
4. ✅ Never use `window.location.reload()` in React
5. ✅ Only remove auth tokens on explicit 401 responses
6. ✅ Convert datetime to Unix timestamp integers for JWT claims
7. ✅ Verify SECRET_KEY values match across services before deploying

**When Adding New Services**:
- Review this document
- Add startup validation for critical env vars
- Log verification info (first 10 chars of secrets)
- Test the deploy process on Railway staging before production

---

## Related Documents

- [Cross-Service Auth Fix](./2026-02-07-cross-service-auth-fix.md) — Detailed root cause analysis
- [Dev Environment Setup](../../suite/implementations/dev-environment-setup.md) — Local development setup
- [Portfolio Intelligence Status](../status/current-implementation-status.md) — Current state
