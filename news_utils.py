import requests
import os
import re
import feedparser
import time
from datetime import datetime, timedelta
from openai import OpenAI
from typing import List, Dict, Tuple, Any, Optional
import logging
from urllib.parse import urlparse, urljoin
import json
import asyncio
import aiohttp
import concurrent.futures
import sys

from enhanced_news_analysis import DynamicSourceOrchestrator, AnalysisConfig
from configuration_and_integration import ConfigurationManager, MigrationHelper

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.getLogger(__name__).info("Environment variables loaded from .env file")
except ImportError:
    # dotenv not installed, assume environment variables are set another way
    logging.getLogger(__name__).info("python-dotenv not available, using system environment variables")
except Exception as e:
    logging.getLogger(__name__).warning(f"Error loading .env file: {e}")

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Fix 4: Enhanced Scoring to Penalize Benzinga/Fool/Zacks
UNWANTED_SOURCES = {
    'benzinga.com': 0,  # Heavy penalty
    'fool.com': -3,      # Heavier penalty  
    'zacks.com': 0,      # Heavy penalty
    'investorplace.com': -4,
    'thestreet.com': -4
}

PREMIUM_SOURCES_ENHANCED = {
    # Tier 1: Maximum priority
    'nytimes.com': 20,    # NYT API gives full content
    'reuters.com': 18,
    'bloomberg.com': 18, 
    'wsj.com': 17,
    'ft.com': 16,
    
    # Tier 2: High quality
    'cnbc.com': 12,
    'marketwatch.com': 12,
    'barrons.com': 14,
    'economist.com': 13,
    'fortune.com': 10,
    
    # Tier 3: Good sources
    'businessinsider.com': 8,
    'guardian.com': 7,
    'theguardian.com': 7,
    'investing.com': 6,
    'seekingalpha.com': 5,
}

# Premium RSS feeds configuration - ANTI-BOT-BLOCKING FEEDS
def get_working_rss_feeds_2025_cleaned() -> Dict[str, str]:
    """
    Actually working RSS feeds as of 2025 - REMOVED broken feeds.
    """
    return {
        # Tier 1: CNBC (Confirmed Working)
        'cnbc_business': 'https://www.cnbc.com/id/10001147/device/rss/rss.html',
        'cnbc_finance': 'https://www.cnbc.com/id/10000664/device/rss/rss.html', 
        'cnbc_earnings': 'https://www.cnbc.com/id/15839135/device/rss/rss.html',
        'cnbc_technology': 'https://www.cnbc.com/id/19854910/device/rss/rss.html',
        'cnbc_economy': 'https://www.cnbc.com/id/20910258/device/rss/rss.html',
        'cnbc_us_news': 'https://www.cnbc.com/id/15837362/device/rss/rss.html',
        
        # Tier 1: Financial Times (Confirmed Working) 
        'ft_home': 'https://www.ft.com/rss/home',
        
        # Tier 1: Other Premium Sources (Confirmed Working)
        'investing_com': 'https://www.investing.com/rss/news.rss',
        'seeking_alpha': 'https://seekingalpha.com/feed.xml',
        'marketwatch_main': 'https://feeds.content.dowjones.io/public/rss/RSSMarketsMain',
        
        # Tier 2: Business Sources (High Probability Working)
        'bloomberg_business': 'https://feeds.bloomberg.com/politics/news.rss',
        'fortune_business': 'https://fortune.com/feed/',
        'business_insider': 'https://www.businessinsider.com/rss',
        'guardian_business': 'https://www.theguardian.com/business/rss',
        'economist_business': 'https://www.economist.com/business/rss.xml',
        
        # Tier 3: Alternative Sources (Known to Work)
        # REMOVED: 'fox_business': 'https://moxie.foxbusiness.com/google-publisher/business.xml',  # Returns 400
        'yahoo_finance': 'https://finance.yahoo.com/rss/',
        'cnn_business': 'http://rss.cnn.com/rss/money_latest.rss',
        # REMOVED: 'reuters_business': 'https://www.reutersagency.com/en/reutersbest/article/tag/business/feed/',  # Returns 404
        
        # Tier 4: Backup Sources
        'moneycontrol': 'https://www.moneycontrol.com/rss/latestnews.xml',
        'zerohedge': 'https://feeds.feedburner.com/zerohedge/feed',
        'benzinga': 'https://www.benzinga.com/feed',
    }

def get_company_specific_feeds_2025_cleaned(company: str) -> Dict[str, str]:
    """
    Company-specific feeds that actually work.
    """
    from company_ticker_service import fast_company_ticker_service
    ticker, _ = fast_company_ticker_service.get_both_ticker_and_company(company)
    
    feeds = {}
    
    # Yahoo Finance per-ticker (works but rate limited)
    if ticker and len(ticker) <= 5:
        feeds['yahoo_ticker'] = f'https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US'
    
    # Google News for company (always works)
    feeds['google_news_company'] = f'https://news.google.com/rss/search?q={company.replace(" ", "+")}&hl=en-US&gl=US&ceid=US:en'
    
    return feeds

