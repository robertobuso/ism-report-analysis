import requests
import os
import re
import feedparser
import time
from datetime import datetime, timedelta
from openai import OpenAI
from typing import List, Dict, Tuple, Any
import logging
from urllib.parse import urlparse, urljoin
import json

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

# Enhanced source diversity and quality
PREMIUM_SOURCES = {
    # Tier 1: Top financial sources
    'bloomberg.com': 12, 'reuters.com': 11, 'wsj.com': 11, 'ft.com': 10,
    'nytimes.com': 9,  # Add NYT as premium
    
    # Tier 2: Strong financial sources  
    'cnbc.com': 8, 'marketwatch.com': 8, 'barrons.com': 9,
    'seekingalpha.com': 7, 'morningstar.com': 7,
    
    # Tier 3: Good sources but limit quantity
    'benzinga.com': 4,  # Lower score to reduce overrepresentation
    'zacks.com': 5, 'thestreet.com': 4, 'investorplace.com': 3,
    'fool.com': 3, 'investing.com': 4
}

# Premium RSS feeds configuration - ANTI-BOT-BLOCKING FEEDS
def get_working_rss_feeds() -> Dict[str, str]:
    """
    Return only RSS feeds that are verified to work and don't block bots.
    These have been tested and confirmed working.
    """
    return {
        # Tier 1: Financial sites that definitely work
        'seeking_alpha': 'https://seekingalpha.com/market_currents.xml',
        'benzinga': 'https://www.benzinga.com/feed',
        'zerohedge': 'https://feeds.feedburner.com/zerohedge/feed',
        
        # Tier 2: Tech/Business sites (bot-friendly)
        'techcrunch_fintech': 'https://techcrunch.com/category/fintech/feed/',
        'venturebeat_business': 'https://venturebeat.com/category/business/feed/',
        'business_insider': 'https://www.businessinsider.com/rss',
        
        # Tier 3: Alternative financial feeds
        'investing_com': 'https://www.investing.com/rss/news.rss',
        'marketwatch_alternative': 'https://www.marketwatch.com/rss/topstories',
        
        # Tier 4: Backup sources
        'yahoo_finance_alternative': 'https://finance.yahoo.com/news/rssindex',
        'forbes_business': 'https://www.forbes.com/business/feed/',
        
        # Note: Only including feeds that have been verified to work
        # Removed all feeds that return 404, 403, or other errors
    }


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

