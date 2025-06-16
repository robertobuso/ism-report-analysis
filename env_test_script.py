#!/usr/bin/env python3
"""
Environment Variables Test Script
Check if all API keys are properly loaded
"""

import os

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ python-dotenv loaded successfully")
except ImportError:
    print("❌ python-dotenv not installed")
    print("💡 Install with: pip install python-dotenv")
except Exception as e:
    print(f"❌ Error loading dotenv: {e}")

print("\n🔍 CHECKING API KEYS")
print("=" * 40)

# Check all the API keys
api_keys = {
    'OPENAI_API_KEY': 'OpenAI (required)',
    'NYTIMES_API_KEY': 'New York Times API',
    'ALPHAVANTAGE_API_KEY': 'AlphaVantage Premium',
    'GOOGLE_CUSTOM_SEARCH_API_KEY': 'Google Custom Search',
    'GOOGLE_SEARCH_ENGINE_ID': 'Google Search Engine ID',
    'REUTERS_API_KEY': 'Reuters API (optional)'
}

found_keys = 0
total_keys = len(api_keys)

for key_name, description in api_keys.items():
    value = os.getenv(key_name)
    if value:
        # Show first 8 and last 4 characters for security
        if len(value) > 12:
            masked_value = f"{value[:8]}...{value[-4:]}"
        else:
            masked_value = "***"
        print(f"✅ {key_name}: {masked_value} ({description})")
        found_keys += 1
    else:
        print(f"❌ {key_name}: NOT FOUND ({description})")

print(f"\n📊 SUMMARY: {found_keys}/{total_keys} API keys found")

if found_keys == 0:
    print("\n🚨 NO API KEYS FOUND!")
    print("This means either:")
    print("1. You don't have a .env file")
    print("2. Your .env file is in the wrong location")
    print("3. python-dotenv is not installed")
    print("4. Your environment variables are set differently")
    
    print("\n🔧 TROUBLESHOOTING:")
    print("1. Check if .env file exists: ls -la .env")
    print("2. Install python-dotenv: pip install python-dotenv")
    print("3. Create .env file with your API keys")
    
elif found_keys < 3:
    print("\n⚠️  LIMITED API KEYS")
    print("You have some keys but missing others.")
    print("The system will work but with reduced functionality.")
    
else:
    print("\n🎉 GOOD API KEY COVERAGE!")
    print("You have enough API keys for premium analysis.")

# Test if we can access the keys the same way the app does
print("\n🧪 TESTING API KEY ACCESS")
print("=" * 40)

nyt_key = os.getenv("NYTIMES_API_KEY")
if nyt_key:
    print(f"✅ NYT API key accessible: {len(nyt_key)} characters")
    
    # Quick test of NYT API
    import requests
    test_url = f"https://api.nytimes.com/svc/search/v2/articlesearch.json?q=test&api-key={nyt_key}"
    try:
        response = requests.get(test_url, timeout=5)
        if response.status_code == 200:
            print("✅ NYT API key works!")
        elif response.status_code == 401:
            print("❌ NYT API key invalid")
        elif response.status_code == 429:
            print("⚠️  NYT API rate limited")
        else:
            print(f"⚠️  NYT API returned: {response.status_code}")
    except Exception as e:
        print(f"⚠️  NYT API test failed: {e}")
else:
    print("❌ NYT API key not accessible")

alphavantage_key = os.getenv("ALPHAVANTAGE_API_KEY")
if alphavantage_key:
    print(f"✅ AlphaVantage key accessible: {len(alphavantage_key)} characters")
else:
    print("❌ AlphaVantage key not accessible")

print("\n🎯 NEXT STEPS:")
if found_keys >= 2:
    print("1. Your environment setup looks good!")
    print("2. Restart your Flask app to pick up the changes")
    print("3. Test your news analysis again")
else:
    print("1. Fix missing API keys in your .env file")
    print("2. Install python-dotenv if needed")
    print("3. Restart your application")