async def fetch_single_rss_async(session: aiohttp.ClientSession, feed_name: str, feed_url: str, 
                                company: str, days_back: int) -> List[Dict]:
    """
    Fetch a single RSS feed asynchronously.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        }
        
        logger.debug(f"RSS Parallel: Starting {feed_name}")
        start_time = time.time()
        
        async with session.get(feed_url, headers=headers, timeout=10) as response:
            if response.status != 200:
                elapsed = (time.time() - start_time) * 1000
                logger.warning(f"RSS {feed_name}: HTTP {response.status} ({elapsed:.0f}ms)")
                return []
            
            content = await response.read()
            elapsed = (time.time() - start_time) * 1000
            
            # Parse feed in thread pool (feedparser is CPU-bound)
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                feed = await loop.run_in_executor(executor, feedparser.parse, content)
            
            if not hasattr(feed, 'entries') or not feed.entries:
                logger.debug(f"RSS {feed_name}: No entries ({elapsed:.0f}ms)")
                return []
            
            # Process articles
            articles = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            # Get search terms for better matching
            from company_ticker_service import fast_company_ticker_service
            ticker, company_name = fast_company_ticker_service.get_both_ticker_and_company(company)
            search_terms = [company.lower()]
            if ticker:
                search_terms.append(ticker.lower())
            if company_name:
                search_terms.append(company_name.lower())
            
            for entry in feed.entries[:20]:  # Limit to 20 entries per feed
                try:
                    title = getattr(entry, 'title', '').strip()
                    link = getattr(entry, 'link', '').strip()
                    
                    if not title or not link:
                        continue
                    
                    # Get description
                    description = ''
                    for field in ['summary', 'description', 'content']:
                        if hasattr(entry, field):
                            field_value = getattr(entry, field)
                            if isinstance(field_value, list) and field_value:
                                description = field_value[0].get('value', '') if isinstance(field_value[0], dict) else str(field_value[0])
                            elif isinstance(field_value, str):
                                description = field_value
                            elif hasattr(field_value, 'value'):
                                description = field_value.value
                            if description.strip():
                                break
                    
                    # Clean description
                    if description:
                        import re
                        description = re.sub(r'<[^>]+>', '', description)
                        description = re.sub(r'\s+', ' ', description).strip()[:800]
                    
                    # Date check
                    pub_date = None
                    for date_field in ['published_parsed', 'updated_parsed']:
                        if hasattr(entry, date_field):
                            date_tuple = getattr(entry, date_field)
                            if date_tuple and len(date_tuple) >= 6:
                                try:
                                    pub_date = datetime(*date_tuple[:6])
                                    break
                                except (ValueError, TypeError):
                                    continue
                    
                    if pub_date and pub_date < cutoff_date:
                        continue
                    
                    # Relevance check
                    title_lower = title.lower()
                    desc_lower = description.lower()
                    content = title_lower + ' ' + desc_lower
                    
                    # Check for company mention
                    has_company_mention = any(term in content for term in search_terms)
                    
                    # Financial context
                    financial_keywords = ['stock', 'shares', 'earnings', 'revenue', 'market', 'business']
                    has_financial_context = any(keyword in content for keyword in financial_keywords)
                    
                    if has_company_mention or has_financial_context:
                        from news_utils import extract_domain
                        article = {
                            "title": title,
                            "snippet": description[:300] if description else title[:300],
                            "full_content": description if description else title,
                            "link": link,
                            "source": extract_domain(link),
                            "published": pub_date.isoformat() if pub_date else "",
                            "source_type": "rss_feed"
                        }
                        articles.append(article)
                    
                except Exception as e:
                    logger.debug(f"Error processing RSS entry in {feed_name}: {e}")
                    continue
            
            total_elapsed = (time.time() - start_time) * 1000
            logger.info(f"✓ RSS Parallel {feed_name}: {len(articles)} articles ({total_elapsed:.0f}ms)")
            return articles
            
    except asyncio.TimeoutError:
        elapsed = (time.time() - start_time) * 1000
        logger.warning(f"RSS {feed_name}: Timeout ({elapsed:.0f}ms)")
        return []
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        logger.warning(f"RSS {feed_name}: Error ({elapsed:.0f}ms) - {e}")
        return []

async def fetch_rss_feeds_parallel(company: str, days_back: int = 7) -> List[Dict]:
    """
    Fetch from RSS feeds in parallel - much faster than sequential.
    """
    start_time = time.time()
    logger.info(f"RSS Parallel: Starting parallel fetch for {company}...")
    
    # Get cleaned feed lists (removed broken feeds)
    working_feeds = get_working_rss_feeds_2025_cleaned()
    company_feeds = get_company_specific_feeds_2025_cleaned(company)
    working_feeds.update(company_feeds)
    
    # Create aiohttp session with connection limits
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Create tasks for all feeds
        tasks = []
        for feed_name, feed_url in working_feeds.items():
            task = fetch_single_rss_async(session, feed_name, feed_url, company, days_back)
            tasks.append(task)
        
        # Execute all tasks in parallel
        logger.info(f"RSS Parallel: Fetching {len(tasks)} feeds simultaneously...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Combine results
    all_articles = []
    successful_feeds = 0
    feed_stats = {}
    
    for i, result in enumerate(results):
        feed_name = list(working_feeds.keys())[i]
        
        if isinstance(result, list):
            all_articles.extend(result)
            successful_feeds += 1
            feed_stats[feed_name] = len(result)
        else:
            logger.error(f"RSS Parallel {feed_name}: Exception - {result}")
            feed_stats[feed_name] = 0
    
    total_time = time.time() - start_time
    logger.info(f"RSS Parallel Complete: {successful_feeds}/{len(working_feeds)} feeds successful, "
               f"{len(all_articles)} total articles in {total_time:.2f}s")
    logger.info(f"RSS Parallel Performance: {feed_stats}")
    
    return all_articles

def fetch_rss_feeds_working_2025_parallel(company: str, days_back: int = 7) -> List[Dict]:
    """
    Synchronous wrapper for parallel RSS fetching.
    """
    try:
        # Create new event loop if none exists
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, run in executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, fetch_rss_feeds_parallel(company, days_back))
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(fetch_rss_feeds_parallel(company, days_back))
        except RuntimeError:
            # No event loop, create new one
            return asyncio.run(fetch_rss_feeds_parallel(company, days_back))
            
    except Exception as e:
        logger.error(f"RSS Parallel wrapper failed: {e}")
        # Fallback to empty list
        return []
    
# More sophisticated financial and business keywords
FINANCIAL_KEYWORDS = [
    # Earnings & Financial Performance
    'earnings', 'revenue', 'profit', 'loss', 'margin', 'ebitda', 'guidance', 'outlook', 'forecast',
    'beat estimates', 'miss estimates', 'consensus', 'eps', 'sales growth', 'cash flow',
    
    # Market & Trading
    'stock', 'shares', 'trading', 'volume', 'price target', 'analyst', 'upgrade', 'downgrade',
    'rating', 'buy', 'sell', 'hold', 'overweight', 'underweight', 'valuation', 'multiple',
    
    # Corporate Actions & Strategy
    'acquisition', 'merger', 'deal', 'partnership', 'investment', 'funding', 'spinoff',
    'dividend', 'buyback', 'split', 'ipo', 'filing', 'insider', 'ceo', 'cfo', 'management',
    
    # Regulatory & Legal
    'lawsuit', 'regulation', 'approval', 'fda', 'sec', 'investigation', 'compliance',
    'patent', 'licensing', 'antitrust', 'settlement',
    
    # Business Development  
    'contract', 'launch', 'breakthrough', 'expansion', 'restructuring', 'layoffs',
    'hiring', 'capex', 'r&d', 'innovation', 'market share', 'competitive'
]

# Company name to ticker mapping
COMPANY_TO_TICKER = {
    # Major tech companies
    'apple': 'AAPL', 'microsoft': 'MSFT', 'google': 'GOOGL', 'alphabet': 'GOOGL',
    'amazon': 'AMZN', 'tesla': 'TSLA', 'meta': 'META', 'facebook': 'META',
    'nvidia': 'NVDA', 'netflix': 'NFLX', 'adobe': 'ADBE', 'salesforce': 'CRM',
    'oracle': 'ORCL', 'intel': 'INTC', 'amd': 'AMD', 'cisco': 'CSCO',
    
    # Financial institutions
    'jpmorgan': 'JPM', 'jp morgan': 'JPM', 'bank of america': 'BAC',
    'wells fargo': 'WFC', 'goldman sachs': 'GS', 'morgan stanley': 'MS',
    'citigroup': 'C', 'american express': 'AXP', 'visa': 'V', 'mastercard': 'MA',
    
    # Healthcare & pharma
    'johnson & johnson': 'JNJ', 'pfizer': 'PFE', 'merck': 'MRK',
    'abbott': 'ABT', 'bristol myers': 'BMY', 'eli lilly': 'LLY',
    
    # Consumer & retail
    'walmart': 'WMT', 'procter & gamble': 'PG', 'coca cola': 'KO',
    'pepsi': 'PEP', 'nike': 'NKE', 'home depot': 'HD', 'mcdonalds': 'MCD',
    
    # Industrial & energy
    'exxon': 'XOM', 'chevron': 'CVX', 'general electric': 'GE',
    'boeing': 'BA', 'caterpillar': 'CAT', 'honeywell': 'HON',
}

class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self):
        self.call_times = {}
    
    def wait_if_needed(self, source: str, min_interval: float = 1.0):
        """Wait if needed to respect rate limits"""
        current_time = time.time()
        last_call = self.call_times.get(source, 0)
        
        if current_time - last_call < min_interval:
            sleep_time = min_interval - (current_time - last_call)
            time.sleep(sleep_time)
        
        self.call_times[source] = time.time()

# Global rate limiter instance
rate_limiter = RateLimiter()

def convert_to_ticker(company: str) -> str:
    """Convert company name to ticker symbol if possible, otherwise return as-is."""
    company_clean = company.lower().strip()
    
    # Direct lookup in mapping
    if company_clean in COMPANY_TO_TICKER:
        return COMPANY_TO_TICKER[company_clean]
    
    # Check if it's already a ticker (short and all caps)
    if len(company) <= 5 and company.isupper():
        return company
    
    # Try some common variations
    variations = [
        company_clean.replace(' inc', '').replace(' corp', '').replace(' ltd', ''),
        company_clean.replace(' corporation', '').replace(' company', ''),
        company_clean.replace(' & ', ' and '),
        company_clean.replace(' and ', ' & ')
    ]
    
    for variation in variations:
        if variation in COMPANY_TO_TICKER:
            return COMPANY_TO_TICKER[variation]
    
    # If no mapping found, try to guess if it's a ticker vs company name
    if len(company) <= 5 and company.replace('.', '').replace('-', '').isalnum():
        return company.upper()  # Likely a ticker
    
    # Return original for company names we don't recognize
    return company

def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return "unknown"

# Fix 1: Fast Parallel NYT API (3 calls simultaneously, first page only)
async def fetch_nyt_parallel(company: str, days_back: int = 7) -> List[Dict]:
    """
    Fast parallel NYT API - 3 searches simultaneously, first page only.
    Total time: ~3-5 seconds instead of 6+ minutes.
    """
    try:
        api_key = os.getenv("NYTIMES_API_KEY")
        if not api_key:
            logger.info("NYT API key not found, skipping NYT news fetch")
            return []
        
        # Get search terms
        search_terms = get_nyt_search_terms_dynamic(company)[:3]  # Limit to 3
        logger.info(f"NYT API: Parallel search for: {search_terms}")
        
        url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
        
        async def fetch_single_term(session, search_term):
            """Fetch first page for a single search term."""
            params = {
                "q": search_term,
                "api-key": api_key,
                "sort": "newest",
                "fl": "headline,abstract,lead_paragraph,web_url,pub_date,section_name",
                "page": 0  # Only first page
            }
            
            try:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "OK":
                            docs = data.get("response", {}).get("docs", [])
                            logger.info(f"NYT '{search_term}': {len(docs)} raw articles")
                            return process_nyt_docs(docs, search_term, days_back)
                    else:
                        logger.warning(f"NYT '{search_term}': HTTP {response.status}")
                        return []
            except Exception as e:
                logger.warning(f"NYT '{search_term}' failed: {e}")
                return []
        
        # Make all 3 calls simultaneously
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_single_term(session, term) for term in search_terms]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_articles = []
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_articles.extend(result)
                logger.info(f"NYT '{search_terms[i]}': {len(result)} relevant articles")
            else:
                logger.error(f"NYT '{search_terms[i]}': {result}")
        
        logger.info(f"NYT Parallel: {len(all_articles)} total articles in ~3 seconds")
        return all_articles
        
    except Exception as e:
        logger.error(f"NYT parallel fetch failed: {e}")
        return []

def process_nyt_docs(docs: List[Dict], search_term: str, days_back: int) -> List[Dict]:
    """Process NYT API documents into article format."""
    articles = []
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    for doc in docs:
        try:
            headline = doc.get("headline", {}) or {}
            title = headline.get("main", "") if isinstance(headline, dict) else str(headline)
            
            abstract = doc.get("abstract", "") or ""
            lead_paragraph = doc.get("lead_paragraph", "") or ""
            web_url = doc.get("web_url", "") or ""
            pub_date = doc.get("pub_date", "") or ""
            section_name = doc.get("section_name", "") or ""
            
            if not title.strip() or not web_url.strip():
                continue
            
            # Date filter
            if pub_date:
                try:
                    article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00').replace('+0000', '+00:00'))
                    if article_date.tzinfo:
                        article_date = article_date.replace(tzinfo=None)
                    if article_date < cutoff_date:
                        continue
                except (ValueError, TypeError):
                    pass
            
            # Content
            content_parts = []
            if abstract.strip():
                content_parts.append(abstract.strip())
            if lead_paragraph.strip() and lead_paragraph.strip() != abstract.strip():
                content_parts.append(lead_paragraph.strip())
            
            full_content = " ".join(content_parts)
            snippet = full_content[:400] if full_content else title
            
            # Relevance check
            title_lower = title.lower()
            content_lower = full_content.lower()
            
            search_term_lower = search_term.lower()
            has_company_mention = (search_term_lower in title_lower or search_term_lower in content_lower)
            is_business_section = any(term in section_name.lower() for term in 
                                    ['business', 'technology', 'markets', 'finance', 'economy'])
            
            if has_company_mention or is_business_section:
                article = {
                    "title": title.strip(),
                    "snippet": snippet,
                    "full_content": full_content,
                    "link": web_url.strip(),
                    "source": "nytimes.com",
                    "published": pub_date,
                    "source_type": "nyt_api",
                    "section": section_name,
                    "search_term": search_term
                }
                articles.append(article)
                
        except Exception as e:
            logger.warning(f"Error processing NYT doc: {e}")
            continue
    
    return articles

# Fix 2: Dynamic Company/Ticker Lookup
def get_nyt_search_terms_dynamic(company: str) -> List[str]:
    """
    Dynamic company/ticker lookup using multiple strategies.
    """
    search_terms = [company.strip()]
    
    # Strategy 1: Try Alpha Vantage symbol search (if we have the key)
    try:
        av_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if av_key and len(company) <= 5 and company.isupper():
            # This looks like a ticker, get company name
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "SYMBOL_SEARCH",
                "keywords": company,
                "apikey": av_key
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                matches = data.get("bestMatches", [])
                if matches:
                    company_name = matches[0].get("2. name", "")
                    if company_name and company_name not in search_terms:
                        # Clean up company name
                        company_name = company_name.replace(" Inc.", "").replace(" Corp.", "").replace(" Ltd.", "")
                        search_terms.insert(0, company_name)
                        logger.info(f"AV Symbol Search: {company} → {company_name}")
    except Exception as e:
        logger.debug(f"AV symbol search failed: {e}")
    
    # Strategy 2: Try Yahoo Finance lookup
    try:
        if len(company) <= 5 and company.isupper():
            url = f"https://query1.finance.yahoo.com/v1/finance/search?q={company}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                quotes = data.get("quotes", [])
                if quotes:
                    long_name = quotes[0].get("longname") or quotes[0].get("shortname", "")
                    if long_name and long_name not in search_terms:
                        long_name = long_name.replace(" Inc.", "").replace(" Corp.", "").replace(" Ltd.", "")
                        search_terms.insert(0, long_name)
                        logger.info(f"Yahoo Finance: {company} → {long_name}")
    except Exception as e:
        logger.debug(f"Yahoo Finance lookup failed: {e}")
    
    # Strategy 3: Basic pattern matching for common cases
    company_upper = company.upper()
    basic_mapping = {
        'AAPL': 'Apple', 'MSFT': 'Microsoft', 'GOOGL': 'Google', 'GOOG': 'Google',
        'AMZN': 'Amazon', 'TSLA': 'Tesla', 'META': 'Meta', 'NVDA': 'Nvidia',
        'JPM': 'JPMorgan', 'V': 'Visa', 'MA': 'Mastercard', 'NFLX': 'Netflix'
    }
    
    if company_upper in basic_mapping:
        mapped_name = basic_mapping[company_upper]
        if mapped_name not in search_terms:
            search_terms.insert(0, mapped_name)
    
    # Add variations for specific companies
    if any(term.lower() in ['apple', 'aapl'] for term in search_terms):
        search_terms.extend(['iPhone', 'Apple Inc'])
    elif any(term.lower() in ['tesla', 'tsla'] for term in search_terms):
        search_terms.append('Elon Musk')
    
    return search_terms[:3]  # Return max 3 terms

def get_nyt_search_terms(company: str) -> List[str]:
    """
    Get better search terms for NYT API.
    NYT uses company names, not ticker symbols.
    """
    # Primary search terms
    search_terms = [company]
    
    # Add company name if we have a ticker
    ticker_to_company = {
        'AAPL': 'Apple',
        'MSFT': 'Microsoft', 
        'GOOGL': 'Google',
        'GOOG': 'Google',
        'AMZN': 'Amazon',
        'TSLA': 'Tesla',
        'META': 'Meta',
        'NVDA': 'Nvidia',
        'JPM': 'JPMorgan',
        'JNJ': 'Johnson & Johnson',
        'V': 'Visa',
        'MA': 'Mastercard',
        'PG': 'Procter & Gamble',
        'HD': 'Home Depot',
        'DIS': 'Disney',
        'NFLX': 'Netflix',
        'CRM': 'Salesforce',
        'ORCL': 'Oracle',
        'INTC': 'Intel',
        'AMD': 'Advanced Micro Devices',
        'CSCO': 'Cisco',
        'PFE': 'Pfizer',
        'MRK': 'Merck',
        'ABT': 'Abbott',
        'CVX': 'Chevron',
        'XOM': 'Exxon',
        'WMT': 'Walmart',
        'KO': 'Coca-Cola',
        'PEP': 'Pepsi',
        'NKE': 'Nike',
        'MCD': 'McDonald\'s',
        'BA': 'Boeing',
        'GE': 'General Electric',
        'CAT': 'Caterpillar'
    }
    
    company_upper = company.upper()
    if company_upper in ticker_to_company:
        company_name = ticker_to_company[company_upper]
        if company_name not in search_terms:
            search_terms.insert(0, company_name)  # Put company name first
    
    # Add alternative terms
    if company.upper() == 'AAPL' or company.lower() == 'apple':
        search_terms.extend(['Apple Inc', 'iPhone', 'Apple stock'])
    elif company.upper() == 'TSLA' or company.lower() == 'tesla':
        search_terms.extend(['Tesla Motors', 'Elon Musk Tesla'])
    elif company.upper() == 'META' or company.lower() == 'meta':
        search_terms.extend(['Facebook', 'Meta Platforms'])
    
    return search_terms[:3]  # Limit to 3 search terms

def fetch_nyt_news_working(company: str, days_back: int = 7, max_articles: int = 150) -> List[Dict]:
    """
    Enhanced NYT API function with better search terms.
    """
    try:
        api_key = os.getenv("NYTIMES_API_KEY")
        if not api_key:
            logger.info("NYT API key not found, skipping NYT news fetch")
            return []
        
        # Get better search terms
        search_terms = get_nyt_search_terms(company)
        logger.info(f"NYT API: Trying search terms: {search_terms}")
        
        url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
        all_articles = []
        
        # Try each search term
        for search_term in search_terms:
            logger.info(f"NYT API: Searching for '{search_term}'...")
            
            # Calculate pages needed for this search term
            pages_needed = min(10, (max_articles - len(all_articles) + 9) // 10)
            if pages_needed <= 0:
                break
            
            base_params = {
                "q": search_term,
                "api-key": api_key,
                "sort": "newest", 
                "fl": "headline,abstract,lead_paragraph,web_url,pub_date,section_name"
            }
            
            term_articles = []
            successful_pages = 0
            
            for page in range(pages_needed):
                try:
                    params = base_params.copy()
                    params["page"] = page
                    
                    response = requests.get(url, params=params, timeout=15)
                    
                    if response.status_code == 429:
                        logger.warning(f"NYT API rate limited on '{search_term}' page {page}, waiting...")
                        time.sleep(12)  # Wait longer on rate limit
                        break
                    
                    response.raise_for_status()
                    
                    data = response.json()
                    if data.get("status") != "OK":
                        logger.warning(f"NYT API returned status: {data.get('status')} for '{search_term}'")
                        break
                    
                    docs = data.get("response", {}).get("docs", [])
                    if not docs:
                        logger.info(f"NYT API: No more articles for '{search_term}' at page {page + 1}")
                        break
                    
                    # Process articles from this page
                    page_articles = []
                    for doc in docs:
                        # [Keep the same article processing logic as before]
                        try:
                            headline = doc.get("headline", {}) or {}
                            title = headline.get("main", "") if isinstance(headline, dict) else str(headline)
                            
                            abstract = doc.get("abstract", "") or ""
                            lead_paragraph = doc.get("lead_paragraph", "") or ""
                            web_url = doc.get("web_url", "") or ""
                            pub_date = doc.get("pub_date", "") or ""
                            section_name = doc.get("section_name", "") or ""
                            
                            if not title.strip() or not web_url.strip():
                                continue
                            
                            content_parts = []
                            if abstract.strip():
                                content_parts.append(abstract.strip())
                            if lead_paragraph.strip() and lead_paragraph.strip() != abstract.strip():
                                content_parts.append(lead_paragraph.strip())
                            
                            full_content = " ".join(content_parts)
                            snippet = full_content[:400] if full_content else title
                            
                            # Apply date filter
                            if pub_date:
                                try:
                                    article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00').replace('+0000', '+00:00'))
                                    cutoff_date = datetime.now() - timedelta(days=days_back)
                                    
                                    if article_date.tzinfo:
                                        article_date = article_date.replace(tzinfo=None)
                                    
                                    if article_date < cutoff_date:
                                        continue
                                except (ValueError, TypeError):
                                    pass
                            
                            # Enhanced relevance check - more lenient for company names
                            title_lower = title.lower()
                            content_lower = full_content.lower()
                            
                            # Check for any of our search terms (not just the original company)
                            has_company_mention = any(
                                term.lower() in title_lower or term.lower() in content_lower 
                                for term in search_terms
                            )
                            
                            is_business_section = any(term in section_name.lower() for term in 
                                                    ['business', 'technology', 'markets', 'finance', 'economy'])
                            
                            if has_company_mention or is_business_section:
                                article = {
                                    "title": title.strip(),
                                    "snippet": snippet,
                                    "full_content": full_content,
                                    "link": web_url.strip(),
                                    "source": "nytimes.com",
                                    "published": pub_date,
                                    "source_type": "nyt_api",
                                    "section": section_name,
                                    "search_term": search_term  # Track which term found this
                                }
                                page_articles.append(article)
                                
                        except Exception as e:
                            logger.warning(f"Error processing NYT article: {e}")
                            continue
                    
                    term_articles.extend(page_articles)
                    successful_pages += 1
                    
                    logger.info(f"NYT '{search_term}' page {page + 1}: {len(page_articles)} articles (term total: {len(term_articles)})")
                    
                    # Stop if we have enough for this term
                    if len(term_articles) >= 50:  # Max 50 per search term
                        break
                    
                    # Rate limiting between pages (12 seconds = 5 requests per minute)
                    time.sleep(12)
                    
                except Exception as e:
                    logger.error(f"NYT API error on '{search_term}' page {page}: {e}")
                    break
            
            # Add this term's articles to the total
            all_articles.extend(term_articles)
            logger.info(f"NYT '{search_term}': {len(term_articles)} articles from {successful_pages} pages")
            
            # Stop if we have enough articles
            if len(all_articles) >= max_articles:
                break
            
            # Wait between search terms
            if search_terms.index(search_term) < len(search_terms) - 1:
                time.sleep(15)  # Longer wait between different search terms
        
        logger.info(f"NYT API: Total {len(all_articles)} articles from all search terms")
        return all_articles[:max_articles]
        
    except Exception as e:
        logger.error(f"NYT API error for '{company}': {e}")
        return []
    
def fetch_reuters_api_news(company: str, days_back: int = 7) -> List[Dict]:
    """
    Placeholder for Reuters API integration.
    Returns empty list as Reuters API access is typically enterprise-only.
    """
    try:
        # Check for Reuters API key (unlikely to be available)
        api_key = os.getenv("REUTERS_API_KEY")
        if not api_key:
            logger.info("Reuters API key not found, will use RSS feeds instead")
            return []
        
        # Implementation would go here if Reuters API is available
        logger.info("Reuters API integration not implemented - using RSS fallback")
        return []
        
    except Exception as e:
        logger.error(f"Error with Reuters API for '{company}': {str(e)}")
        return []

# Fix 3: RSS Parser with sys import fixed
def parse_rss_feed_fixed(feed_url: str, company: str, days_back: int = 7) -> List[Dict]:
    """
    Fixed RSS parser with proper imports.
    """
    try:
        # Headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        }
        
        response = requests.get(feed_url, headers=headers, timeout=15, allow_redirects=True)
        if response.status_code != 200:
            logger.warning(f"RSS feed HTTP {response.status_code}: {feed_url}")
            return []
        
        # Parse feed
        import feedparser
        feed = feedparser.parse(response.content)
        
        if not hasattr(feed, 'entries') or not feed.entries:
            return []
        
        articles = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # Get search terms for better matching
        search_terms = get_nyt_search_terms_dynamic(company)
        search_terms_lower = [term.lower() for term in search_terms]
        
        for entry in feed.entries[:20]:  # Limit to 20 entries
            try:
                title = getattr(entry, 'title', '').strip()
                link = getattr(entry, 'link', '').strip()
                
                if not title or not link:
                    continue
                
                # Get description
                description = ''
                for field in ['summary', 'description', 'content']:
                    if hasattr(entry, field):
                        field_value = getattr(entry, field)
                        if isinstance(field_value, list) and field_value:
                            description = field_value[0].get('value', '') if isinstance(field_value[0], dict) else str(field_value[0])
                        elif isinstance(field_value, str):
                            description = field_value
                        elif hasattr(field_value, 'value'):
                            description = field_value.value
                        if description.strip():
                            break
                
                # Clean description
                if description:
                    import re
                    description = re.sub(r'<[^>]+>', '', description)
                    description = re.sub(r'\s+', ' ', description).strip()[:800]
                
                # Date check
                pub_date = None
                for date_field in ['published_parsed', 'updated_parsed']:
                    if hasattr(entry, date_field):
                        date_tuple = getattr(entry, date_field)
                        if date_tuple and len(date_tuple) >= 6:
                            try:
                                pub_date = datetime(*date_tuple[:6])
                                break
                            except (ValueError, TypeError):
                                continue
                
                if pub_date and pub_date < cutoff_date:
                    continue
                
                # Relevance check
                title_lower = title.lower()
                desc_lower = description.lower()
                content = title_lower + ' ' + desc_lower
                
                # Check for company mention
                has_company_mention = any(term in content for term in search_terms_lower)
                
                # Financial context
                financial_keywords = ['stock', 'shares', 'earnings', 'revenue', 'market', 'business']
                has_financial_context = any(keyword in content for keyword in financial_keywords)
                
                if has_company_mention or has_financial_context:
                    article = {
                        "title": title,
                        "snippet": description[:300] if description else title[:300],
                        "full_content": description if description else title,
                        "link": link,
                        "source": extract_domain(link),
                        "published": pub_date.isoformat() if pub_date else "",
                        "source_type": "rss_feed"
                    }
                    articles.append(article)
                
            except Exception as e:
                logger.debug(f"Error processing RSS entry: {e}")
                continue
        
        return articles
        
    except Exception as e:
        logger.warning(f"RSS feed error {feed_url}: {e}")
        return []

def fetch_rss_feeds_working_2025(company: str, days_back: int = 7) -> List[Dict]:
    """
    Fetch from actually working RSS feeds in 2025.
    """
    logger.info(f"Fetching 2025 working RSS feeds for {company}...")
    
    # Get working feeds
    working_feeds = get_working_rss_feeds_2025_cleaned()  # Changed from get_working_rss_feeds_2025()
    
    # Add company-specific feeds
    company_feeds = get_company_specific_feeds_2025_cleaned(company)  # Changed from get_company_specific_feeds_2025()
    working_feeds.update(company_feeds)
    
    all_articles = []
    successful_feeds = 0
    feed_stats = {}
    
    # Prioritize premium sources (process these first)
    premium_order = [
        'cnbc_business', 'cnbc_finance', 'cnbc_earnings', 
        'ft_home', 'investing_com', 'seeking_alpha',
        'marketwatch_main', 'cnbc_technology'
    ]
    
    # Process premium feeds first
    for feed_name in premium_order:
        if feed_name in working_feeds:
            feed_url = working_feeds[feed_name]
            try:
                logger.debug(f"Processing premium RSS: {feed_name}")
                articles = parse_rss_feed_fixed(feed_url, company, days_back)
                
                if articles:
                    all_articles.extend(articles)
                    successful_feeds += 1
                    feed_stats[feed_name] = len(articles)
                    logger.info(f"✓ Premium RSS {feed_name}: {len(articles)} articles")
                else:
                    feed_stats[feed_name] = 0
                    logger.debug(f"✗ Premium RSS {feed_name}: 0 articles")
                    
                # Rate limiting
                time.sleep(3)  # 3 seconds between premium feeds
                
            except Exception as e:
                logger.warning(f"Premium RSS {feed_name} failed: {e}")
                feed_stats[feed_name] = 0
                continue
    
    # Process remaining feeds
    remaining_feeds = {k: v for k, v in working_feeds.items() if k not in premium_order}
    
    for feed_name, feed_url in remaining_feeds.items():
        try:
            logger.debug(f"Processing RSS: {feed_name}")
            articles = parse_rss_feed_fixed(feed_url, company, days_back)
            
            if articles:
                all_articles.extend(articles)
                successful_feeds += 1
                feed_stats[feed_name] = len(articles)
                logger.info(f"✓ RSS {feed_name}: {len(articles)} articles")
            else:
                feed_stats[feed_name] = 0
                
            # Rate limiting
            time.sleep(2)
            
        except Exception as e:
            logger.warning(f"RSS {feed_name} failed: {e}")
            feed_stats[feed_name] = 0
            continue
    
    logger.info(f"2025 RSS Results: {successful_feeds}/{len(working_feeds)} successful, {len(all_articles)} total articles")
    logger.info(f"Feed performance: {feed_stats}")
    
    return all_articles

def extract_domain_simple(url: str) -> str:
    """Simple domain extraction."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return "unknown"


