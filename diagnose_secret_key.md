# 🔍 JWT Validation Failure - Root Cause & Solution

## Root Cause Identified

The redirect to landing is caused by **JWT validation failure** at `/api/v1/auth/me` in the PI backend.

### The Problem

**Location:** `app.py:68`
```python
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
```

**Why it fails:**
1. If `SECRET_KEY` is **not set** in Flask's Railway environment, Flask generates a **random** secret key on startup
2. This random key is different from the PI Backend's `SECRET_KEY`
3. JWT encoded by Flask cannot be decoded by PI Backend
4. PI Backend returns 401 → Frontend redirects to landing

### JWT Flow in Production

```
✅ Google OAuth → Flask gets email: robertobuso@gmail.com
✅ Flask generates JWT with app.secret_key
✅ JWT passed in URL: ?token=eyJ...
✅ PI Frontend receives token, stores in localStorage
❌ PI Backend tries to decode JWT with settings.secret_key
❌ SECRET_KEY_FLASK ≠ SECRET_KEY_PI_BACKEND
❌ JWTError raised → 401 Unauthorized
❌ Frontend redirects to /landing
```

## ✅ Verified: PyJWT ↔ python-jose Compatibility

**Test Result:** ✅ COMPATIBLE
The libraries work together perfectly. The issue is purely the SECRET_KEY mismatch.

---

## 🔧 Solution

### Step 1: Check Current SECRET_KEY Values

**For Flask Service (ism-report-analysis):**
```bash
# Via Railway Dashboard:
# 1. Go to: https://railway.app/project/ism-report-analysis
# 2. Click "ism-report-analysis" service
# 3. Go to "Variables" tab
# 4. Check if SECRET_KEY exists and note its value
```

**For PI Backend Service (Portfolio Intelligence API):**
```bash
# Via Railway Dashboard:
# 1. Go to: https://railway.app/project/ism-report-analysis
# 2. Click "Portfolio Intelligence API" service
# 3. Go to "Variables" tab
# 4. Check if SECRET_KEY exists and note its value
```

### Step 2: Generate a Shared SECRET_KEY

```bash
# Generate a secure random key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 3: Set SECRET_KEY in Both Services

**CRITICAL:** Both services MUST have the **EXACT SAME** SECRET_KEY value.

**Via Railway Dashboard:**
1. Set in Flask service (ism-report-analysis):
   - Variable name: `SECRET_KEY`
   - Value: [paste the generated key]

2. Set in PI Backend service (Portfolio Intelligence API):
   - Variable name: `SECRET_KEY`
   - Value: [paste the SAME generated key]

### Step 4: Redeploy Both Services

After setting the variables, redeploy:
- Flask service will restart with new SECRET_KEY
- PI Backend will restart with matching SECRET_KEY
- JWT tokens will now validate correctly

---

## 🧪 Testing After Fix

1. Visit: https://envoyllc-ism.up.railway.app
2. Log in with Google OAuth
3. Click "Portfolio Intelligence" card
4. **Expected:** Should stay on PI page (not redirect to landing)
5. **Verify:** Check browser console for any errors
6. **Verify:** Check Railway logs for both services

---

## 📝 Current Railway Services

Based on the environment variables, you have:

1. **ism-report-analysis** (Flask)
   - Domain: envoyllc-ism.up.railway.app
   - Needs: SECRET_KEY env var

2. **Portfolio Intelligence API** (PI Backend)
   - Domain: portfolio-intelligence-api-production.up.railway.app
   - Needs: SECRET_KEY env var (MUST match Flask)

3. **Potfolio Intelligence Frontend**
   - Domain: potfolio-intelligence-frontend-production.up.railway.app
   - Doesn't need SECRET_KEY

---

## 🔒 Security Note

**Never commit SECRET_KEY to git!**
Keep it in Railway environment variables only.

---

## Alternative: Use Railway CLI

If you prefer CLI over web dashboard:

```bash
# Link to Flask service
railway link

# Set SECRET_KEY for Flask
railway variables --set SECRET_KEY="your-secret-key-here"

# Link to PI Backend service
railway link

# Set SAME SECRET_KEY for PI Backend
railway variables --set SECRET_KEY="your-secret-key-here"
```

---

## Next Steps

1. ✅ Generate SECRET_KEY
2. ✅ Set in both Railway services
3. ✅ Redeploy both services
4. ✅ Test login → Portfolio Intelligence flow
5. ✅ Verify no redirect to landing
