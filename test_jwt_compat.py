#!/usr/bin/env python3
"""
Test JWT compatibility between PyJWT (Flask) and python-jose (PI backend)
"""
from datetime import datetime, timedelta
import jwt as pyjwt  # PyJWT
from jose import jwt as jose_jwt  # python-jose

# Test with a shared secret
SECRET_KEY = "test-secret-key-12345"

# Generate JWT using PyJWT (like Flask does)
print("=" * 60)
print("Testing JWT Compatibility")
print("=" * 60)

payload = {
    'email': 'test@example.com',
    'iat': datetime.utcnow(),
    'exp': datetime.utcnow() + timedelta(hours=24)
}

# Encode with PyJWT
pyjwt_token = pyjwt.encode(payload, SECRET_KEY, algorithm='HS256')
print(f"\n✅ PyJWT Token Generated:")
print(f"   {pyjwt_token[:50]}...")
print(f"   Type: {type(pyjwt_token)}")

# Try to decode with python-jose
try:
    decoded = jose_jwt.decode(pyjwt_token, SECRET_KEY, algorithms=['HS256'])
    print(f"\n✅ python-jose Successfully Decoded:")
    print(f"   Email: {decoded.get('email')}")
    print(f"   iat: {decoded.get('iat')}")
    print(f"   exp: {decoded.get('exp')}")
    print(f"\n🎉 PyJWT and python-jose are COMPATIBLE!")
except Exception as e:
    print(f"\n❌ python-jose Failed to Decode:")
    print(f"   Error: {type(e).__name__}: {e}")
    print(f"\n⚠️  PyJWT and python-jose are NOT COMPATIBLE!")

print("\n" + "=" * 60)
print("Conclusion:")
print("=" * 60)
print("If compatible: The issue is SECRET_KEY mismatch in Railway")
print("If not compatible: Need to switch Flask to use python-jose")
print("=" * 60)