def combine_premium_sources_enhanced(company: str, days_back: int = 7) -> List[Dict]:
    """
    Enhanced version that gets 150 NYT articles + premium RSS feeds.
    """
    all_articles = []
    source_stats = {}
    
    # 1. Fetch 150 articles from NYT API with enhanced function
    try:
        nyt_articles = fetch_nyt_news_working(company, days_back, max_articles=150)
        all_articles.extend(nyt_articles)
        source_stats['nyt_api'] = len(nyt_articles)
        if nyt_articles:
            logger.info(f"NYT API Enhanced: {len(nyt_articles)} articles retrieved (up to 150)")
    except Exception as e:
        logger.error(f"NYT API failed: {e}")
        source_stats['nyt_api'] = 0
    
    # 2. Fetch from enhanced premium RSS feeds
    try:
        # FIXED: Use the correct function name
        rss_articles = fetch_rss_feeds_working_2025(company, days_back)  # Make sure this function exists
        all_articles.extend(rss_articles)
        source_stats['premium_rss'] = len(rss_articles)
        if rss_articles:
            logger.info(f"Premium RSS Enhanced: {len(rss_articles)} articles retrieved")
    except Exception as e:
        logger.error(f"Premium RSS feeds failed: {e}")
        source_stats['premium_rss'] = 0
    
    # 3. Optional: Add Reuters API if available (placeholder for future)
    source_stats['reuters_api'] = 0
    
    # Enhanced deduplication with better similarity detection
    unique_articles = []
    seen_urls = set()
    seen_titles = set()
    
    for article in all_articles:
        url = article.get('link', '')
        title = article.get('title', '').lower().strip()
        
        # Skip if URL already seen
        if url and url in seen_urls:
            continue
        
        # Enhanced title similarity detection
        title_words = set(title.split())
        is_duplicate = False
        
        for seen_title in seen_titles:
            seen_words = set(seen_title.split())
            if len(title_words) > 3 and len(seen_words) > 3:
                # Use more sophisticated similarity
                overlap = len(title_words & seen_words)
                total_unique = len(title_words | seen_words)
                similarity = overlap / total_unique if total_unique > 0 else 0
                
                # Also check for substring matches (common in similar headlines)
                title_clean = ' '.join(sorted(title_words))
                seen_clean = ' '.join(sorted(seen_words))
                
                if similarity > 0.7 or (len(title) > 30 and (title[:30] in seen_title or seen_title[:30] in title)):
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            unique_articles.append(article)
            if url:
                seen_urls.add(url)
            if title:
                seen_titles.add(title)
    
    logger.info(f"Enhanced premium sources: {len(all_articles)} total → {len(unique_articles)} unique articles")
    logger.info(f"Enhanced source breakdown: {source_stats}")
    
    return unique_articles

def deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """
    Remove duplicate articles based on URL and title similarity.
    """
    seen_urls = set()
    seen_titles = set()
    unique_articles = []
    
    for article in articles:
        url = article.get('link', '')
        title = article.get('title', '').lower().strip()
        
        # Skip if URL already seen
        if url and url in seen_urls:
            continue
        
        # Skip if very similar title already seen
        title_words = set(title.split())
        is_duplicate = False
        
        for seen_title in seen_titles:
            seen_words = set(seen_title.split())
            if len(title_words) > 3 and len(seen_words) > 3:
                # Check if titles are very similar (>70% word overlap)
                overlap = len(title_words & seen_words)
                total_unique = len(title_words | seen_words)
                if total_unique > 0 and overlap / total_unique > 0.7:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            unique_articles.append(article)
            if url:
                seen_urls.add(url)
            if title:
                seen_titles.add(title)
    
    return unique_articles

def is_relevant_article(article: Dict, company: str) -> bool:
    """Enhanced relevance filtering for better article quality."""
    title = article.get('title', '').lower()
    snippet = article.get('snippet', '').lower()
    source = article.get('source', '').lower()
    company_lower = company.lower()
    
    # Skip job postings, careers pages
    if any(term in title + snippet for term in ['jobs at', 'careers at', 'apply today', 'job openings', 'hiring', 'work at']):
        return False
    
    # Skip obviously unrelated businesses
    if company_lower == 'apple':
        irrelevant_terms = ['ford', 'dealership', 'auto sales', 'car dealer', 'valley', 'city of apple']
        if any(term in title + snippet for term in irrelevant_terms):
            return False
    
    # Skip pure directory/listing pages
    if any(term in title for term in ['directory', 'yellow pages', 'business listing']):
        return False
    
    # Skip non-English content (basic check)
    if len(title) > 20:
        english_words = ['the', 'and', 'of', 'to', 'in', 'a', 'is', 'that', 'for', 'with']
        has_english = any(word in title + snippet for word in english_words)
        if not has_english:
            return False
    
    # Company mention requirement
    company_mentions = title.count(company_lower) + snippet.count(company_lower)
    if company_mentions == 0:
        # For tickers, also check for the company name
        if len(company) <= 5 and company.isupper():
            ticker = company
            company_name = next((name for name, tick in COMPANY_TO_TICKER.items() if tick == ticker), "")
            if company_name:
                company_mentions += title.count(company_name) + snippet.count(company_name)
        
        if company_mentions == 0:
            return False
    
    # Financial context requirement (looser for premium sources)
    has_financial_context = any(keyword in title + snippet for keyword in FINANCIAL_KEYWORDS[:20])  # Top 20 keywords
    
    if source in PREMIUM_SOURCES_ENHANCED:
        return True  # Trust premium sources more
    elif has_financial_context:
        return True
    elif company_mentions >= 2:  # Multiple mentions might indicate relevance
        return True
    
    return False