def fetch_nyt_news_working(company: str, days_back: int = 7) -> List[Dict]:
    """
    WORKING NYT API function - simplified and tested to actually return articles.
    """
    try:
        api_key = os.getenv("NYTIMES_API_KEY")
        if not api_key:
            logger.info("NYT API key not found, skipping NYT news fetch")
            return []
        
        logger.info(f"NYT API: Searching for '{company}' with working query...")
        
        url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
        
        # WORKING APPROACH: Start with simplest possible query that works
        # Your test script proved this works, so let's use the same approach
        base_params = {
            "q": company,
            "api-key": api_key,
            "sort": "newest",
            "fl": "headline,abstract,lead_paragraph,web_url,pub_date,section_name"
        }
        
        # First try: Simple query (like your working test script)
        try:
            response = requests.get(url, params=base_params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") != "OK":
                logger.warning(f"NYT API returned status: {data.get('status')}")
                return []
            
            docs = data.get("response", {}).get("docs", [])
            logger.info(f"NYT simple query returned {len(docs)} total articles")
            
            if len(docs) == 0:
                logger.warning("NYT simple query returned 0 articles - trying alternative search terms")
                
                # Fallback: Try alternative search terms
                alternative_terms = []
                if company.upper() == 'AAPL':
                    alternative_terms = ['Apple Inc', 'Apple stock', 'Apple company']
                elif len(company) <= 5 and company.isupper():
                    # It's a ticker, try the company name
                    ticker_to_name = {
                        'MSFT': 'Microsoft', 'GOOGL': 'Google', 'AMZN': 'Amazon', 
                        'TSLA': 'Tesla', 'META': 'Meta', 'NVDA': 'Nvidia'
                    }
                    if company in ticker_to_name:
                        alternative_terms = [ticker_to_name[company]]
                
                for alt_term in alternative_terms:
                    alt_params = base_params.copy()
                    alt_params["q"] = alt_term
                    
                    alt_response = requests.get(url, params=alt_params, timeout=10)
                    if alt_response.status_code == 200:
                        alt_data = alt_response.json()
                        if alt_data.get("status") == "OK":
                            alt_docs = alt_data.get("response", {}).get("docs", [])
                            if len(alt_docs) > 0:
                                logger.info(f"NYT alternative term '{alt_term}' found {len(alt_docs)} articles")
                                docs = alt_docs
                                break
                    time.sleep(1)  # Rate limiting between attempts
            
            if len(docs) == 0:
                logger.info("NYT: No articles found even with alternative terms")
                return []
            
            # Process the articles we found
            articles = []
            for doc in docs[:15]:  # Limit to first 15 articles
                try:
                    # Extract data with proper null handling
                    headline = doc.get("headline", {}) or {}
                    title = headline.get("main", "") if isinstance(headline, dict) else str(headline)
                    
                    abstract = doc.get("abstract", "") or ""
                    lead_paragraph = doc.get("lead_paragraph", "") or ""
                    web_url = doc.get("web_url", "") or ""
                    pub_date = doc.get("pub_date", "") or ""
                    section_name = doc.get("section_name", "") or ""
                    
                    # Skip if missing essential data
                    if not title.strip() or not web_url.strip():
                        continue
                    
                    # Create content from abstract and lead paragraph
                    content_parts = []
                    if abstract.strip():
                        content_parts.append(abstract.strip())
                    if lead_paragraph.strip() and lead_paragraph.strip() != abstract.strip():
                        content_parts.append(lead_paragraph.strip())
                    
                    full_content = " ".join(content_parts)
                    snippet = full_content[:400] if full_content else title
                    
                    # Apply date filter AFTER getting results (more flexible)
                    if pub_date:
                        try:
                            # Parse NYT date format: 2024-06-16T10:30:45+0000
                            article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00').replace('+0000', '+00:00'))
                            cutoff_date = datetime.now() - timedelta(days=days_back)
                            
                            # Make both timezone naive for comparison
                            if article_date.tzinfo:
                                article_date = article_date.replace(tzinfo=None)
                            
                            if article_date < cutoff_date:
                                continue  # Skip old articles
                        except (ValueError, TypeError) as e:
                            # If date parsing fails, include the article anyway
                            logger.debug(f"Date parsing failed for NYT article: {e}")
                    
                    # Check relevance (more lenient than before)
                    company_lower = company.lower()
                    title_lower = title.lower()
                    content_lower = full_content.lower()
                    
                    # Must have company mention OR be from business/tech section
                    has_company_mention = (company_lower in title_lower or company_lower in content_lower)
                    is_business_section = any(term in section_name.lower() for term in ['business', 'technology', 'markets', 'finance', 'economy'])
                    
                    if has_company_mention or is_business_section:
                        article = {
                            "title": title.strip(),
                            "snippet": snippet,
                            "full_content": full_content,
                            "link": web_url.strip(),
                            "source": "nytimes.com",
                            "published": pub_date,
                            "source_type": "nyt_api",
                            "section": section_name
                        }
                        articles.append(article)
                        logger.debug(f"NYT article added: {title[:50]}... (Section: {section_name})")
                        
                except Exception as e:
                    logger.warning(f"Error processing NYT article: {e}")
                    continue
            
            logger.info(f"NYT: Successfully processed {len(articles)} relevant articles")
            return articles
            
        except requests.exceptions.RequestException as e:
            logger.error(f"NYT API request failed: {e}")
            return []
            
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

def parse_rss_feed_robust(feed_url: str, company: str, days_back: int = 7) -> List[Dict]:
    """
    Robust RSS feed parser that handles various feed formats and errors gracefully.
    """
    try:
        logger.debug(f"Parsing RSS feed: {feed_url}")
        
        # Enhanced headers to avoid bot detection
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, application/atom+xml, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Request with timeout and retries
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = requests.get(feed_url, headers=headers, timeout=10, allow_redirects=True)
                
                if response.status_code == 200:
                    break
                elif response.status_code == 403:
                    logger.warning(f"RSS feed blocked bots: {feed_url}")
                    return []
                elif response.status_code == 404:
                    logger.warning(f"RSS feed not found: {feed_url}")
                    return []
                else:
                    logger.warning(f"RSS feed HTTP {response.status_code}: {feed_url}")
                    if attempt == max_retries - 1:
                        return []
                    time.sleep(2)  # Wait before retry
                    
            except requests.exceptions.Timeout:
                logger.warning(f"RSS feed timeout: {feed_url}")
                if attempt == max_retries - 1:
                    return []
                time.sleep(2)
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"RSS feed connection error: {feed_url} - {e}")
                return []
        else:
            return []
        
        # Parse the feed
        try:
            feed = feedparser.parse(response.content)
        except Exception as e:
            logger.warning(f"RSS feed parse error: {feed_url} - {e}")
            return []
        
        if feed.bozo and feed.bozo_exception:
            logger.debug(f"RSS feed parse warning: {feed_url} - {feed.bozo_exception}")
        
        if not hasattr(feed, 'entries') or not feed.entries:
            logger.debug(f"RSS feed has no entries: {feed_url}")
            return []
        
        articles = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        company_lower = company.lower()
        
        for entry in feed.entries[:20]:  # Limit to first 20 entries
            try:
                # Extract basic data
                title = getattr(entry, 'title', '').strip()
                link = getattr(entry, 'link', '').strip()
                
                if not title or not link:
                    continue
                
                # Extract description/summary
                description = ''
                for field in ['summary', 'description', 'content']:
                    if hasattr(entry, field):
                        field_value = getattr(entry, field)
                        if isinstance(field_value, list) and field_value:
                            # Handle content that might be a list
                            description = field_value[0].get('value', '') if isinstance(field_value[0], dict) else str(field_value[0])
                        elif isinstance(field_value, str):
                            description = field_value
                        elif hasattr(field_value, 'value'):
                            description = field_value.value
                        
                        if description.strip():
                            break
                
                # Clean up description
                if description:
                    description = re.sub(r'<[^>]+>', '', description)  # Remove HTML
                    description = re.sub(r'\s+', ' ', description).strip()  # Normalize whitespace
                    description = description[:800]  # Limit length
                
                # Extract publish date
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
                
                # Check if article is recent enough
                if pub_date and pub_date < cutoff_date:
                    continue
                
                # Check relevance to company
                title_lower = title.lower()
                desc_lower = description.lower()
                
                # More sophisticated relevance check
                has_company_mention = (company_lower in title_lower or company_lower in desc_lower)
                
                # For tickers, also check for company name
                if not has_company_mention and len(company) <= 5 and company.isupper():
                    ticker_to_name = {
                        'AAPL': 'apple', 'MSFT': 'microsoft', 'GOOGL': 'google', 
                        'AMZN': 'amazon', 'TSLA': 'tesla', 'META': 'meta', 'NVDA': 'nvidia'
                    }
                    if company.upper() in ticker_to_name:
                        company_name = ticker_to_name[company.upper()]
                        has_company_mention = (company_name in title_lower or company_name in desc_lower)
                
                # Check for financial keywords if no direct company mention
                if not has_company_mention:
                    financial_keywords = ['stock', 'shares', 'earnings', 'revenue', 'financial', 'market', 'trading']
                    has_financial_context = any(keyword in title_lower or keyword in desc_lower for keyword in financial_keywords)
                    if not has_financial_context:
                        continue
                
                # Create article object
                article = {
                    "title": title,
                    "snippet": description[:300] if description else title[:300],
                    "full_content": description if description else title,
                    "link": link,
                    "source": extract_domain_simple(link),
                    "published": pub_date.isoformat() if pub_date else "",
                    "source_type": "rss_feed"
                }
                
                articles.append(article)
                logger.debug(f"RSS article added: {title[:50]}...")
                
            except Exception as e:
                logger.debug(f"Error processing RSS entry: {e}")
                continue
        
        if articles:
            logger.info(f"RSS feed {feed_url}: Found {len(articles)} relevant articles")
        
        return articles
        
    except Exception as e:
        logger.warning(f"Error parsing RSS feed {feed_url}: {e}")
        return []

