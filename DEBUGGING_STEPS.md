# 🔬 Systematic Debugging - No More Guessing

## Step 1: Check Browser Network Tab

1. Open Chrome/Firefox in **Incognito mode**
2. Open DevTools (F12 or Cmd+Option+I)
3. Go to **Network** tab
4. Visit: https://envoyllc-ism.up.railway.app
5. Log in with Google
6. Click "Portfolio Intelligence"
7. **IMMEDIATELY check Network tab**

### What to Look For:

**Find the request to:** `/api/v1/auth/me`

**Check:**
- Status code (should be 401 if failing)
- Request Headers → Look for `Authorization: Bearer ...`
- Response body → What's the actual error message?
- Response Headers

**Copy and paste:**
1. The full URL of the request
2. The status code
3. The response body (error message)
4. The Authorization header value (just first/last 20 chars)

---

## Step 2: Check Railway Logs RIGHT NOW

While you have the error happening:

1. Go to: https://railway.app/project/ism-report-analysis
2. Click **"Portfolio Intelligence API"** service
3. Click **"Logs"** tab at the top
4. **Keep it open** and refresh your browser
5. Try to access Portfolio Intelligence again
6. **Watch the logs in real-time**

**Copy the EXACT error message** that appears when you try to access PI

---

## Step 3: Test the Debug Endpoint

Copy the JWT token from the browser (from localStorage or Network tab), then test:

```bash
# Get the token from browser console:
# 1. Open browser console (F12 → Console tab)
# 2. Type: localStorage.getItem('token')
# 3. Copy the token value

# Then test the debug endpoint:
curl "https://portfolio-intelligence-api-production.up.railway.app/api/v1/auth/debug/jwt?token=PASTE_TOKEN_HERE"
```

This will tell us if the JWT is valid or not, without touching the database.

---

## Step 4: Check Flask JWT Generation

Open browser console on https://envoyllc-ism.up.railway.app after login:

```javascript
// Check what's in the session
console.log('JWT Token:', localStorage.getItem('token'));

// Check if token is in URL
console.log('URL:', window.location.href);
```

---

## Step 5: Verify Environment Variables

Go to Railway Dashboard:

**For Flask Service (ism-report-analysis):**
1. Click service → Variables tab
2. Verify `SECRET_KEY` is set
3. Copy first 10 characters

**For PI Backend (Portfolio Intelligence API):**
1. Click service → Variables tab
2. Verify `SECRET_KEY` is set
3. Copy first 10 characters
4. **VERIFY they match**

---

## What I Need From You

Please run through these steps and give me:

1. ✅ **Browser Network Tab**: Status code + error message from `/api/v1/auth/me`
2. ✅ **Railway Logs**: Exact error message when you access PI
3. ✅ **Debug Endpoint Result**: Output from the debug endpoint
4. ✅ **SECRET_KEY Verification**: First 10 chars from both services

This will give us REAL DATA instead of guessing.

---

## Quick Railway Logs Access

If Railway CLI works for you:

```bash
# Link to PI Backend service
railway link

# Watch logs in real-time
railway logs --follow
```

Then in another terminal, try to access Portfolio Intelligence and watch the logs.