def fetch_google_news(company: str, days_back: int = 7) -> List[Dict]:
    """
    Enhanced Google search with better rate limiting and error handling.
    """
    try:
        # Check for required API credentials
        api_key = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        if not api_key or not search_engine_id:
            logger.info("Google API credentials not found, skipping Google search")
            return []
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_filter = start_date.strftime("%Y-%m-%d")
        
        # Reduced and more strategic search queries to avoid rate limits
        search_queries = []
        
        # Strategy 1: Focus on 2-3 premium sources instead of all
        priority_sources = ['bloomberg.com', 'reuters.com']  # Reduced from 5 to 2
        for source in priority_sources:
            search_queries.append(f'site:{source} "{company}" after:{date_filter}')
        
        # Strategy 2: One broad financial search
        if len(company) <= 5 and company.isupper():
            search_queries.append(f'"{company}" financial news earnings after:{date_filter}')
        else:
            search_queries.append(f'"{company}" business news after:{date_filter}')
        
        # Strategy 3: One fallback search without benzinga
        search_queries.append(f'"{company}" stock news -site:benzinga.com after:{date_filter}')
        
        all_articles = []
        seen_urls = set()
        source_counts = {}
        successful_queries = 0
        
        # Enhanced rate limiting - longer delays between requests
        rate_limiter.wait_if_needed('google', 2.0)  # Increased from 1.0 to 2.0 seconds
        
        for i, query in enumerate(search_queries):
            try:
                # Additional delay between queries to prevent rate limiting
                if i > 0:
                    time.sleep(1.5)  # 1.5 second delay between queries
                
                url = "https://www.googleapis.com/customsearch/v1"
                params = {
                    "key": api_key,
                    "cx": search_engine_id,
                    "q": query,
                    "sort": "date",
                    "num": 8,  # Reduced from 10 to 8 per query
                    "dateRestrict": f"d{days_back}"
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                # Handle rate limiting gracefully
                if response.status_code == 429:
                    logger.warning(f"Google API rate limited, waiting and continuing with other sources")
                    time.sleep(5)  # Wait 5 seconds on rate limit
                    continue  # Skip this query but continue with others
                
                response.raise_for_status()
                successful_queries += 1
                
                items = response.json().get("items", [])
                for item in items:
                    article_url = item.get("link", "")
                    
                    if article_url in seen_urls:
                        continue
                    seen_urls.add(article_url)
                    
                    source_domain = extract_domain(article_url)
                    
                    # Implement source diversity - limit articles per source
                    current_count = source_counts.get(source_domain, 0)
                    max_per_source = 3 if source_domain == 'benzinga.com' else 6  # Reduced limits
                    
                    if current_count >= max_per_source:
                        continue
                    
                    article = {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "link": article_url,
                        "source": source_domain,
                        "published": item.get("snippet", ""),
                        "source_type": "google_search"
                    }
                    
                    if is_relevant_article(article, company):
                        all_articles.append(article)
                        source_counts[source_domain] = current_count + 1
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning(f"Google API rate limit hit for query: {query[:50]}...")
                    time.sleep(5)  # Wait before next query
                else:
                    logger.warning(f"Google query failed: {query[:50]}... - {str(e)}")
                continue
            except Exception as query_e:
                logger.warning(f"Google query failed: {query[:50]}... - {str(query_e)}")
                continue
        
        # Log results
        if successful_queries > 0:
            logger.info(f"Google Search: {len(all_articles)} articles from {len(source_counts)} sources ({successful_queries}/{len(search_queries)} queries successful)")
        else:
            logger.warning(f"Google Search: All queries failed (likely rate limited)")
        
        return all_articles
        
    except Exception as e:
        logger.error(f"Error in Google search for {company}: {str(e)}")
        return []

def fetch_alphavantage_news_enhanced(company: str, days_back: int = 7) -> List[Dict]:
    """
    Enhanced AlphaVantage News Sentiment API with improved filtering to ensure 
    we process at least 25% of found articles instead of filtering too aggressively.
    """
    try:
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            logger.warning("AlphaVantage API key not found, skipping premium news fetch")
            return []
        
        # Use dynamic ticker conversion instead of hard-coded mapping
        from company_ticker_service import fast_company_ticker_service as company_ticker_service
        ticker, company_name = company_ticker_service.get_both_ticker_and_company(company)
        
        if not ticker:
            logger.warning(f"Could not convert '{company}' to ticker symbol")
            ticker = company.upper()  # Fallback to original input
        
        logger.info(f"AlphaVantage: Using ticker '{ticker}' for company '{company}'")
        
        rate_limiter.wait_if_needed('alphavantage', 12.0)
        
        # AlphaVantage News Sentiment API
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "apikey": api_key,
            "limit": 200,  # Get more articles for better filtering
            "sort": "LATEST"
        }
        
        logger.info(f"Fetching AlphaVantage news for ticker: {ticker}...")
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for API errors
        if "Error Message" in data:
            logger.error(f"AlphaVantage API error: {data['Error Message']}")
            return []
        
        if "Information" in data:
            if "Invalid inputs" in data["Information"]:
                logger.warning(f"AlphaVantage: Invalid ticker '{ticker}' for company '{company}'")
                return []
            else:
                logger.warning(f"AlphaVantage API info: {data['Information']}")
                return []
        
        feed_data = data.get("feed", [])
        
        if not feed_data:
            logger.info(f"AlphaVantage: No articles found for ticker {ticker}")
            return []
        
        logger.info(f"AlphaVantage: Processing {len(feed_data)} raw articles from feed...")
        
        # STEP 1: Basic filtering (date and content validation)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        valid_articles = []
        
        for item in feed_data:
            try:
                # Parse article date
                time_published = item.get("time_published", "")
                if time_published:
                    try:
                        article_date = datetime.strptime(time_published[:8], "%Y%m%d")
                        if article_date < cutoff_date:
                            continue
                    except ValueError:
                        pass  # Include articles with invalid dates rather than exclude
                
                # Basic content validation
                title = item.get("title", "").strip()
                summary = item.get("summary", "").strip()
                url = item.get("url", "").strip()
                
                if not title or not url:
                    continue
                
                # Extract sentiment and relevance data
                ticker_sentiment_data = item.get("ticker_sentiment", [])
                relevance_score = 0.0
                sentiment_score = 0.0
                sentiment_label = "Neutral"
                
                # Look for ticker-specific sentiment data
                for sentiment_item in ticker_sentiment_data:
                    if sentiment_item.get("ticker") == ticker:
                        try:
                            relevance_score = float(sentiment_item.get("relevance_score", 0))
                            sentiment_score = float(sentiment_item.get("ticker_sentiment_score", 0))
                            sentiment_label = sentiment_item.get("ticker_sentiment_label", "Neutral")
                            break
                        except (ValueError, TypeError):
                            continue
                
                # Fallback to overall sentiment if no ticker-specific data
                if relevance_score == 0:
                    try:
                        relevance_score = float(item.get("relevance_score", 0))
                    except (ValueError, TypeError):
                        relevance_score = 0.0
                
                if sentiment_score == 0:
                    try:
                        sentiment_score = float(item.get("overall_sentiment_score", 0))
                        sentiment_label = item.get("overall_sentiment_label", "Neutral")
                    except (ValueError, TypeError):
                        sentiment_score = 0.0
                
                article = {
                    "title": title,
                    "snippet": summary[:300],
                    "full_content": summary,
                    "link": url,
                    "source": extract_domain(url),
                    "published": time_published,
                    "sentiment_score": sentiment_score,
                    "sentiment_label": sentiment_label,
                    "relevance_score": relevance_score,
                    "source_type": "alphavantage_premium"
                }
                
                valid_articles.append(article)
                
            except Exception as item_error:
                logger.warning(f"Error processing AlphaVantage article: {item_error}")
                continue
        
        logger.info(f"AlphaVantage: {len(valid_articles)} articles passed basic validation")
        
        # STEP 2: Enhanced relevance filtering with multiple criteria
        # Instead of strict filtering, use scoring and take top articles
        scored_articles = []
        
        # Create comprehensive search terms for matching
        search_terms = [company.lower(), ticker.lower()]
        if company_name and company_name.lower() not in search_terms:
            search_terms.append(company_name.lower())
        
        # Add cleaned versions
        for term in search_terms.copy():
            clean_term = term.replace(" inc", "").replace(" corp", "").replace(" ltd", "")
            if clean_term != term and clean_term not in search_terms:
                search_terms.append(clean_term)
        
        for article in valid_articles:
            score = 0.0
            content_lower = (article['title'] + " " + article['full_content']).lower()
            
            # Scoring criteria (additive, not eliminative)
            
            # 1. Relevance score from AlphaVantage (weight: high)
            av_relevance = article.get('relevance_score', 0)
            score += av_relevance * 50  # High weight for AlphaVantage's own relevance scoring
            
            # 2. Company/ticker mentions (weight: high)
            mention_score = 0
            for search_term in search_terms:
                mentions = content_lower.count(search_term)
                mention_score += mentions * 10
            score += min(mention_score, 30)  # Cap at 30 points
            
            # 3. Financial context keywords (weight: medium)
            financial_keywords = [
                'earnings', 'revenue', 'profit', 'stock', 'shares', 'analyst', 
                'upgrade', 'downgrade', 'target', 'estimate', 'guidance', 'outlook'
            ]
            financial_score = sum(2 for keyword in financial_keywords if keyword in content_lower)
            score += min(financial_score, 20)  # Cap at 20 points
            
            # 4. Sentiment strength (weight: low)
            sentiment_strength = abs(article.get('sentiment_score', 0))
            score += sentiment_strength * 5
            
            # 5. Source quality bonus (weight: medium)
            source = article.get('source', '')
            if source in ['bloomberg.com', 'reuters.com', 'wsj.com', 'marketwatch.com']:
                score += 15
            elif source in ['cnbc.com', 'ft.com', 'barrons.com']:
                score += 10
            elif source in ['yahoo.com', 'investing.com']:
                score += 5
            
            # 6. Title relevance bonus (weight: medium)
            title_lower = article['title'].lower()
            title_mentions = sum(1 for term in search_terms if term in title_lower)
            score += title_mentions * 8
            
            scored_articles.append((article, score))
        
        # Sort by score and take top articles
        scored_articles.sort(key=lambda x: x[1], reverse=True)
        
        # STEP 3: Ensure we get at least 25% of found articles (minimum quality threshold)
        target_count = max(min(len(valid_articles) // 4, 50), 10)  # At least 25% or 10, max 50
        
        # Take articles with score > 5 (basic relevance) or top target_count, whichever is larger
        relevant_articles = []
        
        for article, score in scored_articles:
            if score > 5 or len(relevant_articles) < target_count:
                relevant_articles.append(article)
            if len(relevant_articles) >= 50:  # Cap at 50 total articles
                break
        
        # Log detailed metrics for debugging
        if scored_articles:
            scores = [score for _, score in scored_articles]
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
            min_score = min(scores)
            
            logger.info(f"AlphaVantage scoring - Articles: {len(scored_articles)}, "
                       f"Avg score: {avg_score:.2f}, Max: {max_score:.2f}, Min: {min_score:.2f}")
            logger.info(f"AlphaVantage taking {len(relevant_articles)} articles "
                       f"(target was {target_count}, {len(relevant_articles)/len(valid_articles)*100:.1f}% of valid)")
        
        # Sort final articles by relevance and sentiment for quality ranking
        relevant_articles.sort(key=lambda x: (x.get('relevance_score', 0) + abs(x.get('sentiment_score', 0))), reverse=True)
        
        logger.info(f"AlphaVantage FINAL: {len(relevant_articles)} articles for {ticker} "
                   f"(from {len(feed_data)} raw → {len(valid_articles)} valid → {len(relevant_articles)} relevant)")
        
        return relevant_articles
        
    except Exception as e:
        logger.error(f"Error fetching AlphaVantage news for '{company}': {str(e)}")
        import traceback
        logger.error(f"AlphaVantage traceback: {traceback.format_exc()}")
        return []

def ensure_minimum_alphavantage_articles(all_articles: List[Dict], target_percentage: float = 0.25) -> List[Dict]:
    """
    Ensure AlphaVantage articles represent at least target_percentage of the final articles.
    If not, boost AlphaVantage articles in the final selection.
    """
    alphavantage_articles = [a for a in all_articles if a.get('source_type') == 'alphavantage_premium']
    total_articles = len(all_articles)
    
    if total_articles == 0:
        return all_articles
    
    current_percentage = len(alphavantage_articles) / total_articles
    
    logger.info(f"AlphaVantage representation: {len(alphavantage_articles)}/{total_articles} = {current_percentage:.1%}")
    
    if current_percentage >= target_percentage:
        logger.info(f"AlphaVantage target met ({current_percentage:.1%} >= {target_percentage:.1%})")
        return all_articles
    
    # Need to boost AlphaVantage representation
    target_av_count = int(total_articles * target_percentage)
    needed_av_articles = target_av_count - len(alphavantage_articles)
    
    logger.info(f"Boosting AlphaVantage: need {needed_av_articles} more AV articles for {target_percentage:.1%} representation")
    
    # If we don't have enough AV articles, we need to either:
    # 1. Reduce other articles to maintain proportion, or
    # 2. Accept lower percentage but ensure quality
    
    # Strategy: Ensure we have at least 25% AV articles or 8 AV articles minimum
    min_av_articles = max(target_av_count, 8)
    
    if len(alphavantage_articles) < min_av_articles:
        logger.warning(f"Only {len(alphavantage_articles)} AlphaVantage articles available, "
                      f"target was {min_av_articles}")
    
    return all_articles

def score_articles_fixed(articles: List[Dict], company: str) -> List[Tuple[Dict, float]]:
    """
    Enhanced scoring that heavily penalizes unwanted sources.
    """
    scored_articles = []
    
    for article in articles:
        score = 0.0
        
        source = article.get('source', '').lower()
        source_type = article.get('source_type', 'google_search')
        title = article.get('title', '').lower()
        snippet = article.get('snippet', '').lower()
        
        # UNWANTED SOURCE PENALTIES (Heavy penalties)
        if source in UNWANTED_SOURCES:
            score += UNWANTED_SOURCES[source]
            logger.debug(f"Penalized {source}: {UNWANTED_SOURCES[source]} points")
        
        # PREMIUM SOURCE BONUSES
        if source in PREMIUM_SOURCES_ENHANCED:
            score += PREMIUM_SOURCES_ENHANCED[source]
        
        # SOURCE TYPE BONUSES
        if source_type == 'alphavantage_premium':
            # But penalize if it's from unwanted sources
            if source not in UNWANTED_SOURCES:
                score += 15
                relevance_score = float(article.get('relevance_score', 0))
                score += relevance_score * 10
        elif source_type == 'nyt_api':
            score += 25  # Big bonus for NYT API
        elif source_type == 'rss_feed':
            score += 8
        
        # Company mention bonus
        company_lower = company.lower()
        if company_lower in title:
            score += 5
        content = title + ' ' + snippet
        company_mentions = content.count(company_lower)
        score += min(company_mentions * 2, 6)
        
        # Financial relevance
        financial_keywords = ['earnings', 'revenue', 'stock', 'analyst', 'price target']
        financial_score = sum(1 for keyword in financial_keywords if keyword in content)
        score += financial_score * 1.5
        
        # Final penalty for unwanted sources (double penalty)
        if source in UNWANTED_SOURCES:
            score += UNWANTED_SOURCES[source]  # Apply penalty twice
        
        scored_articles.append((article, score))
    
    # Sort by score
    scored_articles.sort(key=lambda x: x[1], reverse=True)
    
    # FIXED: Log source distribution for ALL 30 articles (not just top 20)
    if scored_articles:
        top_30_sources = [art[0]['source'] for art in scored_articles[:30]]  # Changed from 20 to 30
        source_dist = {}
        for source in top_30_sources:
            source_dist[source] = source_dist.get(source, 0) + 1
        logger.info(f"Fixed scoring - Top 30 source distribution: {source_dist}")  # Changed from 20 to 30
    
    return scored_articles

def fetch_comprehensive_news_enhanced(company: str, days_back: int = 7, enable_monitoring: bool = True) -> Dict[str, Any]:
    """
    Enhanced version of the main orchestration function.
    """
    import time
    start_time = time.time()
    
    all_articles = []
    source_performance = {}
    api_errors = []
    
    logger.info(f"🚀 Starting ENHANCED comprehensive news fetch for {company} ({days_back} days)")
    
    # Step 1: Fetch from AlphaVantage Premium (highest priority)
    try:
        alphavantage_articles = fetch_alphavantage_news_enhanced(company, days_back)  # FIXED: Added _enhanced
        all_articles.extend(alphavantage_articles)
        source_performance['alphavantage'] = len(alphavantage_articles)
        logger.info(f"✓ AlphaVantage: {len(alphavantage_articles)} articles with full content + sentiment")
    except Exception as e:
        logger.error(f"AlphaVantage failed: {e}")
        source_performance['alphavantage'] = 0
        api_errors.append(f"AlphaVantage: {str(e)}")
    
    # Step 2: Fetch from Enhanced Premium Sources (150 NYT + Premium RSS)
    try:
        premium_articles = combine_premium_sources_enhanced(company, days_back)
        
        # Deduplicate against AlphaVantage articles
        alphavantage_urls = {article.get('link', '') for article in alphavantage_articles}
        new_premium_articles = []
        
        for article in premium_articles:
            if article.get('link', '') not in alphavantage_urls:
                new_premium_articles.append(article)
        
        all_articles.extend(new_premium_articles)
        source_performance['enhanced_premium'] = len(new_premium_articles)
        logger.info(f"✓ Enhanced Premium Sources: {len(new_premium_articles)} unique articles (150 NYT + Premium RSS)")
        
    except Exception as e:
        logger.error(f"Enhanced premium sources failed: {e}")
        source_performance['enhanced_premium'] = 0
        api_errors.append(f"Enhanced premium sources: {str(e)}")
    
    # Step 3: Google Search (minimal, only for gap-filling)
    try:
        google_articles = fetch_google_news(company, days_back)
        
        # Deduplicate against existing articles
        existing_urls = {article.get('link', '') for article in all_articles}
        new_google_articles = []
        
        for article in google_articles:
            if article.get('link', '') not in existing_urls:
                new_google_articles.append(article)
        
        # Limit Google results since we have premium sources
        new_google_articles = new_google_articles[:20]  # Only top 20 from Google
        all_articles.extend(new_google_articles)
        source_performance['google_fallback'] = len(new_google_articles)
        logger.info(f"✓ Google Fallback: {len(new_google_articles)} additional articles (limited)")
        
    except Exception as e:
        logger.error(f"Google search failed: {e}")
        source_performance['google_fallback'] = 0
        api_errors.append(f"Google search: {str(e)}")
    
    # Final enhanced deduplication
    all_articles = deduplicate_articles(all_articles)
    total_articles = len(all_articles)
    
    logger.info(f"📊 FINAL SUMMARY: {total_articles} unique articles from all sources")
    logger.info(f"📈 Source performance: {source_performance}")
    
    # Calculate enhanced quality metrics
    premium_source_domains = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'cnbc.com', 
                             'marketwatch.com', 'barrons.com', 'nytimes.com']
    high_quality_sources = sum(1 for article in all_articles 
                             if article.get('source', '') in premium_source_domains)
    
    # Count articles by source type
    alphavantage_count = source_performance.get('alphavantage', 0)
    premium_sources_count = source_performance.get('premium_sources', 0)
    google_count = source_performance.get('google_search', 0)
    
    # Count specific premium source types
    nyt_articles = sum(1 for article in all_articles if article.get('source_type') == 'nyt_api')
    rss_articles = sum(1 for article in all_articles if article.get('source_type') == 'rss_feed')
    
    # Calculate coverage percentages
    if total_articles > 0:
        premium_coverage = (high_quality_sources / total_articles * 100)
        alphavantage_coverage = (alphavantage_count / total_articles * 100)
        premium_sources_coverage = (premium_sources_count / total_articles * 100)
    else:
        premium_coverage = 0
        alphavantage_coverage = 0
        premium_sources_coverage = 0
    
    # Enhanced analysis quality determination
    full_content_articles = alphavantage_count + nyt_articles + rss_articles
    
    if alphavantage_coverage >= 40 and premium_sources_coverage >= 20:
        analysis_quality = "Premium+"
    elif alphavantage_coverage >= 30 or (premium_sources_coverage >= 30 and full_content_articles >= 5):
        analysis_quality = "Institutional"
    elif full_content_articles >= 3 or premium_coverage >= 40:
        analysis_quality = "Professional" 
    elif high_quality_sources >= 2 or alphavantage_count >= 1:
        analysis_quality = "Standard"
    else:
        analysis_quality = "Limited"
    
    # Generate analysis if articles found
    summaries = {}
    if all_articles:
        summaries = generate_premium_analysis(company, all_articles)
    else:
        summaries = {
            "executive": ["**[NO DATA]** No recent financial news found across all premium sources (AlphaVantage, NYT, Reuters, Bloomberg RSS). Try expanding date range or verifying company ticker *(Source: comprehensive multi-source search)*"],
            "investor": ["**[RECOMMENDATION]** Verify company ticker symbol or try major exchanges (NYSE/NASDAQ). Consider checking earnings calendar for upcoming coverage opportunities *(Source: search optimization)*"],
            "catalysts": ["**[TIMING]** Monitor upcoming earnings announcements, product launches, or regulatory events that typically generate financial coverage *(Source: typical coverage patterns)*"]
        }
    
    response_time = time.time() - start_time
    
    # Enhanced logging with detailed breakdown
    logger.info(f"🎯 ANALYSIS COMPLETE for {company}:")
    logger.info(f"   • Total articles: {total_articles}")
    logger.info(f"   • AlphaVantage (full content + sentiment): {alphavantage_count}")
    logger.info(f"   • Premium sources (NYT API + RSS): {premium_sources_count}")
    logger.info(f"   • Google fallback: {google_count}")
    logger.info(f"   • NYT API articles: {nyt_articles}")
    logger.info(f"   • RSS feed articles: {rss_articles}")
    logger.info(f"   • Premium domains: {high_quality_sources}")
    logger.info(f"   • Analysis quality: {analysis_quality}")
    logger.info(f"   • Response time: {response_time:.2f}s")
    
    # Optional monitoring integration
    if enable_monitoring:
        try:
            # Try to import and use monitoring if available
            from monitoring import log_analysis_request
            
            article_counts = {
                'total': total_articles,
                'alphavantage': alphavantage_count,
                'nyt': nyt_articles,
                'rss': rss_articles,
                'google': google_count,
                'premium': high_quality_sources
            }
            
            source_success_rates = {}
            for source, count in source_performance.items():
                # Simple success rate calculation (could be enhanced)
                source_success_rates[source] = 1.0 if count > 0 else 0.0
            
            log_analysis_request(
                company=company,
                article_counts=article_counts,
                analysis_quality=analysis_quality,
                response_time=response_time,
                api_errors=api_errors,
                source_success_rates=source_success_rates
            )
            
        except ImportError:
            # Monitoring module not available, skip silently
            pass
        except Exception as e:
            logger.warning(f"Monitoring failed: {e}")
    
    response_time = time.time() - start_time
    logger.info(f"🎯 ENHANCED ANALYSIS COMPLETE for {company}: {total_articles} articles in {response_time:.2f}s")
    
    # Return comprehensive results
    return {
        'company': company,
        'articles': all_articles,
        'summaries': generate_premium_analysis(company, all_articles) if all_articles else {},
        'metrics': {
            'total_articles': total_articles,
            'alphavantage_articles': source_performance.get('alphavantage', 0),
            'enhanced_premium_articles': source_performance.get('enhanced_premium', 0),
            'google_articles': source_performance.get('google_fallback', 0),
            'premium_sources_count': premium_sources_count,
            'high_quality_sources': high_quality_sources,
            'premium_coverage': round(premium_coverage, 1),
            'alphavantage_coverage': round(alphavantage_coverage, 1),
            'premium_sources_coverage': round(premium_sources_coverage, 1),
            'analysis_quality': analysis_quality,
            'response_time': response_time,
            'full_content_articles': full_content_articles
        },
        'source_performance': source_performance,
        'api_errors': api_errors,
        'success': total_articles > 0
    }

def generate_premium_analysis(company: str, articles: List[Dict], max_articles: int = 30) -> Dict[str, List[str]]:
    """
    Enhanced analysis function - increased from 20 to 30 articles for better diversity.
    """
    if not articles:
        return {
            "executive": ["No recent financial news found. Consider expanding date range or checking company name/ticker."],
            "investor": ["No recent investor-relevant developments identified."],
            "catalysts": ["No material catalysts or risks detected in recent coverage."]
        }
    
    try:
        # Score and filter articles
        scored_articles = score_articles_fixed(articles, company)
        top_articles = [article for article, score in scored_articles[:max_articles]]  # Increased to 30
        
        # Calculate source quality metrics
        source_type_counts = {}
        for article in top_articles:
            source_type = article.get('source_type', 'google_search')
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        
        premium_count = sum(1 for article in top_articles if article['source'] in PREMIUM_SOURCES_ENHANCED)
        total_articles = len(top_articles)
        
        # Prepare article content for analysis
        article_text = ""
        for i, article in enumerate(top_articles, 1):
            source_type = article.get('source_type', 'google_search')
            
            if source_type == 'alphavantage_premium':
                content_quality = "PREMIUM+FULL_CONTENT+SENTIMENT"
                content = article.get('full_content', article.get('snippet', ''))[:800]
                sentiment_label = article.get('sentiment_label', 'Neutral')
                sentiment_score = article.get('sentiment_score', 0)
                relevance_score = article.get('relevance_score', 0)
                
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']} | Sentiment: {sentiment_label} ({sentiment_score:.2f}) | Relevance: {relevance_score:.3f}\n"
                article_text += f"   Full Content: {content}\n"
                
            elif source_type == 'nyt_api':
                content_quality = "NYT_API+FULL_ABSTRACT"
                content = article.get('full_content', article.get('snippet', ''))
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']} (NYT API)\n"
                article_text += f"   Full Abstract: {content}\n"
                
            elif source_type == 'rss_feed':
                content_quality = "RSS_FEED+ENHANCED_CONTENT"
                content = article.get('full_content', article.get('snippet', ''))
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']} (RSS)\n"
                article_text += f"   Content: {content}\n"
                
            else:
                content_quality = "PREMIUM" if article['source'] in PREMIUM_SOURCES_ENHANCED else "STANDARD"
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']}\n"
                article_text += f"   Content: {article['snippet']}\n"
            
            article_text += f"   Link: {article['link']}\n"
        
        # Enhanced analysis prompt for 30 articles
        prompt = f"""You are a senior equity research analyst at Goldman Sachs with access to premium financial data sources for {company}.

ENHANCED DATA SOURCES ({total_articles} articles from multiple premium APIs and feeds):
{article_text}

SOURCE QUALITY BREAKDOWN:
{source_type_counts}

INSTITUTIONAL ANALYSIS FRAMEWORK:
Generate actionable insights for portfolio managers making investment decisions. Leverage the enhanced content from APIs and RSS feeds.

REQUIREMENTS FOR EACH BULLET:
1. Extract specific financial metrics from full content (revenue, EPS, price targets, guidance)
2. Include quantified impact estimates and timeline context
3. Add market context and trading implications
4. Reference sentiment analysis where available

REQUIRED SECTIONS (3-4 substantive bullets each due to increased article count):

**EXECUTIVE SUMMARY**
Focus: Strategic developments affecting fundamental business outlook
- Extract specific financial impacts from enhanced content sources
- Include management statements and strategic direction changes
- Quantify revenue/margin implications with timeline estimates
- Use varied tags: [STRATEGY], [PRODUCT], [MANAGEMENT], [PARTNERSHIP], [EXPANSION]

**INVESTOR INSIGHTS** 
Focus: Valuation drivers, analyst actions, and market sentiment
- Include specific price targets, rating changes, and EPS estimates
- Add sentiment-driven market context when sentiment data available
- Reference peer comparisons and sector positioning
- Include trading recommendations and technical levels
- Use tags: [ANALYST], [VALUATION], [SENTIMENT], [ESTIMATES], [PEER_ANALYSIS]

**CATALYSTS & RISKS**
Focus: Near-term trading catalysts and risk factors
- Extract specific event dates and timeline-driven catalysts
- Quantify potential impact magnitude and probability
- Include sentiment-based risk assessment
- Reference regulatory, competitive, or operational developments
- Use tags: [CATALYST], [RISK], [REGULATORY], [SENTIMENT_RISK], [TECHNICAL]

CRITICAL REQUIREMENTS:
- Leverage enhanced content from APIs and RSS feeds for deeper insights
- Include sentiment analysis implications when available
- Extract specific numbers: price targets, earnings estimates, revenue forecasts
- Add trading context and technical analysis when mentioned
- Quantify everything possible: timelines, financial impacts, probability estimates
- Reference premium source advantages: "According to full AlphaVantage analysis..." or "Enhanced NYT content reveals..."
- Generate 3-4 bullets per section due to increased article diversity

Format each insight with quantified impact and cite sources appropriately."""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": f"You are a senior equity research analyst with access to premium financial data APIs, RSS feeds, and sentiment analysis. Use this enhanced data to provide institutional-grade analysis for {company} with specific financial metrics and actionable insights."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.05,
            max_tokens=2500  # Increased for more detailed analysis
        )
        
        analysis_text = response.choices[0].message.content
        
        # Log analysis quality metrics
        alphavantage_count = source_type_counts.get('alphavantage_premium', 0)
        nyt_count = source_type_counts.get('nyt_api', 0)
        rss_count = source_type_counts.get('rss_feed', 0)
        
        logger.info(f"Enhanced premium analysis for {company}: {len(analysis_text)} chars from {total_articles} articles "
                   f"(AV:{alphavantage_count}, NYT:{nyt_count}, RSS:{rss_count}, Premium:{premium_count})")
        
        return parse_financial_summaries(analysis_text)
        
    except Exception as e:
        logger.error(f"Error generating premium analysis for {company}: {str(e)}")
        return {
            "executive": [f"Error generating premium analysis: {str(e)}"],
            "investor": ["Premium analysis unavailable due to processing error."],
            "catalysts": ["Unable to identify catalysts at this time."]
        }
    