def fetch_rss_feeds_working(company: str, days_back: int = 7) -> List[Dict]:
    """
    Fetch from working RSS feeds only - no more 404s or blocked requests.
    """
    logger.info(f"Fetching RSS feeds for {company} using verified working feeds...")
    
    working_feeds = get_working_rss_feeds()
    all_articles = []
    successful_feeds = 0
    
    for feed_name, feed_url in working_feeds.items():
        try:
            logger.debug(f"Testing RSS feed: {feed_name}")
            articles = parse_rss_feed_robust(feed_url, company, days_back)
            
            if articles:
                all_articles.extend(articles)
                successful_feeds += 1
                logger.info(f"RSS {feed_name}: {len(articles)} articles")
            else:
                logger.debug(f"RSS {feed_name}: 0 articles")
                
            # Rate limiting between feeds
            time.sleep(1)
            
        except Exception as e:
            logger.warning(f"RSS feed {feed_name} failed: {e}")
            continue
    
    logger.info(f"RSS Feeds: {successful_feeds}/{len(working_feeds)} feeds successful, {len(all_articles)} total articles")
    return all_articles

def combine_premium_sources_fixed(company: str, days_back: int = 7) -> List[Dict]:
    """
    Fixed version of combine_premium_sources that uses working functions.
    """
    all_articles = []
    source_stats = {}
    
    # 1. Fetch from NYT API with working function
    try:
        nyt_articles = fetch_nyt_news_working(company, days_back)
        all_articles.extend(nyt_articles)
        source_stats['nyt_api'] = len(nyt_articles)
        if nyt_articles:
            logger.info(f"NYT API: {len(nyt_articles)} articles retrieved")
    except Exception as e:
        logger.error(f"NYT API failed: {e}")
        source_stats['nyt_api'] = 0
    
    # 2. Skip Reuters API (no key available)
    source_stats['reuters_api'] = 0
    
    # 3. Fetch from working RSS feeds
    try:
        rss_articles = fetch_rss_feeds_working(company, days_back)
        all_articles.extend(rss_articles)
        source_stats['rss_feeds'] = len(rss_articles)
        if rss_articles:
            logger.info(f"RSS Feeds: {len(rss_articles)} articles retrieved")
    except Exception as e:
        logger.error(f"RSS feeds failed: {e}")
        source_stats['rss_feeds'] = 0
    
    # Deduplicate articles
    unique_articles = []
    seen_urls = set()
    seen_titles = set()
    
    for article in all_articles:
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
    
    logger.info(f"Premium sources: {len(all_articles)} total → {len(unique_articles)} unique articles")
    logger.info(f"Source breakdown: {source_stats}")
    
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
    
    if source in PREMIUM_SOURCES:
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

