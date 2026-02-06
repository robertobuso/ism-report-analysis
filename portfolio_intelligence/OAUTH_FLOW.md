# Portfolio Intelligence - OAuth Flow Guide

## Overview

The Portfolio Intelligence app uses TradeStation OAuth for authentication. In **mock mode**, the OAuth screen is bypassed for easier testing.

## Flow Diagram

### Mock Mode (Testing)
```
User clicks "Connect to TradeStation"
    ↓
Frontend: window.location = "http://localhost:8000/api/v1/auth/login"
    ↓
Backend: Redirects directly to callback (skips OAuth screen)
    → http://localhost:8000/api/v1/auth/callback?code=mock_xxx&state=mock_state
    ↓
Backend: Creates/logs in user, generates JWT
    ↓
Backend: Redirects to frontend
    → http://localhost:3100/auth/callback?token=JWT_TOKEN&expires_in=3600
    ↓
Frontend: Extracts token, stores it, redirects to dashboard
```

### Real Mode (Production)
```
User clicks "Connect to TradeStation"
    ↓
Frontend: window.location = "http://localhost:8000/api/v1/auth/login"
    ↓
Backend: Redirects to TradeStation OAuth consent page
    → https://signin.tradestation.com/authorize?...
    ↓
User: Logs in to TradeStation, grants permissions
    ↓
TradeStation: Redirects back to callback
    → http://localhost:8000/api/v1/auth/callback?code=REAL_CODE&state=xxx
    ↓
Backend: Exchanges code for access/refresh tokens
Backend: Creates/logs in user, generates JWT
    ↓
Backend: Redirects to frontend
    → http://localhost:3100/auth/callback?token=JWT_TOKEN&expires_in=3600
    ↓
Frontend: Extracts token, stores it, redirects to dashboard
```

## Frontend Implementation

### 1. Login Button

```tsx
// In your login/landing page
const handleConnectTradeStation = () => {
  // Redirect to backend auth endpoint
  window.location.href = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/login`;
};

return (
  <button onClick={handleConnectTradeStation}>
    Connect to TradeStation
  </button>
);
```

### 2. Callback Page

Create a page at `/auth/callback` to handle the redirect:

```tsx
// app/auth/callback/page.tsx
'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function AuthCallback() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    // Extract token from URL
    const token = searchParams.get('token');
    const expiresIn = searchParams.get('expires_in');

    if (token) {
      // Store token (localStorage, cookie, or state management)
      localStorage.setItem('pi_auth_token', token);

      if (expiresIn) {
        const expiryTime = Date.now() + parseInt(expiresIn) * 1000;
        localStorage.setItem('pi_token_expiry', expiryTime.toString());
      }

      // Redirect to dashboard
      router.push('/dashboard');
    } else {
      // Error: no token received
      console.error('No token in callback');
      router.push('/login?error=auth_failed');
    }
  }, [searchParams, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h2 className="text-xl font-semibold mb-2">Authenticating...</h2>
        <p className="text-gray-600">Please wait while we log you in.</p>
      </div>
    </div>
  );
}
```

### 3. API Client with Auth

```tsx
// lib/api.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = {
  getAuthToken: () => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('pi_auth_token');
  },

  isTokenExpired: () => {
    if (typeof window === 'undefined') return true;
    const expiry = localStorage.getItem('pi_token_expiry');
    if (!expiry) return true;
    return Date.now() > parseInt(expiry);
  },

  async fetch(endpoint: string, options: RequestInit = {}) {
    const token = this.getAuthToken();

    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers,
    };

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // Token expired or invalid
      localStorage.removeItem('pi_auth_token');
      localStorage.removeItem('pi_token_expiry');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    return response;
  },

  // Convenience methods
  async get(endpoint: string) {
    const response = await this.fetch(endpoint);
    return response.json();
  },

  async post(endpoint: string, data: any) {
    const response = await this.fetch(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return response.json();
  },
};
```

### 4. Protected Routes

```tsx
// components/ProtectedRoute.tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [isAuthed, setIsAuthed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = apiClient.getAuthToken();

    if (!token || apiClient.isTokenExpired()) {
      router.push('/login');
      return;
    }

    // Optionally verify token with backend
    apiClient.get('/api/v1/auth/me')
      .then(() => {
        setIsAuthed(true);
        setIsLoading(false);
      })
      .catch(() => {
        router.push('/login');
      });
  }, [router]);

  if (isLoading) {
    return <div>Loading...</div>;
  }

  return isAuthed ? <>{children}</> : null;
}
```

## Environment Variables

### Development (.env.local)

```bash
# Mock mode - connects to local backend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Production (.env.production)