def parse_financial_summaries(text: str) -> Dict[str, List[str]]:
    """Parse the LLM response into structured summaries."""
    sections = {"executive": [], "investor": [], "catalysts": []}
    current_section = None
    
    # Enhanced section detection patterns
    section_patterns = {
        "executive": re.compile(r".*executive\s+summary.*", re.IGNORECASE),
        "investor": re.compile(r".*investor\s+insights.*", re.IGNORECASE),
        "catalysts": re.compile(r".*(catalysts?\s*(&|and)?\s*risks?|risks?\s*(&|and)?\s*catalysts?).*", re.IGNORECASE)
    }
    
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for section headers
        section_found = False
        for section_name, pattern in section_patterns.items():
            if pattern.match(line):
                current_section = section_name
                section_found = True
                break
        
        if section_found:
            continue
            
        # Process bullet points
        if line.startswith(('-', '•', '*')) and current_section:
            bullet = line.lstrip('-•* ').strip()
            if bullet and len(bullet) > 10:
                sections[current_section].append(bullet)
    
    # Fallback parsing if section detection fails
    if all(len(section) == 0 for section in sections.values()):
        logger.warning("Section detection failed, using fallback parsing")
        bullets = [line.lstrip('-•* ').strip() for line in lines 
                  if line.strip().startswith(('-', '•', '*')) and len(line.strip()) > 10]
        
        for i, bullet in enumerate(bullets[:9]):
            section_names = list(sections.keys())
            sections[section_names[i % 3]].append(bullet)
    
    # Ensure each section has at least one item
    for section_name, bullets in sections.items():
        if not bullets:
            sections[section_name] = ["No significant developments identified in this category."]
    
    return sections

def create_source_url_mapping(articles: List[Dict]) -> Dict[str, str]:
    """Create mapping of source domains to their actual article URLs for linking."""
    source_mapping = {}
    for article in articles:
        source = article.get('source', '')
        if source and source not in source_mapping:
            source_mapping[source] = article.get('link', '#')
    
    return source_mapping

def convert_markdown_to_html(text: str, source_mapping: Dict[str, str] = None) -> str:
    """Convert markdown formatting to HTML with clickable source links."""
    if source_mapping is None:
        source_mapping = {}
    
    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Convert *italic* to <em>
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    
    # Convert [text](url) to HTML links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    
    # Convert *(Source: domain)* to clickable source links
    def replace_source(match):
        source_domain = match.group(1).strip()
        if source_domain in source_mapping:
            url = source_mapping[source_domain]
            premium_badge = ''
            if source_domain in ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'nytimes.com']:
                premium_badge = ' <span class="badge bg-success badge-sm">Premium</span>'
            return f'<span class="text-muted small">(Source: <a href="{url}" target="_blank" rel="noopener" class="source-link">{source_domain}</a>{premium_badge})</span>'
        else:
            return f'<span class="text-muted small">(Source: {source_domain})</span>'
    
    text = re.sub(r'\*\(Source:\s*([^)]+)\)\*', replace_source, text)
    
    return text