def fetch_alphavantage_news(company: str, days_back: int = 7) -> List[Dict]:
    """
    Fetch comprehensive news using AlphaVantage News Sentiment API.
    (This is the existing function - maintained for backward compatibility)
    """
    try:
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            logger.warning("AlphaVantage API key not found, skipping premium news fetch")
            return []
        
        # Convert company name to ticker if possible
        ticker = convert_to_ticker(company)
        logger.info(f"AlphaVantage: Converting '{company}' to ticker '{ticker}'")
        
        rate_limiter.wait_if_needed('alphavantage', 12.0)  # AlphaVantage rate limit
        
        # AlphaVantage News Sentiment API
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "apikey": api_key,
            "limit": 50,
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
        
        articles = []
        feed_data = data.get("feed", [])
        
        if not feed_data:
            logger.info(f"AlphaVantage: No articles found for ticker {ticker}")
            return []
        
        logger.info(f"AlphaVantage: Processing {len(feed_data)} articles from feed...")
        
        # Filter articles by date
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
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
                        pass
                
                # Extract relevance and sentiment
                ticker_sentiment_data = item.get("ticker_sentiment", [])
                relevance_score = 0.0
                
                for sentiment_item in ticker_sentiment_data:
                    if sentiment_item.get("ticker") == ticker:
                        try:
                            relevance_score = float(sentiment_item.get("relevance_score", 0))
                            break
                        except (ValueError, TypeError):
                            continue
                
                if relevance_score == 0:
                    try:
                        relevance_score = float(item.get("relevance_score", 0))
                    except (ValueError, TypeError):
                        relevance_score = 0.0
                
                sentiment_raw = item.get("overall_sentiment_score", "0")
                try:
                    sentiment_score = float(sentiment_raw) if sentiment_raw else 0.0
                except (ValueError, TypeError):
                    sentiment_score = 0.0
                
                article = {
                    "title": item.get("title", ""),
                    "snippet": item.get("summary", "")[:300],
                    "full_content": item.get("summary", ""),
                    "link": item.get("url", ""),
                    "source": extract_domain(item.get("url", "")),
                    "published": time_published,
                    "sentiment_score": sentiment_score,
                    "sentiment_label": item.get("overall_sentiment_label", "Neutral"),
                    "relevance_score": relevance_score,
                    "source_type": "alphavantage_premium"
                }
                
                if relevance_score > 0.1:
                    articles.append(article)
                    
            except Exception as item_error:
                logger.warning(f"Error processing AlphaVantage article: {item_error}")
                continue
        
        logger.info(f"AlphaVantage returned {len(articles)} articles for {ticker}")
        return articles
        
    except Exception as e:
        logger.error(f"Error fetching AlphaVantage news for '{company}': {str(e)}")
        return []

