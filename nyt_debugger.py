#!/usr/bin/env python3
"""
NYT API Debugger - Find out why NYT is returning 0 articles
"""

import os
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_nyt_api():
    """Test NYT API with different configurations."""
    
    api_key = os.getenv("NYTIMES_API_KEY")
    if not api_key:
        print("❌ NYT_API_KEY environment variable not found")
        return
    
    print(f"🔑 Using API key: {api_key[:8]}...{api_key[-4:]}")
    print()
    
    base_url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
    
    # Test 1: Exact same query as browser (simplest)
    print("TEST 1: Simple browser-like query")
    print("-" * 40)
    
    simple_params = {
        "q": "AAPL",
        "api-key": api_key
    }
    
    try:
        response = requests.get(base_url, params=simple_params, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response status: {data.get('status', 'Unknown')}")
            
            docs = data.get("response", {}).get("docs", [])
            print(f"Total articles found: {len(docs)}")
            
            if docs:
                print("\nSample articles:")
                for i, doc in enumerate(docs[:3]):
                    title = doc.get("headline", {}).get("main", "No title")
                    section = doc.get("section_name", "No section")
                    date = doc.get("pub_date", "No date")
                    print(f"  {i+1}. {title[:60]}...")
                    print(f"     Section: {section}, Date: {date[:10]}")
            else:
                print("❌ No articles found even with simple query")
                
        elif response.status_code == 401:
            print("❌ 401 Unauthorized - Invalid API key")
            return
        elif response.status_code == 429:
            print("❌ 429 Rate Limited - Try again later")
            return
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text[:200])
            return
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return
    
    print("\n" + "="*50)
    
    # Test 2: Query with date range (last 7 days)
    print("TEST 2: Query with date range (last 7 days)")
    print("-" * 40)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    date_params = {
        "q": "AAPL",
        "begin_date": start_date.strftime("%Y%m%d"),
        "end_date": end_date.strftime("%Y%m%d"),
        "sort": "newest",
        "api-key": api_key
    }
    
    try:
        response = requests.get(base_url, params=date_params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            docs = data.get("response", {}).get("docs", [])
            print(f"Articles in last 7 days: {len(docs)}")
            
            if len(docs) == 0:
                print("❌ No articles in last 7 days - try longer period")
                
                # Test with 30 days
                start_date_30 = end_date - timedelta(days=30)
                date_params_30 = date_params.copy()
                date_params_30["begin_date"] = start_date_30.strftime("%Y%m%d")
                
                response_30 = requests.get(base_url, params=date_params_30, timeout=10)
                if response_30.status_code == 200:
                    data_30 = response_30.json()
                    docs_30 = data_30.get("response", {}).get("docs", [])
                    print(f"Articles in last 30 days: {len(docs_30)}")
                    
        else:
            print(f"❌ Date query failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Date query error: {e}")
    
    print("\n" + "="*50)
    
    # Test 3: Try different search terms
    print("TEST 3: Try different search terms")
    print("-" * 40)
    
    test_queries = ["Apple", "Apple Inc", "Apple stock", "AAPL stock"]
    
    for query in test_queries:
        try:
            test_params = {
                "q": query,
                "api-key": api_key,
                "sort": "newest"
            }
            
            response = requests.get(base_url, params=test_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                docs = data.get("response", {}).get("docs", [])
                print(f"Query '{query}': {len(docs)} articles")
            else:
                print(f"Query '{query}': Failed ({response.status_code})")
                
        except Exception as e:
            print(f"Query '{query}': Error - {e}")
    
    print("\n🎯 RECOMMENDATIONS:")
    print("1. If simple query works but date-filtered doesn't:")
    print("   → Remove date filtering from your code")
    print("2. If no queries work:")
    print("   → Check your API key at https://developer.nytimes.com/my-apps")
    print("3. If different search terms work better:")
    print("   → Use 'Apple' instead of 'AAPL' in your queries")

if __name__ == "__main__":
    test_nyt_api()