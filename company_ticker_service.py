import requests
import logging
import time
from typing import Dict, Optional, Tuple
import os

logger = logging.getLogger(__name__)

class FastCompanyTickerService:
    """
    Fast company/ticker conversion service with comprehensive logging and timeouts.
    """
    
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = 3600  # 1 hour cache
        
        # Basic fallback mappings for speed
        self.common_mappings = {
            'apple': ('AAPL', 'Apple Inc'),
            'microsoft': ('MSFT', 'Microsoft Corporation'),
            'google': ('GOOGL', 'Alphabet Inc'),
            'alphabet': ('GOOGL', 'Alphabet Inc'),
            'amazon': ('AMZN', 'Amazon.com Inc'),
            'tesla': ('TSLA', 'Tesla Inc'),
            'meta': ('META', 'Meta Platforms Inc'),
            'facebook': ('META', 'Meta Platforms Inc'),
            'nvidia': ('NVDA', 'NVIDIA Corporation'),
            'netflix': ('NFLX', 'Netflix Inc'),
            'adobe': ('ADBE', 'Adobe Inc'),
            'salesforce': ('CRM', 'Salesforce Inc'),
            'oracle': ('ORCL', 'Oracle Corporation'),
            'intel': ('INTC', 'Intel Corporation'),
            'amd': ('AMD', 'Advanced Micro Devices'),
            'cisco': ('CSCO', 'Cisco Systems'),
            'jpmorgan': ('JPM', 'JPMorgan Chase & Co'),
            'jp morgan': ('JPM', 'JPMorgan Chase & Co'),
            'bank of america': ('BAC', 'Bank of America Corp'),
            'wells fargo': ('WFC', 'Wells Fargo & Company'),
            'goldman sachs': ('GS', 'Goldman Sachs Group'),
            'morgan stanley': ('MS', 'Morgan Stanley'),
            'visa': ('V', 'Visa Inc'),
            'mastercard': ('MA', 'Mastercard Inc'),
            'johnson & johnson': ('JNJ', 'Johnson & Johnson'),
            'pfizer': ('PFE', 'Pfizer Inc'),
            'walmart': ('WMT', 'Walmart Inc'),
            'coca cola': ('KO', 'Coca-Cola Company'),
            'pepsi': ('PEP', 'PepsiCo Inc'),
            'nike': ('NKE', 'Nike Inc'),
            'boeing': ('BA', 'Boeing Company'),
            'general electric': ('GE', 'General Electric'),
            'exxon': ('XOM', 'Exxon Mobil Corporation'),
            'chevron': ('CVX', 'Chevron Corporation')
        }
    
    def get_both_ticker_and_company(self, input_text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        FAST conversion with comprehensive logging.
        Returns (ticker, company_name) tuple.
        """
        start_time = time.time()
        input_clean = input_text.strip().lower()
        
        logger.info(f"🔍 TICKER SERVICE: Starting conversion for '{input_text}'")
        
        # Step 1: Check cache first (fastest)
        cache_key = f"conversion_{input_clean}"
        if self._is_cached_valid(cache_key):
            cached_result = self.cache[cache_key]
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"✅ TICKER SERVICE: Cache hit for '{input_text}' → {cached_result} ({elapsed:.0f}ms)")
            return cached_result['ticker'], cached_result['company']
        
        # Step 2: Check common mappings (very fast)
        if input_clean in self.common_mappings:
            ticker, company = self.common_mappings[input_clean]
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"✅ TICKER SERVICE: Common mapping for '{input_text}' → ticker: '{ticker}', company: '{company}' ({elapsed:.0f}ms)")
            self._cache_result(cache_key, ticker, company)
            return ticker, company
        
        # Step 3: Check if input is already a valid ticker
        if self._looks_like_ticker(input_text):
            ticker = input_text.upper()
            logger.info(f"🎯 TICKER SERVICE: Input '{input_text}' looks like ticker, using '{ticker}'")
            
            # Try to get company name with fast timeout
            company_name = self._fast_ticker_to_company(ticker)
            elapsed = (time.time() - start_time) * 1000
            
            if company_name:
                logger.info(f"✅ TICKER SERVICE: Ticker resolved '{ticker}' → company: '{company_name}' ({elapsed:.0f}ms)")
                self._cache_result(cache_key, ticker, company_name)
                return ticker, company_name
            else:
                logger.info(f"✅ TICKER SERVICE: Using ticker '{ticker}' without company name ({elapsed:.0f}ms)")
                self._cache_result(cache_key, ticker, None)
                return ticker, None
        
        # Step 4: Try API conversion (with fast timeout)
        logger.info(f"🌐 TICKER SERVICE: Trying API conversion for company '{input_text}'")
        ticker = self._fast_company_to_ticker(input_text)
        
        elapsed = (time.time() - start_time) * 1000
        
        if ticker:
            logger.info(f"✅ TICKER SERVICE: API conversion '{input_text}' → ticker: '{ticker}' ({elapsed:.0f}ms)")
            self._cache_result(cache_key, ticker, input_text)
            return ticker, input_text
        else:
            logger.warning(f"❌ TICKER SERVICE: No conversion found for '{input_text}' ({elapsed:.0f}ms)")
            self._cache_result(cache_key, None, input_text)
            return None, input_text
    
    def _fast_company_to_ticker(self, company_name: str) -> Optional[str]:
        """Fast company to ticker conversion with 3-second timeout."""
        # Try AlphaVantage first (most reliable)
        ticker = self._try_alphavantage_fast(company_name)
        if ticker:
            return ticker
        
        # Try Yahoo Finance as backup
        ticker = self._try_yahoo_fast(company_name)
        if ticker:
            return ticker
        
        return None
    
    def _fast_ticker_to_company(self, ticker: str) -> Optional[str]:
        """Fast ticker to company conversion with 3-second timeout."""
        # Try AlphaVantage first
        company = self._try_alphavantage_overview(ticker)
        if company:
            return company
        
        # Try Yahoo Finance as backup
        company = self._try_yahoo_ticker_lookup(ticker)
        if company:
            return company
        
        return None
    
    def _try_alphavantage_fast(self, company_name: str) -> Optional[str]:
        """Try AlphaVantage with 3-second timeout and comprehensive logging."""
        try:
            api_key = os.getenv("ALPHAVANTAGE_API_KEY")
            if not api_key:
                logger.debug("TICKER SERVICE: No AlphaVantage API key, skipping")
                return None
            
            logger.debug(f"TICKER SERVICE: Trying AlphaVantage for '{company_name}'")
            
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "SYMBOL_SEARCH",
                "keywords": company_name,
                "apikey": api_key
            }
            
            start_time = time.time()
            response = requests.get(url, params=params, timeout=3)  # 3-second timeout
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                matches = data.get("bestMatches", [])
                
                if matches:
                    # Look for US market matches first
                    for match in matches:
                        symbol = match.get("1. symbol", "")
                        name = match.get("2. name", "")
                        region = match.get("4. region", "")
                        
                        if "United States" in region and symbol:
                            logger.info(f"✅ TICKER SERVICE: AlphaVantage found '{company_name}' → '{symbol}' ({name}) ({elapsed:.0f}ms)")
                            return symbol
                    
                    # If no US match, take first match
                    first_match = matches[0]
                    symbol = first_match.get("1. symbol", "")
                    if symbol:
                        name = first_match.get("2. name", "")
                        logger.info(f"✅ TICKER SERVICE: AlphaVantage fallback '{company_name}' → '{symbol}' ({name}) ({elapsed:.0f}ms)")
                        return symbol
                
                logger.debug(f"TICKER SERVICE: AlphaVantage no matches for '{company_name}' ({elapsed:.0f}ms)")
            else:
                logger.warning(f"TICKER SERVICE: AlphaVantage HTTP {response.status_code} for '{company_name}' ({elapsed:.0f}ms)")
                
        except requests.exceptions.Timeout:
            logger.warning(f"TICKER SERVICE: AlphaVantage timeout (>3s) for '{company_name}'")
        except Exception as e:
            logger.debug(f"TICKER SERVICE: AlphaVantage error for '{company_name}': {e}")
        
        return None
    
    def _try_yahoo_fast(self, company_name: str) -> Optional[str]:
        """Try Yahoo Finance with 2-second timeout."""
        try:
            logger.debug(f"TICKER SERVICE: Trying Yahoo Finance for '{company_name}'")
            
            url = "https://query1.finance.yahoo.com/v1/finance/search"
            params = {"q": company_name, "quotesCount": 5}
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            start_time = time.time()
            response = requests.get(url, params=params, headers=headers, timeout=2)
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                quotes = data.get("quotes", [])
                
                for quote in quotes:
                    symbol = quote.get("symbol", "")
                    long_name = quote.get("longname", "")
                    quote_type = quote.get("quoteType", "")
                    
                    # Only consider US equities
                    if quote_type == "EQUITY" and symbol and not '.' in symbol:
                        if long_name and any(word in long_name.lower() for word in company_name.lower().split()):
                            logger.info(f"✅ TICKER SERVICE: Yahoo Finance found '{company_name}' → '{symbol}' ({long_name}) ({elapsed:.0f}ms)")
                            return symbol
                
                logger.debug(f"TICKER SERVICE: Yahoo Finance no matches for '{company_name}' ({elapsed:.0f}ms)")
            else:
                logger.warning(f"TICKER SERVICE: Yahoo Finance HTTP {response.status_code} for '{company_name}' ({elapsed:.0f}ms)")
                
        except requests.exceptions.Timeout:
            logger.warning(f"TICKER SERVICE: Yahoo Finance timeout (>2s) for '{company_name}'")
        except Exception as e:
            logger.debug(f"TICKER SERVICE: Yahoo Finance error for '{company_name}': {e}")
        
        return None
    
    def _try_alphavantage_overview(self, ticker: str) -> Optional[str]:
        """Try AlphaVantage Overview with timeout."""
        try:
            api_key = os.getenv("ALPHAVANTAGE_API_KEY")
            if not api_key:
                return None
            
            logger.debug(f"TICKER SERVICE: Trying AlphaVantage Overview for '{ticker}'")
            
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "OVERVIEW",
                "symbol": ticker,
                "apikey": api_key
            }
            
            start_time = time.time()
            response = requests.get(url, params=params, timeout=3)
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                company_name = data.get("Name")
                
                if company_name and company_name != "None":
                    # Clean up company name
                    company_name = company_name.replace(" Inc.", "").replace(" Corp.", "").replace(" Ltd.", "")
                    logger.info(f"✅ TICKER SERVICE: AlphaVantage Overview '{ticker}' → '{company_name}' ({elapsed:.0f}ms)")
                    return company_name
                
                logger.debug(f"TICKER SERVICE: AlphaVantage Overview no name for '{ticker}' ({elapsed:.0f}ms)")
            else:
                logger.warning(f"TICKER SERVICE: AlphaVantage Overview HTTP {response.status_code} for '{ticker}' ({elapsed:.0f}ms)")
                
        except requests.exceptions.Timeout:
            logger.warning(f"TICKER SERVICE: AlphaVantage Overview timeout (>3s) for '{ticker}'")
        except Exception as e:
            logger.debug(f"TICKER SERVICE: AlphaVantage Overview error for '{ticker}': {e}")
        
        return None
    
    def _try_yahoo_ticker_lookup(self, ticker: str) -> Optional[str]:
        """Try Yahoo Finance ticker lookup."""
        try:
            logger.debug(f"TICKER SERVICE: Trying Yahoo ticker lookup for '{ticker}'")
            
            url = f"https://query1.finance.yahoo.com/v1/finance/search"
            params = {"q": ticker}
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            start_time = time.time()
            response = requests.get(url, params=params, headers=headers, timeout=2)
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                quotes = data.get("quotes", [])
                
                for quote in quotes:
                    if quote.get("symbol", "").upper() == ticker.upper():
                        long_name = quote.get("longname") or quote.get("shortname")
                        if long_name:
                            company_name = long_name.replace(" Inc.", "").replace(" Corp.", "").replace(" Ltd.", "")
                            logger.info(f"✅ TICKER SERVICE: Yahoo ticker lookup '{ticker}' → '{company_name}' ({elapsed:.0f}ms)")
                            return company_name
                
                logger.debug(f"TICKER SERVICE: Yahoo ticker lookup no match for '{ticker}' ({elapsed:.0f}ms)")
            else:
                logger.warning(f"TICKER SERVICE: Yahoo ticker lookup HTTP {response.status_code} for '{ticker}' ({elapsed:.0f}ms)")
                
        except requests.exceptions.Timeout:
            logger.warning(f"TICKER SERVICE: Yahoo ticker lookup timeout (>2s) for '{ticker}'")
        except Exception as e:
            logger.debug(f"TICKER SERVICE: Yahoo ticker lookup error for '{ticker}': {e}")
        
        return None
    
    def _looks_like_ticker(self, text: str) -> bool:
        """Enhanced ticker detection."""
        if not text:
            return False
        
        text_clean = text.strip().upper()
        
        # Length check (most tickers are 1-5 characters)
        if len(text_clean) > 5:
            return False
        
        # Should be mostly alphabetic (allow . and -)
        if not text_clean.replace('.', '').replace('-', '').isalpha():
            return False
        
        # All caps or could be all caps
        return True
    
    def _is_cached_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid."""
        if cache_key not in self.cache:
            return False
        
        cached_time = self.cache[cache_key]['timestamp']
        return (time.time() - cached_time) < self.cache_duration
    
    def _cache_result(self, cache_key: str, ticker: Optional[str], company: Optional[str]):
        """Cache the lookup result."""
        self.cache[cache_key] = {
            'ticker': ticker,
            'company': company,
            'timestamp': time.time()
        }

# Global instance
fast_company_ticker_service = FastCompanyTickerService()

def get_enhanced_search_terms(company: str) -> list:
    """
    Get comprehensive search terms using the fast ticker service.
    """
    ticker, company_name = fast_company_ticker_service.get_both_ticker_and_company(company)
    
    search_terms = []
    
    # Add the original input
    search_terms.append(company.strip())
    
    # Add ticker if we found one
    if ticker and ticker not in search_terms:
        search_terms.append(ticker)
    
    # Add company name if we found one
    if company_name and company_name not in search_terms:
        search_terms.append(company_name)
    
    # Add common variations
    if company_name:
        # Remove common corporate suffixes for search
        clean_name = company_name
        for suffix in [" Inc", " Corp", " Corporation", " Company", " Ltd", " Limited"]:
            clean_name = clean_name.replace(suffix, "")
        if clean_name != company_name and clean_name not in search_terms:
            search_terms.append(clean_name)
    
    # Limit to 3 search terms for API efficiency
    return search_terms[:3]