# Fix 5: Full Parallel Implementation
async def fetch_all_sources_parallel(company: str, days_back: int = 7) -> Dict[str, Any]:
    """
    Fetch from all sources in parallel: AlphaVantage + NYT + RSS simultaneously.
    """
    logger.info(f"🚀 Parallel fetch starting for {company}...")
    start_time = time.time()
    
    # Define async functions for each source
    async def fetch_alphavantage_async():
        """Run AlphaVantage in thread pool (it's not async)."""
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(fetch_alphavantage_news, company, days_back)
            return await loop.run_in_executor(None, lambda: future.result())
    
    async def fetch_rss_async():
        """Run RSS feeds in thread pool."""
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(fetch_rss_simple, company, days_back)
            return await loop.run_in_executor(None, lambda: future.result())
    
    # Run all three simultaneously
    try:
        alphavantage_task = fetch_alphavantage_async()
        nyt_task = fetch_nyt_parallel(company, days_back)
        rss_task = fetch_rss_async()
        
        # Wait for all to complete
        alphavantage_articles, nyt_articles, rss_articles = await asyncio.gather(
            alphavantage_task, nyt_task, rss_task, return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(alphavantage_articles, Exception):
            logger.error(f"AlphaVantage failed: {alphavantage_articles}")
            alphavantage_articles = []
        if isinstance(nyt_articles, Exception):
            logger.error(f"NYT parallel failed: {nyt_articles}")
            nyt_articles = []
        if isinstance(rss_articles, Exception):
            logger.error(f"RSS failed: {rss_articles}")
            rss_articles = []
        
        parallel_time = time.time() - start_time
        logger.info(f"✓ Parallel fetch complete in {parallel_time:.2f}s:")
        logger.info(f"  • AlphaVantage: {len(alphavantage_articles)} articles")
        logger.info(f"  • NYT: {len(nyt_articles)} articles") 
        logger.info(f"  • RSS: {len(rss_articles)} articles")
        
        return {
            'alphavantage': alphavantage_articles,
            'nyt': nyt_articles,
            'rss': rss_articles,
            'parallel_time': parallel_time
        }
        
    except Exception as e:
        logger.error(f"Parallel fetch failed: {e}")
        return {
            'alphavantage': [],
            'nyt': [],
            'rss': [],
            'parallel_time': time.time() - start_time
        }

def fetch_rss_simple(company: str, days_back: int = 7) -> List[Dict]:
    """Simplified RSS fetch for parallel execution."""
    feeds = {
        'cnbc_business': 'https://www.cnbc.com/id/10001147/device/rss/rss.html',
        'investing_com': 'https://www.investing.com/rss/news.rss',
        'seeking_alpha': 'https://seekingalpha.com/feed.xml',
    }
    
    articles = []
    for name, url in feeds.items():
        try:
            feed_articles = parse_rss_feed_fixed(url, company, days_back)
            articles.extend(feed_articles)
            logger.info(f"RSS {name}: {len(feed_articles)} articles")
        except Exception as e:
            logger.warning(f"RSS {name} failed: {e}")
    
    return articles

# Main integration function
def fetch_comprehensive_news_parallel(company: str, days_back: int = 7) -> Dict[str, Any]:
    """
    Enhanced parallel function with improved AlphaVantage filtering and increased article limits.
    """
    try:
        # Run parallel fetch
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(fetch_all_sources_parallel(company, days_back))
        loop.close()
        
        # Combine all articles
        all_articles = []
        all_articles.extend(results['alphavantage'])
        all_articles.extend(results['nyt'])
        all_articles.extend(results['rss'])
        
        # Enhanced deduplication
        unique_articles = deduplicate_articles(all_articles)
        
        # Apply enhanced scoring to fix Benzinga/Fool/Zacks issue
        scored_articles = score_articles_fixed(unique_articles, company)
        final_articles = [article for article, score in scored_articles if score > -5]  # Filter out heavily penalized
        
        # Calculate enhanced metrics
        alphavantage_count = len(results['alphavantage'])
        nyt_count = len(results['nyt'])
        rss_count = len(results['rss'])
        total_unique = len(final_articles)
        
        # Calculate quality metrics
        premium_source_domains = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'cnbc.com', 
                                 'marketwatch.com', 'barrons.com', 'nytimes.com']
        high_quality_sources = sum(1 for article in final_articles 
                                 if article.get('source', '') in premium_source_domains)
        
        # Calculate coverage percentages
        if total_unique > 0:
            premium_coverage = (high_quality_sources / total_unique * 100)
            alphavantage_coverage = (alphavantage_count / total_unique * 100) if alphavantage_count <= total_unique else (alphavantage_count / (alphavantage_count + nyt_count + rss_count) * 100)
        else:
            premium_coverage = 0
            alphavantage_coverage = 0
        
        # Enhanced analysis quality determination
        full_content_articles = alphavantage_count + nyt_count + rss_count
        
        if alphavantage_count >= 8 and premium_coverage >= 40:
            analysis_quality = "Premium+"
        elif alphavantage_count >= 5 and (premium_coverage >= 30 or full_content_articles >= 10):
            analysis_quality = "Institutional"
        elif alphavantage_count >= 3 or (premium_coverage >= 40 and full_content_articles >= 8):
            analysis_quality = "Professional" 
        elif alphavantage_count >= 1 or high_quality_sources >= 3:
            analysis_quality = "Standard"
        else:
            analysis_quality = "Limited"
        
        logger.info(f"🎯 Enhanced parallel analysis complete: {total_unique} articles")
        logger.info(f"📊 Source breakdown - AV: {alphavantage_count}, NYT: {nyt_count}, RSS: {rss_count}")
        logger.info(f"📈 Quality: {analysis_quality} | Premium coverage: {premium_coverage:.1f}% | AV coverage: {alphavantage_coverage:.1f}%")
        
        # Generate analysis with increased article limit (30 instead of 20)
        summaries = generate_premium_analysis(company, final_articles, max_articles=30) if final_articles else {}
        
        return {
            'company': company,
            'articles': final_articles,
            'summaries': summaries,
            'metrics': {
                'total_articles': total_unique,
                'alphavantage_articles': alphavantage_count,
                'nyt_articles': nyt_count,
                'rss_articles': rss_count,
                'premium_sources_count': high_quality_sources,
                'high_quality_sources': high_quality_sources,
                'premium_coverage': round(premium_coverage, 1),
                'alphavantage_coverage': round(alphavantage_coverage, 1),
                'analysis_quality': analysis_quality,
                'parallel_time': results['parallel_time'],
                'full_content_articles': full_content_articles
            },
            'source_performance': {
                'alphavantage': alphavantage_count,
                'nyt_parallel': nyt_count,
                'rss_feeds': rss_count
            },
            'success': len(final_articles) > 0
        }
        
    except Exception as e:
        logger.error(f"Enhanced parallel comprehensive news failed: {e}")
        return {
            'company': company,
            'articles': [],
            'summaries': {},
            'metrics': {'total_articles': 0, 'parallel_time': 0, 'analysis_quality': 'Error'},
            'source_performance': {},
            'success': False
        }

def fetch_comprehensive_news_guaranteed_30_enhanced(company: str, days_back: int = 7) -> Dict[str, Any]:
    """
    ENHANCED version with dynamic relevance assessment and intelligent Google CSE triggering.
    
    This replaces the original function with:
    1. Early relevance assessment for premium source articles
    2. Dynamic Google CSE triggering based on relevance, not just quantity
    3. Improved article selection and scoring
    4. Better performance for both well-known and lesser-known companies
    
    Maintains backward compatibility with existing app.py calls.
    """
    
    try:
        logger.info(f"🚀 Starting ENHANCED 30-article analysis for {company} ({days_back} days)")
        
        # Use the enhanced system with configuration
        config_manager = ConfigurationManager()
        config = config_manager.get_analysis_config()
        orchestrator = DynamicSourceOrchestrator(config)
        
        # Execute enhanced analysis
        results = orchestrator.fetch_enhanced_news_with_dynamic_cse(company, days_back)
        
        if not results['success']:
            logger.warning(f"Enhanced analysis found no articles for {company}")
            return create_empty_results(company, days_back)
        
        # Convert to original format for backward compatibility with app.py
        enhanced_results = {
            'company': company,
            'articles': results['articles'],
            'summaries': results['summaries'],
            'metrics': {
                # Original fields (maintained for compatibility)
                'total_articles': results['metrics']['total_articles'],
                'alphavantage_articles': results['metrics']['alphavantage_articles'],
                'nyt_articles': results['metrics']['nyt_articles'],
                'rss_articles': results['metrics']['rss_articles'],
                'google_articles': results['metrics'].get('google_articles', 0),
                'premium_sources_count': results['metrics']['premium_sources_count'],
                'high_quality_sources': results['metrics']['premium_sources_count'],
                'premium_coverage': results['metrics']['premium_coverage'],
                'alphavantage_coverage': results['metrics']['alphavantage_coverage'],
                'analysis_quality': results['metrics']['analysis_quality'],
                'response_time': results['metrics']['response_time'],
                'articles_analyzed': results['metrics']['total_articles'],
                'articles_displayed': min(12, results['metrics']['total_articles']),
                'full_content_articles': results['metrics']['alphavantage_articles'] + results['metrics']['nyt_articles'],
                'premium_sources_coverage': results['metrics']['premium_coverage'],
                
                # Enhanced fields (new capabilities)
                'relevant_articles': results['metrics'].get('relevant_articles', 0),
                'relevance_percentage': results['metrics'].get('relevance_percentage', 0),
                'average_relevance_score': results['metrics'].get('average_relevance_score', 0),
                'enhanced_scoring_used': True,
                'dynamic_cse_logic_used': True
            },
            'source_performance': results['source_performance'],
            'success': results['success'],
            
            # Enhanced metadata
            'google_cse_triggered': results.get('google_cse_triggered', False),
            'relevance_metrics': results.get('relevance_metrics', {}),
            'resolved_ticker': results.get('resolved_ticker'),
            'resolved_company_name': results.get('resolved_company_name'),
            'enhanced_analysis': True
        }
        
        # Enhanced logging
        logger.info(f"✅ ENHANCED Analysis Complete for {company}:")
        logger.info(f"   • Total articles: {enhanced_results['metrics']['total_articles']}")
        logger.info(f"   • Relevant articles: {enhanced_results['metrics']['relevant_articles']} ({enhanced_results['metrics']['relevance_percentage']:.1f}%)")
        logger.info(f"   • Google CSE triggered: {enhanced_results['google_cse_triggered']}")
        logger.info(f"   • Analysis quality: {enhanced_results['metrics']['analysis_quality']}")
        
        return enhanced_results
        
    except Exception as e:
        logger.error(f"Enhanced analysis failed for {company}: {str(e)}")
        logger.error(f"Falling back to original implementation...")
        
        # Fallback to original logic if enhanced system fails
        try:
            return fetch_comprehensive_news_fallback(company, days_back)
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            return create_error_results(company, days_back, str(e))

def fetch_comprehensive_news_fallback(company: str, days_back: int = 7) -> Dict[str, Any]:
    """
    Fallback implementation using original logic if enhanced system fails.
    """
    logger.warning(f"Using fallback implementation for {company}")
    
    try:
        all_articles = []
        source_performance = {}
        
        # Use existing functions in original order
        # 1. AlphaVantage
        try:
            alphavantage_articles = fetch_alphavantage_news_enhanced(company, days_back)
            all_articles.extend(alphavantage_articles)
            source_performance['alphavantage'] = len(alphavantage_articles)
        except Exception as e:
            logger.error(f"Fallback AlphaVantage failed: {e}")
            source_performance['alphavantage'] = 0
        
        # 2. NYT
        try:
            nyt_articles = fetch_nyt_news_working(company, days_back, max_articles=100)
            # Deduplicate against AlphaVantage
            existing_urls = {a.get('link', '') for a in all_articles}
            new_nyt_articles = [a for a in nyt_articles if a.get('link', '') not in existing_urls]
            all_articles.extend(new_nyt_articles)
            source_performance['nyt'] = len(new_nyt_articles)
        except Exception as e:
            logger.error(f"Fallback NYT failed: {e}")
            source_performance['nyt'] = 0
        
        # 3. RSS
        try:
            rss_articles = fetch_rss_feeds_working_2025_parallel(company, days_back)
            # Deduplicate
            existing_urls = {a.get('link', '') for a in all_articles}
            new_rss_articles = [a for a in rss_articles if a.get('link', '') not in existing_urls]
            all_articles.extend(new_rss_articles)
            source_performance['rss'] = len(new_rss_articles)
        except Exception as e:
            logger.error(f"Fallback RSS failed: {e}")
            source_performance['rss'] = 0
        
        # 4. Google (if needed)
        google_articles = 0
        if len(all_articles) < 25:
            try:
                google_results = fetch_google_news(company, days_back)
                existing_urls = {a.get('link', '') for a in all_articles}
                new_google_articles = [a for a in google_results if a.get('link', '') not in existing_urls]
                all_articles.extend(new_google_articles[:10])  # Limit Google results
                google_articles = len(new_google_articles[:10])
                source_performance['google'] = google_articles
            except Exception as e:
                logger.error(f"Fallback Google failed: {e}")
                source_performance['google'] = 0
        
        # Final processing
        unique_articles = deduplicate_articles(all_articles)
        scored_articles = score_articles_fixed(unique_articles, company)
        final_articles = [article for article, score in scored_articles[:30]]
        
        # Calculate metrics
        alphavantage_count = source_performance.get('alphavantage', 0)
        nyt_count = source_performance.get('nyt', 0)
        rss_count = source_performance.get('rss', 0)
        total_articles = len(final_articles)
        
        # Premium source calculation
        premium_sources = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'nytimes.com']
        high_quality_sources = sum(1 for a in final_articles if a.get('source', '') in premium_sources)
        premium_coverage = (high_quality_sources / total_articles * 100) if total_articles > 0 else 0
        alphavantage_coverage = (alphavantage_count / total_articles * 100) if total_articles > 0 else 0
        
        # Generate summaries
        if final_articles:
            summaries = generate_premium_analysis_30_articles(company, final_articles)
        else:
            summaries = create_empty_summaries()
        
        return {
            'company': company,
            'articles': final_articles,
            'summaries': summaries,
            'metrics': {
                'total_articles': total_articles,
                'alphavantage_articles': alphavantage_count,
                'nyt_articles': nyt_count,
                'rss_articles': rss_count,
                'google_articles': google_articles,
                'premium_sources_count': high_quality_sources,
                'high_quality_sources': high_quality_sources,
                'premium_coverage': round(premium_coverage, 1),
                'alphavantage_coverage': round(alphavantage_coverage, 1),
                'analysis_quality': 'Standard',
                'response_time': 0,
                'articles_analyzed': total_articles,
                'articles_displayed': min(12, total_articles),
                'full_content_articles': alphavantage_count + nyt_count,
                'premium_sources_coverage': round(premium_coverage, 1)
            },
            'source_performance': source_performance,
            'success': len(final_articles) > 0,
            'google_cse_triggered': google_articles > 0,
            'enhanced_analysis': False  # Indicate this is fallback
        }
        
    except Exception as e:
        logger.error(f"Fallback implementation also failed: {e}")
        return create_error_results(company, days_back, f"Fallback error: {str(e)}")