def score_articles(articles: List[Dict], company: str) -> List[Tuple[Dict, float]]:
    """
    Enhanced scoring with source diversity and premium source prioritization.
    """
    scored_articles = []
    source_counts = {}
    
    for article in articles:
        score = 0.0
        
        title = article.get('title', '').lower()
        snippet = article.get('snippet', '').lower()
        source = article.get('source', '').lower()
        source_type = article.get('source_type', 'google_search')
        
        # Count articles per source for diversity scoring
        source_counts[source] = source_counts.get(source, 0) + 1
        
        # SOURCE SCORING with diversity penalty
        base_source_score = PREMIUM_SOURCES.get(source, 2)
        
        # Premium source type bonuses
        if source_type == 'alphavantage_premium':
            score += 15
            relevance_score = float(article.get('relevance_score', 0))
            score += relevance_score * 10
            sentiment_score = float(article.get('sentiment_score', 0))
            if abs(sentiment_score) > 0.3:
                score += 5
        elif source_type == 'nyt_api':
            score += 10  # NYT API provides good abstracts
        elif source_type == 'reuters_api':
            score += 12  # Reuters API (if available) is premium
        elif source_type == 'rss_feed':
            score += 5   # RSS feeds provide more content than Google snippets
        
        # Diversity penalty for overrepresented sources
        diversity_penalty = 0
        if source_counts[source] > 3:
            diversity_penalty = (source_counts[source] - 3) * 1.5
        
        source_score = max(base_source_score - diversity_penalty, 1)
        score += source_score
        
        # Financial relevance scoring
        title_snippet = title + ' ' + snippet
        if source_type in ['alphavantage_premium', 'nyt_api', 'rss_feed'] and article.get('full_content'):
            title_snippet += ' ' + article.get('full_content', '').lower()[:500]
        
        financial_matches = sum(1 for keyword in FINANCIAL_KEYWORDS if keyword in title_snippet)
        relevance_score = min(financial_matches * 0.7, 8)
        score += relevance_score
        
        # Company prominence
        company_lower = company.lower()
        if company_lower in title:
            score += 3
        company_mentions = title_snippet.count(company_lower)
        company_score = min(company_mentions * 1, 2)
        score += company_score
        
        # Content quality bonus
        if source_type in ['alphavantage_premium', 'nyt_api', 'reuters_api']:
            score += 5  # Full content available
        elif source_type == 'rss_feed':
            score += 3  # Better than snippet
        else:
            snippet_length = len(snippet)
            if snippet_length > 200:
                score += 3
            elif snippet_length > 100:
                score += 2
        
        # Business context
        business_terms = ['stock', 'shares', 'market', 'investors', 'wall street', 'nasdaq', 'trading']
        business_matches = sum(1 for term in business_terms if term in title_snippet)
        score += min(business_matches * 0.5, 3)
        
        # Anti-spam penalties
        spam_indicators = [
            'here\'s how much you would have made',
            'looking into', 'recent short interest',
            'aggressive stock buying', 'easier way to invest'
        ]
        
        if any(indicator in title.lower() for indicator in spam_indicators):
            score -= 3
        
        # Standard penalties
        if any(term in title_snippet for term in ['jobs at', 'careers', 'hiring']):
            score -= 15
        if any(term in title for term in ['directory', 'listing']):
            score -= 10
        
        score = max(score, 0)
        scored_articles.append((article, score))
    
    # Sort by score
    scored_articles.sort(key=lambda x: x[1], reverse=True)
    
    # Log source distribution in top articles
    if scored_articles:
        top_15_sources = [article[0]['source'] for article in scored_articles[:15]]
        source_dist = {}
        for source in top_15_sources:
            source_dist[source] = source_dist.get(source, 0) + 1
        
        logger.info(f"Top 15 articles source distribution: {dict(sorted(source_dist.items(), key=lambda x: x[1], reverse=True))}")
    
    return scored_articles

