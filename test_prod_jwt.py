#!/usr/bin/env python3
"""
Test the actual JWT token from production.
This will tell us EXACTLY what's failing.
"""
import sys
import os
from jose import jwt, JWTError
from datetime import datetime

def test_jwt(token, secret_key):
    """Test JWT decode with detailed diagnostics."""
    print("=" * 80)
    print("🔬 JWT PRODUCTION DIAGNOSTICS")
    print("=" * 80)

    print(f"\n📊 Input Details:")
    print(f"   Token length: {len(token)}")
    print(f"   Token preview: {token[:30]}...{token[-30:]}")
    print(f"   Secret key length: {len(secret_key)}")
    print(f"   Secret key preview: {secret_key[:10]}...")

    # Try to decode without verification first (to see payload even if signature fails)
    print(f"\n🔓 Step 1: Decode WITHOUT verification (to see payload)...")
    try:
        unverified_payload = jwt.get_unverified_claims(token)
        print(f"   ✅ Unverified payload:")
        for key, value in unverified_payload.items():
            if key in ('iat', 'exp'):
                dt = datetime.fromtimestamp(value)
                print(f"      {key}: {value} ({dt})")
            else:
                print(f"      {key}: {value}")
    except Exception as e:
        print(f"   ❌ Failed to get unverified payload: {e}")
        return

    # Check expiration
    print(f"\n⏰ Step 2: Check expiration...")
    exp = unverified_payload.get('exp')
    if exp:
        now = datetime.utcnow().timestamp()
        if exp < now:
            print(f"   ❌ TOKEN IS EXPIRED!")
            print(f"      Expired at: {datetime.fromtimestamp(exp)}")
            print(f"      Current time: {datetime.fromtimestamp(now)}")
            print(f"      Expired {(now - exp)/60:.1f} minutes ago")
        else:
            print(f"   ✅ Token is NOT expired")
            print(f"      Expires in: {(exp - now)/60:.1f} minutes")
    else:
        print(f"   ⚠️  No expiration claim found")

    # Try to decode WITH verification
    print(f"\n🔐 Step 3: Decode WITH verification (validate signature)...")
    try:
        verified_payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        print(f"   ✅ JWT SIGNATURE IS VALID!")
        print(f"   ✅ Payload verified:")
        for key, value in verified_payload.items():
            print(f"      {key}: {value}")
    except JWTError as e:
        print(f"   ❌ JWT VERIFICATION FAILED!")
        print(f"      Error type: {type(e).__name__}")
        print(f"      Error message: {e}")
        print(f"\n   🔍 This means:")
        if "expired" in str(e).lower():
            print(f"      - Token has EXPIRED")
        elif "signature" in str(e).lower():
            print(f"      - SECRET_KEY is WRONG or token was signed with different key")
        else:
            print(f"      - {e}")
        return

    # Check required claims
    print(f"\n✅ Step 4: Check required claims...")
    has_email = 'email' in verified_payload
    has_sub = 'sub' in verified_payload

    if has_email:
        print(f"   ✅ Has 'email' claim: {verified_payload['email']}")
        print(f"      This is a FLASK-issued token")
    elif has_sub:
        print(f"   ✅ Has 'sub' claim: {verified_payload['sub']}")
        print(f"      This is a TRADESTATION-issued token")
    else:
        print(f"   ❌ Missing BOTH 'email' and 'sub' claims!")
        print(f"      Token is invalid for this application")

    print(f"\n" + "=" * 80)
    print(f"🎯 CONCLUSION:")
    print(f"=" * 80)
    if has_email or has_sub:
        print(f"✅ JWT IS VALID - The problem is likely in database/user creation")
    else:
        print(f"❌ JWT IS INVALID - The problem is in JWT generation or validation")
    print(f"=" * 80)


if __name__ == "__main__":
    print("\n🔬 JWT Production Tester")
    print("\nThis will test the ACTUAL JWT token from production.")
    print("\n" + "=" * 80)

    # Get inputs
    print("\n📋 Step 1: Get the JWT token")
    print("   1. Open browser to: https://envoyllc-ism.up.railway.app")
    print("   2. Log in with Google")
    print("   3. Open DevTools Console (F12)")
    print("   4. Type: localStorage.getItem('token')")
    print("   5. Copy the token (without quotes)")
    print("")

    if len(sys.argv) > 1:
        token = sys.argv[1]
        print(f"✅ Using token from command line argument")
    else:
        token = input("Paste JWT token here: ").strip().strip('"').strip("'")

    if not token:
        print("❌ No token provided!")
        sys.exit(1)

    print("\n📋 Step 2: Get the SECRET_KEY from Railway")
    print("   1. Go to: https://railway.app/project/ism-report-analysis")
    print("   2. Click 'Portfolio Intelligence API' service")
    print("   3. Click 'Variables' tab")
    print("   4. Copy the SECRET_KEY value")
    print("")

    if len(sys.argv) > 2:
        secret_key = sys.argv[2]
        print(f"✅ Using SECRET_KEY from command line argument")
    else:
        secret_key = input("Paste SECRET_KEY here: ").strip().strip('"').strip("'")

    if not secret_key:
        print("❌ No SECRET_KEY provided!")
        sys.exit(1)

    # Run test
    test_jwt(token, secret_key)