```bash
# Real mode - connects to deployed backend
NEXT_PUBLIC_API_URL=https://your-api.railway.app
```

## Testing the Flow

### 1. Start Backend (Mock Mode)

```bash
cd portfolio_intelligence/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Verify logs show:
# INFO: Using MOCK TradeStation client
```

### 2. Start Frontend

```bash
cd portfolio_intelligence/frontend
npm run dev
```

### 3. Test OAuth Flow

1. Navigate to login page
2. Click "Connect to TradeStation"
3. Should **instantly** redirect back (no OAuth screen in mock mode)
4. Should land on `/auth/callback?token=...`
5. Should extract token and redirect to dashboard

### 4. Verify Token Works

```tsx
// In your dashboard/portfolio pages
useEffect(() => {
  apiClient.get('/api/v1/portfolios')
    .then(data => console.log('Portfolios:', data))
    .catch(err => console.error('Error:', err));
}, []);
```

## Debugging

### Issue: Redirect loop
**Cause:** Frontend redirect URL doesn't match backend config
**Solution:** Check `FRONTEND_URL` in backend `.env` matches your frontend URL

```bash
# Backend .env
FRONTEND_URL=http://localhost:3100

# Frontend .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Issue: 401 Unauthorized on API calls
**Cause:** Token not being sent or expired
**Solution:** Check token is in localStorage and Authorization header is set

```tsx
console.log('Token:', localStorage.getItem('pi_auth_token'));
console.log('Expired?', apiClient.isTokenExpired());
```

### Issue: CORS errors
**Cause:** Backend CORS settings don't include frontend URL
**Solution:** Verify backend `app/main.py` has correct CORS origins

```python
# Should already be configured
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, settings.suite_url],  # Includes localhost:3100
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Mock vs Real Mode Differences

| Aspect | Mock Mode | Real Mode |
|--------|-----------|-----------|
| **OAuth Screen** | Skipped (instant redirect) | Real TradeStation login |
| **User Data** | Generic mock user | Real TradeStation account |
| **Setup Time** | Instant | Requires user login |
| **Token Validity** | JWT expires in 60 min | JWT expires in 60 min |
| **Refresh Token** | Mock (not functional) | Real (can refresh access) |

## Production Checklist

When switching to real TradeStation:

### Backend Changes
```bash
# portfolio_intelligence/backend/.env
USE_MOCK_TRADESTATION=false
TRADESTATION_CLIENT_ID=your_real_client_id
TRADESTATION_CLIENT_SECRET=your_real_client_secret
TRADESTATION_REDIRECT_URI=https://your-api.railway.app/api/v1/auth/callback
TRADESTATION_BASE_URL=https://api.tradestation.com/v3  # or sim-api for testing
FRONTEND_URL=https://your-frontend.railway.app
```

### Frontend Changes
```bash
# portfolio_intelligence/frontend/.env.production
NEXT_PUBLIC_API_URL=https://your-api.railway.app
```

### TradeStation Developer Settings
1. Log in to TradeStation Developer Portal
2. Configure OAuth redirect URI: `https://your-api.railway.app/api/v1/auth/callback`
3. Copy Client ID and Secret to backend `.env`

### Test in Production
1. Navigate to your deployed frontend
2. Click "Connect to TradeStation"
3. Should see **real TradeStation login screen**
4. Log in with TradeStation credentials
5. Grant permissions
6. Should redirect back to your app with token

---

**Current Status:** ✅ Mock mode working, ready for frontend integration
**Next Step:** When TradeStation approves → Update env vars → Production ready