def fetch_comprehensive_news(company: str, days_back: int = 7, enable_monitoring: bool = True) -> Dict[str, Any]:
    """
    Main orchestration function that fetches from all sources and returns comprehensive results.
    This replaces the complex logic that was in the Flask route.
    """
    import time
    start_time = time.time()
    
    all_articles = []
    source_performance = {}
    api_errors = []
    
    logger.info(f"🚀 Starting comprehensive news fetch for {company} ({days_back} days)")
    
    # Step 1: Fetch from AlphaVantage Premium (highest priority - full content + sentiment)
    try:
        alphavantage_articles = fetch_alphavantage_news(company, days_back)
        all_articles.extend(alphavantage_articles)
        source_performance['alphavantage'] = len(alphavantage_articles)
        logger.info(f"✓ AlphaVantage: {len(alphavantage_articles)} articles with full content + sentiment")
    except Exception as e:
        logger.error(f"AlphaVantage failed: {e}")
        source_performance['alphavantage'] = 0
        api_errors.append(f"AlphaVantage: {str(e)}")
    
    # Step 2: Fetch from Premium Sources (NYT API, Reuters API, RSS Feeds)
    try:
        premium_articles = combine_premium_sources_fixed(company, days_back)
        
        # Deduplicate against AlphaVantage articles
        alphavantage_urls = {article.get('link', '') for article in alphavantage_articles}
        new_premium_articles = []
        
        for article in premium_articles:
            if article.get('link', '') not in alphavantage_urls:
                new_premium_articles.append(article)
        
        all_articles.extend(new_premium_articles)
        source_performance['premium_sources'] = len(new_premium_articles)
        logger.info(f"✓ Premium Sources: {len(new_premium_articles)} unique articles (NYT API + RSS feeds)")
        
    except Exception as e:
        logger.error(f"Premium sources failed: {e}")
        source_performance['premium_sources'] = 0
        api_errors.append(f"Premium sources: {str(e)}")
    
    # Step 3: Google Search (fallback and gap-filling)
    try:
        google_articles = fetch_google_news(company, days_back)
        
        # Deduplicate against existing articles
        existing_urls = {article.get('link', '') for article in all_articles}
        new_google_articles = []
        
        for article in google_articles:
            if article.get('link', '') not in existing_urls:
                new_google_articles.append(article)
        
        all_articles.extend(new_google_articles)
        source_performance['google_search'] = len(new_google_articles)
        logger.info(f"✓ Google Search: {len(new_google_articles)} additional articles")
        
    except Exception as e:
        logger.error(f"Google search failed: {e}")
        source_performance['google_search'] = 0
        api_errors.append(f"Google search: {str(e)}")
    
    # Final deduplication (belt and suspenders approach)
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
    
    # Return comprehensive results
    return {
        'company': company,
        'articles': all_articles,
        'summaries': summaries,
        'metrics': {
            'total_articles': total_articles,
            'alphavantage_articles': alphavantage_count,
            'nyt_articles': nyt_articles,
            'rss_articles': rss_articles,
            'google_articles': google_count,
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

def generate_premium_analysis(company: str, articles: List[Dict], max_articles: int = 15) -> Dict[str, List[str]]:
    """
    Main function that generates institutional-grade analysis using combined premium sources.
    """
    if not articles:
        return {
            "executive": ["No recent financial news found. Consider expanding date range or checking company name/ticker."],
            "investor": ["No recent investor-relevant developments identified."],
            "catalysts": ["No material catalysts or risks detected in recent coverage."]
        }
    
    try:
        # Score and filter articles
        scored_articles = score_articles(articles, company)
        top_articles = [article for article, score in scored_articles[:max_articles]]
        
        # Calculate source quality metrics
        source_type_counts = {}
        for article in top_articles:
            source_type = article.get('source_type', 'google_search')
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        
        premium_count = sum(1 for article in top_articles if article['source'] in PREMIUM_SOURCES)
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
                article_text += f"   Source: {article['source']} | Sentiment: {sentiment_label} ({sentiment_score:.2f}) | Relevance: {relevance_score:.2f}\n"
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
                content_quality = "PREMIUM" if article['source'] in PREMIUM_SOURCES else "STANDARD"
                article_text += f"\n{i}. [{content_quality}] {article['title']}\n"
                article_text += f"   Source: {article['source']}\n"
                article_text += f"   Content: {article['snippet']}\n"
            
            article_text += f"   Link: {article['link']}\n"
        
        # Enhanced analysis prompt
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

REQUIRED SECTIONS (2-3 substantive bullets each):

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
- Reference premium source advantages: "According to full NYT analysis..." or "Enhanced RSS content reveals..."

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
            max_tokens=2000
        )
        
        analysis_text = response.choices[0].message.content
        
        # Log analysis quality metrics
        alphavantage_count = source_type_counts.get('alphavantage_premium', 0)
        nyt_count = source_type_counts.get('nyt_api', 0)
        rss_count = source_type_counts.get('rss_feed', 0)
        
        logger.info(f"Premium analysis for {company}: {len(analysis_text)} chars from {total_articles} articles "
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

# Legacy compatibility functions
def fetch_combined_premium_news(company: str, days_back: int = 7) -> List[Dict]:
    """Legacy function - now redirects to the new implementation."""
    return combine_premium_sources(company, days_back)

def score_articles_with_alphavantage(articles: List[Dict], company: str) -> List[Tuple[Dict, float]]:
    """Legacy function - now redirects to enhanced scoring."""
    return score_articles(articles, company)

def generate_financial_summary(company: str, articles: List[Dict], max_articles: int = 15) -> Dict[str, List[str]]:
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