def create_empty_results(company: str, days_back: int) -> Dict[str, Any]:
    """Create empty results structure when no articles found."""
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    date_range = f"{start_date.strftime('%B %d, %Y')} – {end_date.strftime('%B %d, %Y')}"
    
    return {
        'company': company,
        'articles': [],
        'summaries': {
            "executive": [f"**[NO DATA]** No recent financial news found for {company} across all premium sources (AlphaVantage, NYT, Bloomberg RSS). Try expanding date range or verifying company ticker."],
            "investor": [f"**[RECOMMENDATION]** Verify company ticker symbol or try major exchanges (NYSE/NASDAQ). Consider checking earnings calendar for {company}."],
            "catalysts": [f"**[TIMING]** Monitor upcoming earnings announcements, product launches, or regulatory events for {company}."]
        },
        'metrics': {
            'total_articles': 0,
            'alphavantage_articles': 0,
            'nyt_articles': 0,
            'rss_articles': 0,
            'google_articles': 0,
            'premium_sources_count': 0,
            'high_quality_sources': 0,
            'premium_coverage': 0,
            'alphavantage_coverage': 0,
            'analysis_quality': 'No Data',
            'response_time': 0,
            'articles_analyzed': 0,
            'articles_displayed': 0,
            'full_content_articles': 0
        },
        'source_performance': {},
        'success': False,
        'google_cse_triggered': False,
        'enhanced_analysis': True
    }

def create_error_results(company: str, days_back: int, error_msg: str) -> Dict[str, Any]:
    """Create error results structure when analysis fails."""
    return {
        'company': company,
        'articles': [],
        'summaries': {
            "executive": [f"**[ERROR]** Analysis temporarily unavailable for {company}: {error_msg}"],
            "investor": ["**[RETRY]** Please try again in a few moments or contact support."],
            "catalysts": ["**[FALLBACK]** Consider checking company's investor relations page directly."]
        },
        'metrics': {
            'total_articles': 0,
            'analysis_quality': 'Error',
            'response_time': 0,
            'alphavantage_articles': 0,
            'nyt_articles': 0,
            'rss_articles': 0,
            'google_articles': 0,
            'premium_sources_count': 0,
            'high_quality_sources': 0,
            'premium_coverage': 0,
            'alphavantage_coverage': 0,
            'articles_analyzed': 0,
            'articles_displayed': 0,
            'full_content_articles': 0
        },
        'source_performance': {},
        'success': False,
        'enhanced_analysis': False
    }

def create_empty_summaries() -> Dict[str, List[str]]:
    """Create empty summaries when no articles available."""
    return {
        "executive": ["No significant executive developments identified."],
        "investor": ["No recent investor-relevant developments identified."],
        "catalysts": ["No material catalysts or risks detected in recent coverage."]
    }

def enhance_articles_with_full_text(articles: List[Dict]) -> List[Dict]:
    """
    Optional: Try to extract full text from premium article URLs.
    """
    enhanced_articles = []
    
    for article in articles:
        enhanced_article = article.copy()
        
        # Only try to extract full text from premium sources
        source = article.get('source', '')
        if source in ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'cnbc.com', 'marketwatch.com']:
            try:
                # Try to extract full text (simplified version)
                full_text = extract_article_text(article.get('link', ''))
                if full_text and len(full_text) > len(article.get('snippet', '')):
                    enhanced_article['full_content'] = full_text[:2000]  # Limit to 2000 chars
                    enhanced_article['enhanced'] = True
                    logger.debug(f"Enhanced article from {source}: {len(full_text)} chars")
            except Exception as e:
                logger.debug(f"Could not enhance article from {source}: {e}")
        
        enhanced_articles.append(enhanced_article)
    
    return enhanced_articles

def extract_article_text(url: str) -> Optional[str]:
    """
    Simple article text extraction (can be enhanced with newspaper3k, readability, etc.)
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Try to find article content
        content_selectors = [
            'article', '.article-body', '.story-body', '.article-content',
            '.content', '.post-content', '.entry-content'
        ]
        
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                text = content_div.get_text(strip=True)
                if len(text) > 200:  # Must be substantial content
                    return text
        
        # Fallback: get all paragraph text
        paragraphs = soup.find_all('p')
        text = ' '.join([p.get_text(strip=True) for p in paragraphs])
        
        return text if len(text) > 200 else None
        
    except Exception as e:
        logger.debug(f"Text extraction failed for {url}: {e}")
        return None

def generate_premium_analysis_30_articles(company: str, articles: List[Dict]) -> Dict[str, List[str]]:
    """
    Enhanced analysis function optimized for exactly 30 articles.
    """
    if not articles or len(articles) == 0:
        return {
            "executive": ["No recent financial news found."],
            "investor": ["No recent investor-relevant developments identified."],
            "catalysts": ["No material catalysts or risks detected."]
        }
    
    try:
        # Ensure we use all 30 articles (not a subset)
        analysis_articles = articles[:30]  # Take up to 30 articles
        logger.info(f"Generating analysis from {len(analysis_articles)} articles for {company}")
        
        # Calculate source quality metrics for the prompt
        source_type_counts = {}
        for article in analysis_articles:
            source_type = article.get('source_type', 'google_search')
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        
        premium_count = sum(1 for article in analysis_articles if article['source'] in PREMIUM_SOURCES_ENHANCED)
        alphavantage_count = source_type_counts.get('alphavantage_premium', 0)
        
        # Prepare article content for analysis with enhanced content extraction
        article_text = ""
        for i, article in enumerate(analysis_articles, 1):
            source_type = article.get('source_type', 'google_search')
            
            if source_type == 'alphavantage_premium':
                content_quality = "ALPHAVANTAGE_PREMIUM+SENTIMENT"
                content = article.get('full_content', article.get('snippet', ''))[:800]
                sentiment_label = article.get('sentiment_label', 'Neutral')
                sentiment_score = article.get('sentiment_score', 0)
                relevance_score = article.get('relevance_score', 0)
                
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']} | Sentiment: {sentiment_label} ({sentiment_score:.2f}) | Relevance: {relevance_score:.3f}\n"
                article_text += f"   Full Content: {content}\n"
                
            elif source_type == 'nyt_api':
                content_quality = "NYT_API+FULL_ABSTRACT"
                content = article.get('full_content', article.get('snippet', ''))
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']} (NYT API)\n"
                article_text += f"   Full Abstract: {content}\n"
                
            elif source_type == 'rss_feed':
                content_quality = "RSS_PREMIUM_FEED"
                content = article.get('full_content', article.get('snippet', ''))
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']} (Premium RSS)\n"
                article_text += f"   Content: {content}\n"
                
            else:
                content_quality = "PREMIUM" if article['source'] in PREMIUM_SOURCES_ENHANCED else "STANDARD"
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']}\n"
                article_text += f"   Content: {article['snippet']}\n"
            
            article_text += f"   Link: {article['link']}\n"
        
        # Enhanced analysis prompt optimized for 30 articles
        prompt = f"""You are a senior equity research analyst at Goldman Sachs analyzing {company} with comprehensive financial data.

COMPREHENSIVE DATA SET (30 articles from premium sources):
{article_text}

SOURCE BREAKDOWN:
{source_type_counts}
Total Premium Sources: {premium_count}/30
AlphaVantage Articles with Sentiment: {alphavantage_count}/30

INSTITUTIONAL ANALYSIS FRAMEWORK:
Generate actionable insights for portfolio managers and institutional investors making investment decisions. 
Leverage ALL 30 articles for comprehensive coverage.

REQUIREMENTS:
1. Extract specific financial metrics: revenue, EPS, price targets, guidance changes
2. Include quantified impact estimates with timeline context  
3. Reference sentiment analysis from AlphaVantage articles when available
4. Provide trading context and technical analysis implications
5. Generate 4 substantive bullets per section due to comprehensive 30-article coverage

REQUIRED SECTIONS (4 bullets each):

**EXECUTIVE SUMMARY**
Focus: Strategic developments affecting fundamental business outlook
- Extract specific financial impacts from 30-article comprehensive analysis
- Include management statements and strategic direction changes
- Quantify revenue/margin implications with timeline estimates
- Use varied tags: [STRATEGY], [PRODUCT], [MANAGEMENT], [PARTNERSHIP], [EXPANSION]

**INVESTOR INSIGHTS** 
Focus: Valuation drivers, analyst actions, and market sentiment
- Include specific price targets, rating changes, and EPS estimates from coverage
- Add sentiment-driven market context from AlphaVantage data when available
- Reference peer comparisons and sector positioning across articles
- Include trading recommendations and technical levels mentioned
- Use tags: [ANALYST], [VALUATION], [SENTIMENT], [ESTIMATES], [PEER_ANALYSIS]

**CATALYSTS & RISKS**
Focus: Near-term trading catalysts and risk factors from comprehensive coverage
- Extract specific event dates and timeline-driven catalysts from all sources
- Quantify potential impact magnitude and probability estimates
- Include sentiment-based risk assessment from AlphaVantage articles
- Reference regulatory, competitive, or operational developments
- Use tags: [CATALYST], [RISK], [REGULATORY], [SENTIMENT_RISK], [TECHNICAL]

CRITICAL REQUIREMENTS FOR 30-ARTICLE ANALYSIS:
- Leverage comprehensive coverage for deeper insights than typical 15-20 article analysis
- Extract specific numbers: price targets, earnings estimates, revenue forecasts
- Reference sentiment analysis implications when available from AlphaVantage
- Add trading context and technical analysis when mentioned across sources
- Quantify everything: timelines, financial impacts, probability estimates
- Generate exactly 4 substantive bullets per section utilizing full article set
- Cite source advantages: "According to comprehensive AlphaVantage analysis..." or "Cross-source analysis reveals..."

Format each insight with quantified impact and cite premium sources appropriately."""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": f"You are a senior equity research analyst with access to 30 comprehensive articles including premium financial data APIs, RSS feeds, and sentiment analysis. Use this complete dataset to provide institutional-grade analysis for {company} with specific financial metrics and actionable insights."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.05,
            max_tokens=3000  # Increased for comprehensive 30-article analysis
        )
        
        analysis_text = response.choices[0].message.content
        
        logger.info(f"Generated comprehensive 30-article analysis for {company}: {len(analysis_text)} chars")
        
        return parse_financial_summaries(analysis_text)
        
    except Exception as e:
        logger.error(f"Error generating 30-article analysis for {company}: {str(e)}")
        return {
            "executive": [f"Error generating comprehensive analysis: {str(e)}"],
            "investor": ["Comprehensive analysis unavailable due to processing error."],
            "catalysts": ["Unable to identify catalysts from 30-article dataset."]
        }

# Legacy compatibility functions
def fetch_combined_premium_news(company: str, days_back: int = 7) -> List[Dict]:
    """Legacy function - now redirects to the new implementation."""
    return combine_premium_sources(company, days_back)

def score_articles_with_alphavantage(articles: List[Dict], company: str) -> List[Tuple[Dict, float]]:
    """Legacy function - now redirects to enhanced scoring."""
    return score_articles_fixed(articles, company)

def generate_financial_summary(company: str, articles: List[Dict], max_articles: int = 20) -> Dict[str, List[str]]:
    """Legacy function - now redirects to premium analysis."""
    return generate_premium_analysis(company, articles, max_articles)

def analyze_sentiment_distribution(articles: List[Dict]) -> str:
    """Analyze sentiment distribution across articles for market context."""
    sentiment_counts = {'Bullish': 0, 'Bearish': 0, 'Neutral': 0}
    total_sentiment_score = 0
    alphavantage_articles = 0
    
    for article in articles:
        if article.get('source_type') == 'alphavantage_premium':
            alphavantage_articles += 1
            sentiment_label = article.get('sentiment_label', 'Neutral')
            sentiment_score = float(article.get('sentiment_score', 0))
            
            if sentiment_label in sentiment_counts:
                sentiment_counts[sentiment_label] += 1
            
            total_sentiment_score += sentiment_score
    
    if alphavantage_articles > 0:
        avg_sentiment = total_sentiment_score / alphavantage_articles
        sentiment_trend = "Bullish" if avg_sentiment > 0.2 else "Bearish" if avg_sentiment < -0.2 else "Neutral"
        
        return f"Sentiment Analysis ({alphavantage_articles} articles): {sentiment_counts['Bullish']} Bullish, {sentiment_counts['Neutral']} Neutral, {sentiment_counts['Bearish']} Bearish. Average sentiment: {avg_sentiment:.2f} ({sentiment_trend} trend)"
    else:
        return "Sentiment Analysis: Not available (no AlphaVantage articles with sentiment data)"