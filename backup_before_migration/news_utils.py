"""
Financial News Analysis System - Consolidated Version
===================================================

SINGLE FILE containing all functionality:
- Parallel source fetching (AlphaVantage + NYT + RSS + Google)
- Advanced relevance assessment
- Claude Sonnet 4 quality validation with web search
- Company name resolution
- Enhanced article scoring

Replaces: enhanced_news_analysis.py, news_utils_claude_sonnet_4.py, quality_validation.py
"""

import os
import re
import json
import time
import logging
import asyncio
import aiohttp
import feedparser
import concurrent.futures
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

# External imports
import requests
from openai import OpenAI

# Optional imports
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class NewsAnalysisConfig:
    """Centralized configuration for the news analysis system."""
    
    # Source weights for scoring
    ALPHAVANTAGE_WEIGHT: float = 2.0
    NYT_WEIGHT: float = 1.8
    RSS_WEIGHT: float = 1.5
    GOOGLE_WEIGHT: float = 1.0
    
    # Quality thresholds
    MIN_RELEVANCE_SCORE: float = 0.3
    MIN_COMPANY_RELEVANCE: float = 0.6
    MIN_FINANCIAL_CONTEXT: float = 0.3
    TARGET_ARTICLE_COUNT: int = 30
    MIN_RELEVANT_ARTICLES_BEFORE_GOOGLE: int = 8
    MIN_RELEVANCE_PERCENTAGE: float = 0.4
    
    # Quality validation
    QUALITY_VALIDATION_ENABLED: bool = True
    QUALITY_MIN_SCORE: float = 7.0
    QUALITY_TARGET_SCORE: float = 8.0
    QUALITY_MAX_RETRIES: int = 2
    
    # Performance settings
    PARALLEL_TIMEOUT: int = 180
    RSS_TIMEOUT: int = 15
    NYT_TIMEOUT: int = 10
    GOOGLE_TIMEOUT: int = 10

# Backward compatibility aliases
AnalysisConfig = NewsAnalysisConfig  # For existing imports

# Global configuration
config = NewsAnalysisConfig()

# Premium sources
PREMIUM_SOURCES = {
    'bloomberg.com': 18, 'reuters.com': 18, 'wsj.com': 17, 'ft.com': 16,
    'nytimes.com': 20, 'cnbc.com': 12, 'marketwatch.com': 12, 'barrons.com': 14,
    'economist.com': 13, 'fortune.com': 10, 'businessinsider.com': 8
}

# Unwanted sources (heavy penalties)
UNWANTED_SOURCES = {
    'benzinga.com': -5, 'fool.com': -5, 'zacks.com': -5,
    'investorplace.com': -4, 'thestreet.com': -4
}

# Financial keywords for relevance assessment
FINANCIAL_KEYWORDS = {
    'earnings': 1.0, 'revenue': 1.0, 'profit': 0.9, 'eps': 1.0,
    'guidance': 0.9, 'forecast': 0.8, 'outlook': 0.8,
    'analyst': 0.9, 'rating': 0.8, 'target': 0.8, 'upgrade': 0.9, 'downgrade': 0.9,
    'stock': 0.7, 'shares': 0.7, 'price': 0.6, 'market': 0.5,
    'acquisition': 1.0, 'merger': 1.0, 'deal': 0.8, 'investment': 0.8,
    'ceo': 0.8, 'cfo': 0.8, 'management': 0.7, 'board': 0.7,
    'product': 0.6, 'launch': 0.7, 'partnership': 0.7
}

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================================
# RELEVANCE ASSESSMENT
# ============================================================================

class RelevanceAssessor:
    """Advanced relevance assessment for articles."""
    
    def __init__(self):
        self.financial_patterns = [
            r'\$[\d,]+(?:\.\d+)?[kmb]?',  # Dollar amounts
            r'\d+(?:\.\d+)?%',  # Percentages
            r'q[1-4]\s+\d{4}',  # Quarters
            r'fy\s*\d{4}',  # Fiscal years
            r'\d+\.\d+\s*eps',  # EPS mentions
        ]
        
        self.negative_indicators = {
            'job', 'career', 'hiring', 'apply', 'employment', 'work at',
            'directory', 'listing', 'yellow pages', 'contact us'
        }
    
    def assess_article_relevance(self, article: Dict, company: str, 
                               ticker: Optional[str] = None, 
                               company_name: Optional[str] = None) -> Dict[str, float]:
        """Comprehensive relevance assessment for a single article."""
        
        title = article.get('title', '').lower()
        content = article.get('snippet', '') or article.get('full_content', '')
        content = content.lower()
        combined_text = f"{title} {content}"
        
        # Get company identifiers
        identifiers = self._get_company_identifiers(company, ticker, company_name)
        
        # Assess different dimensions
        company_relevance = self._assess_company_mentions(combined_text, identifiers)
        financial_context = self._assess_financial_context(combined_text)
        content_quality = self._assess_content_quality(article)
        source_quality = self._assess_source_quality(article)
        negative_penalty = self._check_negative_indicators(combined_text)
        
        # Calculate overall relevance
        overall_relevance = (
            company_relevance * 0.4 +
            financial_context * 0.3 +
            content_quality * 0.2 +
            source_quality * 0.1
        ) - negative_penalty
        
        overall_relevance = max(0.0, min(1.0, overall_relevance))
        
        # Determine if company-specific
        is_company_specific = (
            company_relevance >= config.MIN_COMPANY_RELEVANCE and
            financial_context >= config.MIN_FINANCIAL_CONTEXT and
            overall_relevance >= 0.5
        )
        
        return {
            'company_relevance': round(company_relevance, 3),
            'financial_context': round(financial_context, 3),
            'content_quality': round(content_quality, 3),
            'source_quality': round(source_quality, 3),
            'overall_relevance': round(overall_relevance, 3),
            'is_company_specific': is_company_specific,
            'negative_penalty': round(negative_penalty, 3)
        }
    
    def _get_company_identifiers(self, company: str, ticker: Optional[str], 
                               company_name: Optional[str]) -> List[str]:
        """Get all possible identifiers for the company."""
        identifiers = [company.lower().strip()]
        
        if ticker:
            identifiers.append(ticker.lower())
        
        if company_name:
            identifiers.append(company_name.lower())
            # Add cleaned version without suffixes
            clean_name = company_name.lower()
            for suffix in [' inc', ' corp', ' corporation', ' company', ' ltd', ' limited']:
                clean_name = clean_name.replace(suffix, '')
            if clean_name not in identifiers:
                identifiers.append(clean_name)
        
        return list(set(identifiers))
    
    def _assess_company_mentions(self, text: str, identifiers: List[str]) -> float:
        """Assess how prominently the company is mentioned."""
        if not text:
            return 0.0
        
        mention_score = 0.0
        total_mentions = 0
        
        for identifier in identifiers:
            if not identifier:
                continue
            
            mentions = text.count(identifier)
            total_mentions += mentions
            
            # Title mentions get extra weight
            title_mentions = text[:100].count(identifier)
            mention_score += title_mentions * 0.3
            
            # Word boundary matches
            word_boundary_pattern = r'\b' + re.escape(identifier) + r'\b'
            word_matches = len(re.findall(word_boundary_pattern, text, re.IGNORECASE))
            mention_score += word_matches * 0.2
        
        # Normalize by text length
        text_words = len(text.split())
        if text_words > 0:
            mention_density = total_mentions / text_words
            mention_score += mention_density * 10
        
        return min(mention_score, 1.0)
    
    def _assess_financial_context(self, text: str) -> float:
        """Assess financial and business context."""
        if not text:
            return 0.0
        
        context_score = 0.0
        
        # Financial keyword scoring
        for keyword, weight in FINANCIAL_KEYWORDS.items():
            if keyword in text:
                context_score += weight * 0.1
        
        # Financial pattern matching
        for pattern in self.financial_patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            context_score += matches * 0.15
        
        # Business context phrases
        business_phrases = [
            'quarterly results', 'annual report', 'sec filing', 'press release',
            'financial results', 'business update', 'market share', 'competitive'
        ]
        
        for phrase in business_phrases:
            if phrase in text:
                context_score += 0.1
        
        return min(context_score, 1.0)
    
    def _assess_content_quality(self, article: Dict) -> float:
        """Assess content quality and depth."""
        quality_score = 0.0
        
        # Length-based quality
        text_length = len(article.get('snippet', '') + article.get('full_content', ''))
        if text_length > 500:
            quality_score += 0.3
        elif text_length > 200:
            quality_score += 0.2
        elif text_length > 100:
            quality_score += 0.1
        
        # Source type bonuses
        source_type = article.get('source_type', '')
        if source_type == 'alphavantage_premium':
            quality_score += 0.4
        elif source_type == 'nyt_api':
            quality_score += 0.3
        elif source_type == 'rss_feed':
            quality_score += 0.2
        
        # Full content availability
        if article.get('full_content') and len(article['full_content']) > 300:
            quality_score += 0.2
        
        # Sentiment data (AlphaVantage)
        if article.get('sentiment_label') and article.get('sentiment_score') is not None:
            quality_score += 0.1
        
        return min(quality_score, 1.0)
    
    def _assess_source_quality(self, article: Dict) -> float:
        """Assess source quality."""
        source = article.get('source', '').lower()
        return PREMIUM_SOURCES.get(source, 0.3) / 20.0  # Normalize to 0-1
    
    def _check_negative_indicators(self, text: str) -> float:
        """Check for negative indicators."""
        penalty = 0.0
        for indicator in self.negative_indicators:
            if indicator in text:
                penalty += 0.1
        return min(penalty, 0.5)

# ============================================================================
# QUALITY VALIDATION
# ============================================================================

class QualityValidationEngine:
    """Claude Sonnet 4 quality validation with web search."""
    
    def __init__(self):
        self.anthropic_client = None
        if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            logger.info("✅ Quality Validation Engine initialized")
        else:
            logger.warning("⚠️ Quality validation disabled - missing Anthropic setup")
    
    async def validate_and_enhance_analysis(self, company: str, analysis: Dict[str, List[str]], 
                                          articles: List[Dict]) -> Dict[str, Any]:
        """Main quality validation pipeline."""
        if not self.anthropic_client:
            return self._create_unvalidated_result(analysis)
        
        try:
            logger.info(f"🔍 Starting quality validation for {company}")
            
            # Create validation prompt
            validation_prompt = self._create_validation_prompt(company, analysis, articles)
            
            # Run Claude validation
            start_time = time.time()
            validation_response = await self._run_claude_validation(validation_prompt)
            validation_time = time.time() - start_time
            
            # Parse response
            validation_result = self._parse_validation_response(validation_response)
            
            # Log metrics
            self._log_quality_metrics(company, validation_result, validation_time)
            
            return self._create_validated_result(validation_result, validation_time)
            
        except Exception as e:
            logger.error(f"❌ Quality validation failed for {company}: {str(e)}")
            return self._create_fallback_result(analysis, str(e))
    
    def _create_validation_prompt(self, company: str, analysis: Dict[str, List[str]], 
                                articles: List[Dict]) -> str:
        """Create validation prompt for Claude."""
        today_str = datetime.now().strftime("%B %d, %Y")
        
        # Format analysis
        formatted_analysis = ""
        section_headers = {
            'executive': '**EXECUTIVE SUMMARY**',
            'investor': '**INVESTOR INSIGHTS**',
            'catalysts': '**CATALYSTS & RISKS**'
        }
        
        for section_key, bullets in analysis.items():
            header = section_headers.get(section_key, f'**{section_key.upper()}**')
            formatted_analysis += f"{header}\n"
            for i, bullet in enumerate(bullets, 1):
                clean_bullet = bullet.replace('<strong>', '').replace('</strong>', '')
                formatted_analysis += f"{i}. {clean_bullet}\n"
            formatted_analysis += "\n"
        
        return f"""You are a Managing Director of Equity Research validating financial analysis for institutional investors.

TODAY'S DATE: {today_str}
COMPANY: {company}
ARTICLES ANALYZED: {len(articles)}

DRAFT ANALYSIS TO REVIEW:
{formatted_analysis}

VALIDATION FRAMEWORK (Score 0-10):
1. FACT VERIFICATION - Verify numerical claims, stock data, financial metrics
2. VALUATION CONTEXT - Ensure current market data, proper risk context
3. INVESTMENT ACTIONABILITY - Specific, actionable insights with clear timelines
4. PROFESSIONAL TONE - Institutional-grade language, analytical objectivity

Return ONLY valid JSON:
{{
  "overall_verdict": "pass" | "needs_revision" | "fail",
  "overall_score": float,
  "gate_scores": {{
    "fact_verification": float,
    "valuation_context": float,
    "investment_actionability": float,
    "professional_tone": float
  }},
  "critical_issues": [
    {{
      "category": "fact_verification|valuation_context|investment_actionability|professional_tone",
      "severity": "high|medium|low",
      "issue": "Description",
      "recommendation": "How to fix"
    }}
  ],
  "revised_analysis": {{
    "executive": ["Enhanced bullet 1", "Enhanced bullet 2", "Enhanced bullet 3"],
    "investor": ["Enhanced insight 1", "Enhanced insight 2", "Enhanced insight 3"],
    "catalysts": ["Enhanced catalyst 1", "Enhanced catalyst 2", "Enhanced catalyst 3"]
  }}
}}"""
    
    async def _run_claude_validation(self, prompt: str) -> str:
        """Execute Claude validation."""
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: self.anthropic_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8000,
                    temperature=0.05,
                    messages=[{"role": "user", "content": prompt}]
                )
            ),
            timeout=180.0
        )
        return response.content[0].text
    
    def _parse_validation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response."""
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            raise ValueError("No JSON found in Claude response")
        
        json_text = response_text[json_start:json_end]
        result = json.loads(json_text)
        
        # Validate required fields
        required_fields = ['overall_verdict', 'overall_score', 'gate_scores', 'revised_analysis']
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")
        
        return result
    
    def _log_quality_metrics(self, company: str, validation_result: Dict, validation_time: float):
        """Log quality metrics."""
        score = validation_result.get('overall_score', 0)
        verdict = validation_result.get('overall_verdict', 'unknown')
        
        logger.info(f"🎯 Quality Validation for {company}:")
        logger.info(f"   • Score: {score:.1f}/10")
        logger.info(f"   • Verdict: {verdict}")
        logger.info(f"   • Time: {validation_time:.2f}s")
    
    def _create_validated_result(self, validation_result: Dict, validation_time: float) -> Dict[str, Any]:
        """Create validated result."""
        return {
            'analysis': validation_result['revised_analysis'],
            'quality_validation': {
                'enabled': True,
                'passed': validation_result['overall_score'] >= config.QUALITY_MIN_SCORE,
                'score': validation_result['overall_score'],
                'verdict': validation_result['overall_verdict'],
                'gate_scores': validation_result['gate_scores'],
                'critical_issues': validation_result.get('critical_issues', []),
                'validation_time': validation_time,
                'quality_grade': self._calculate_quality_grade(validation_result['overall_score'])
            },
            'success': True,
            'enhanced': True
        }
    
    def _create_unvalidated_result(self, analysis: Dict[str, List[str]]) -> Dict[str, Any]:
        """Create unvalidated result."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': False,
                'passed': None,
                'score': None,
                'message': 'Quality validation disabled'
            },
            'success': True,
            'enhanced': False
        }
    
    def _create_fallback_result(self, analysis: Dict[str, List[str]], error: str) -> Dict[str, Any]:
        """Create fallback result."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': True,
                'passed': False,
                'score': None,
                'error': error,
                'message': 'Quality validation failed'
            },
            'success': True,
            'enhanced': False
        }
    
    def _calculate_quality_grade(self, score: float) -> str:
        """Calculate quality grade."""
        if score >= 9.0: return "A+"
        elif score >= 8.5: return "A"
        elif score >= 8.0: return "A-"
        elif score >= 7.5: return "B+"
        elif score >= 7.0: return "B"
        elif score >= 6.0: return "B-"
        else: return "C"

# ============================================================================
# ORCHESTRATOR CLASSES (for backward compatibility)
# ============================================================================

class DynamicSourceOrchestrator:
    """
    Backward compatibility class - functionality moved to main function.
    Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.
    """
    
    def __init__(self, config: NewsAnalysisConfig = None):
        self.config = config or NewsAnalysisConfig()
        logger.warning("DynamicSourceOrchestrator is deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() directly.")
    
    async def fetch_enhanced_news(self, company: str, days_back: int = 7) -> Dict[str, Any]:
        """Deprecated - use main function instead."""
        logger.warning("Use fetch_comprehensive_news_guaranteed_30_enhanced() instead of DynamicSourceOrchestrator")
        return await _run_comprehensive_analysis(company, days_back, True)

class ParallelSourceOrchestrator:
    """
    Backward compatibility class - functionality moved to main function.
    Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.
    """
    
    def __init__(self, config: NewsAnalysisConfig = None):
        self.config = config or NewsAnalysisConfig()
        self.relevance_assessor = RelevanceAssessor()
        logger.warning("ParallelSourceOrchestrator is deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() directly.")
    
    async def fetch_enhanced_news_with_parallel_sources(self, company: str, days_back: int = 7) -> Dict[str, Any]:
        """Deprecated - use main function instead."""
        logger.warning("Use fetch_comprehensive_news_guaranteed_30_enhanced() instead of ParallelSourceOrchestrator")
        return await _run_comprehensive_analysis(company, days_back, False)
    
    async def fetch_enhanced_news_with_quality_validation(self, company: str, days_back: int = 7) -> Dict[str, Any]:
        """Deprecated - use main function instead."""
        logger.warning("Use fetch_comprehensive_news_guaranteed_30_enhanced() instead of ParallelSourceOrchestrator")
        return await _run_comprehensive_analysis(company, days_back, True)

class QualityEnhancedSourceOrchestrator:
    """
    Backward compatibility class - functionality moved to main function.
    Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.
    """
    
    def __init__(self, config: NewsAnalysisConfig = None):
        self.config = config or NewsAnalysisConfig()
        logger.warning("QualityEnhancedSourceOrchestrator is deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() directly.")
    
    async def fetch_enhanced_news_with_optional_quality_validation(self, company: str, days_back: int = 7, 
                                                                  enable_quality_validation: bool = True) -> Dict[str, Any]:
        """Deprecated - use main function instead."""
        logger.warning("Use fetch_comprehensive_news_guaranteed_30_enhanced() instead of QualityEnhancedSourceOrchestrator")
        return await _run_comprehensive_analysis(company, days_back, enable_quality_validation)

# ============================================================================
# COMPANY RESOLUTION
# ============================================================================

def resolve_company_identifiers(company: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve company input to ticker and company name."""
    try:
        from company_ticker_service import fast_company_ticker_service
        return fast_company_ticker_service.get_both_ticker_and_company(company)
    except ImportError:
        logger.warning("Company ticker service not available")
        if len(company) <= 5 and company.isupper():
            return company, None
        else:
            return None, company

# ============================================================================
# SOURCE FETCHING
# ============================================================================

def fetch_alphavantage_news_enhanced(company: str, days_back: int = 7) -> List[Dict]:
    """Fetch from AlphaVantage News Sentiment API."""
    try:
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            logger.warning("AlphaVantage API key not found")
            return []
        
        ticker, company_name = resolve_company_identifiers(company)
        if not ticker:
            ticker = company.upper()
        
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "apikey": api_key,
            "limit": 200,
            "sort": "LATEST"
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if "Error Message" in data or "Information" in data:
            logger.warning(f"AlphaVantage API issue: {data}")
            return []
        
        feed_data = data.get("feed", [])
        if not feed_data:
            return []
        
        # Process articles
        articles = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for item in feed_data:
            try:
                # Parse date
                time_published = item.get("time_published", "")
                if time_published:
                    try:
                        article_date = datetime.strptime(time_published[:8], "%Y%m%d")
                        if article_date < cutoff_date:
                            continue
                    except ValueError:
                        pass
                
                # Extract content
                title = item.get("title", "").strip()
                summary = item.get("summary", "").strip()
                url_link = item.get("url", "").strip()
                
                if not title or not url_link:
                    continue
                
                # Extract sentiment data
                ticker_sentiment_data = item.get("ticker_sentiment", [])
                relevance_score = 0.0
                sentiment_score = 0.0
                sentiment_label = "Neutral"
                
                for sentiment_item in ticker_sentiment_data:
                    if sentiment_item.get("ticker") == ticker:
                        try:
                            relevance_score = float(sentiment_item.get("relevance_score", 0))
                            sentiment_score = float(sentiment_item.get("ticker_sentiment_score", 0))
                            sentiment_label = sentiment_item.get("ticker_sentiment_label", "Neutral")
                            break
                        except (ValueError, TypeError):
                            continue
                
                article = {
                    "title": title,
                    "snippet": summary[:300],
                    "full_content": summary,
                    "link": url_link,
                    "source": extract_domain(url_link),
                    "published": time_published,
                    "sentiment_score": sentiment_score,
                    "sentiment_label": sentiment_label,
                    "relevance_score": relevance_score,
                    "source_type": "alphavantage_premium"
                }
                articles.append(article)
                
            except Exception as e:
                logger.debug(f"Error processing AlphaVantage article: {e}")
                continue
        
        logger.info(f"AlphaVantage: {len(articles)} articles for {ticker}")
        return articles
        
    except Exception as e:
        logger.error(f"AlphaVantage error for {company}: {e}")
        return []

async def fetch_nyt_api_parallel(company: str, days_back: int = 7) -> List[Dict]:
    """Fetch from NYT API using company names (not tickers)."""
    try:
        api_key = os.getenv("NYTIMES_API_KEY")
        if not api_key:
            logger.info("NYT API key not found")
            return []
        
        ticker, company_name = resolve_company_identifiers(company)
        
        # Prioritize company names for NYT search
        search_terms = []
        if company_name and company_name.strip():
            search_terms.append(company_name.strip())
            # Add cleaned version
            clean_name = company_name
            for suffix in [' Inc', ' Corp', ' Corporation', ' Company', ' Ltd', ' Limited']:
                clean_name = clean_name.replace(suffix, '')
            if clean_name != company_name and clean_name.strip():
                search_terms.append(clean_name.strip())
        elif len(company) > 5:
            search_terms.append(company)
        else:
            # Basic ticker-to-company mapping
            ticker_mapping = {
                'AAPL': 'Apple', 'MSFT': 'Microsoft', 'GOOGL': 'Google',
                'AMZN': 'Amazon', 'TSLA': 'Tesla', 'META': 'Meta',
                'NVDA': 'Nvidia', 'ONTO': 'Onto Innovation'
            }
            if ticker and ticker.upper() in ticker_mapping:
                search_terms.append(ticker_mapping[ticker.upper()])
            else:
                search_terms.append(company)
        
        # Limit to 3 terms for performance
        search_terms = search_terms[:3]
        logger.info(f"NYT search terms: {search_terms}")
        
        url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
        
        async def fetch_single_term(session, search_term):
            params = {
                "q": search_term,
                "api-key": api_key,
                "sort": "newest",
                "fl": "headline,abstract,lead_paragraph,web_url,pub_date,section_name",
                "page": 0
            }
            
            try:
                async with session.get(url, params=params, timeout=config.NYT_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "OK":
                            docs = data.get("response", {}).get("docs", [])
                            return process_nyt_docs(docs, search_term, days_back)
                    return []
            except Exception as e:
                logger.warning(f"NYT '{search_term}' failed: {e}")
                return []
        
        # Execute all searches in parallel
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_single_term(session, term) for term in search_terms]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_articles = []
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_articles.extend(result)
                logger.info(f"NYT '{search_terms[i]}': {len(result)} articles")
        
        logger.info(f"NYT total: {len(all_articles)} articles")
        return all_articles
        
    except Exception as e:
        logger.error(f"NYT API error: {e}")
        return []

def process_nyt_docs(docs: List[Dict], search_term: str, days_back: int) -> List[Dict]:
    """Process NYT API documents."""
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
            
            # Build content
            content_parts = []
            if abstract.strip():
                content_parts.append(abstract.strip())
            if lead_paragraph.strip() and lead_paragraph.strip() != abstract.strip():
                content_parts.append(lead_paragraph.strip())
            
            full_content = " ".join(content_parts)
            snippet = full_content[:400] if full_content else title
            
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
            logger.debug(f"Error processing NYT doc: {e}")
            continue
    
    return articles

async def fetch_rss_feeds_parallel(company: str, days_back: int = 7) -> List[Dict]:
    """Fetch from RSS feeds in parallel."""
    # Working RSS feeds
    feeds = {
        'cnbc_business': 'https://www.cnbc.com/id/10001147/device/rss/rss.html',
        'cnbc_finance': 'https://www.cnbc.com/id/10000664/device/rss/rss.html',
        'cnbc_earnings': 'https://www.cnbc.com/id/15839135/device/rss/rss.html',
        'investing_com': 'https://www.investing.com/rss/news.rss',
        'marketwatch_main': 'https://feeds.content.dowjones.io/public/rss/RSSMarketsMain',
        'seeking_alpha': 'https://seekingalpha.com/feed.xml',
        'fortune_business': 'https://fortune.com/feed/',
        'business_insider': 'https://www.businessinsider.com/rss'
    }
    
    # Add company-specific feeds
    ticker, company_name = resolve_company_identifiers(company)
    if ticker:
        feeds['yahoo_ticker'] = f'http://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US'
    
    async def fetch_single_rss(session, feed_name, feed_url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            async with session.get(feed_url, headers=headers, timeout=config.RSS_TIMEOUT) as response:
                if response.status != 200:
                    return []
                
                content = await response.read()
                
                # Parse in thread pool
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    feed = await loop.run_in_executor(executor, feedparser.parse, content)
                
                if not hasattr(feed, 'entries'):
                    return []
                
                return process_rss_entries(feed.entries, company, ticker, company_name, days_back)
                
        except Exception as e:
            logger.debug(f"RSS {feed_name} failed: {e}")
            return []
    
    # Execute all feeds in parallel
    connector = aiohttp.TCPConnector(limit=10)
    timeout = aiohttp.ClientTimeout(total=config.RSS_TIMEOUT)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch_single_rss(session, name, url) for name, url in feeds.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Combine results
    all_articles = []
    for i, result in enumerate(results):
        if isinstance(result, list):
            all_articles.extend(result)
    
    logger.info(f"RSS: {len(all_articles)} articles from {len(feeds)} feeds")
    return all_articles

def process_rss_entries(entries: List, company: str, ticker: Optional[str], 
                       company_name: Optional[str], days_back: int) -> List[Dict]:
    """Process RSS feed entries."""
    articles = []
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    # Get search terms
    search_terms = [company.lower()]
    if ticker:
        search_terms.append(ticker.lower())
    if company_name:
        search_terms.append(company_name.lower())
    
    for entry in entries[:20]:  # Limit entries per feed
        try:
            title = getattr(entry, 'title', '').strip()
            link = getattr(entry, 'link', '').strip()
            
            if not title or not link:
                continue
            
            # Get description
            description = ''
            for field in ['summary', 'description']:
                if hasattr(entry, field):
                    field_value = getattr(entry, field)
                    if isinstance(field_value, str):
                        description = field_value
                        break
            
            if description:
                description = re.sub(r'<[^>]+>', '', description)[:400]
            
            # Date parsing
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
            content = title.lower() + ' ' + description.lower()
            has_company_mention = any(term in content for term in search_terms)
            
            financial_keywords = ['stock', 'earnings', 'revenue', 'business', 'financial']
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

async def fetch_google_cse_parallel(company: str, days_back: int, existing_urls: set) -> List[Dict]:
    """Fetch from Google Custom Search in parallel."""
    try:
        api_key = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        if not api_key or not search_engine_id:
            logger.info("Google API credentials not found")
            return []
        
        ticker, company_name = resolve_company_identifiers(company)
        
        # Determine search company (prioritize company name)
        if company_name and company_name.strip():
            search_company = company_name.strip()
        elif len(company) > 5:
            search_company = company
        else:
            search_company = f'"{company}" company stock'
        
        # Create search queries
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_filter = start_date.strftime("%Y-%m-%d")
        
        search_queries = [
            f'"{search_company}" (news OR announcement) after:{date_filter}',
            f'"{search_company}" (earnings OR financial) after:{date_filter}',
            f'"{search_company}" (stock OR analyst) after:{date_filter}',
            f'site:bloomberg.com OR site:reuters.com "{search_company}" after:{date_filter}'
        ]
        
        async def fetch_single_query(session, query):
            try:
                url = "https://www.googleapis.com/customsearch/v1"
                params = {
                    "key": api_key,
                    "cx": search_engine_id,
                    "q": query,
                    "sort": "date",
                    "num": 8,
                    "dateRestrict": f"d{days_back}"
                }
                
                async with session.get(url, params=params, timeout=config.GOOGLE_TIMEOUT) as response:
                    if response.status == 429:
                        logger.warning("Google API rate limited")
                        return []
                    
                    response.raise_for_status()
                    data = await response.json()
                    items = data.get("items", [])
                    
                    articles = []
                    for item in items:
                        article_url = item.get("link", "")
                        if article_url in existing_urls:
                            continue
                        
                        article = {
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                            "link": article_url,
                            "source": extract_domain(article_url),
                            "published": "",
                            "source_type": "google_search"
                        }
                        articles.append(article)
                    
                    return articles
                    
            except Exception as e:
                logger.debug(f"Google query failed: {e}")
                return []
        
        # Execute queries in parallel
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_single_query(session, query) for query in search_queries]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
        
        logger.info(f"Google CSE: {len(all_articles)} articles")
        return all_articles[:15]  # Limit Google results
        
    except Exception as e:
        logger.error(f"Google CSE error: {e}")
        return []

# ============================================================================
# PARALLEL ORCHESTRATION
# ============================================================================

async def fetch_all_sources_parallel(company: str, days_back: int = 7) -> Dict[str, List[Dict]]:
    """Fetch from all sources in parallel."""
    logger.info(f"🚀 Starting parallel fetch for {company}")
    start_time = time.time()
    
    # Create async tasks for all sources
    async def fetch_alphavantage_async():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(fetch_alphavantage_news_enhanced, company, days_back)
            return await loop.run_in_executor(None, lambda: future.result(timeout=30))
    
    # Execute all sources simultaneously
    tasks = [
        fetch_alphavantage_async(),
        fetch_nyt_api_parallel(company, days_back),
        fetch_rss_feeds_parallel(company, days_back)
    ]
    
    try:
        alphavantage_articles, nyt_articles, rss_articles = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(alphavantage_articles, Exception):
            logger.error(f"AlphaVantage failed: {alphavantage_articles}")
            alphavantage_articles = []
        if isinstance(nyt_articles, Exception):
            logger.error(f"NYT failed: {nyt_articles}")
            nyt_articles = []
        if isinstance(rss_articles, Exception):
            logger.error(f"RSS failed: {rss_articles}")
            rss_articles = []
        
        parallel_time = time.time() - start_time
        logger.info(f"⚡ Parallel fetch complete in {parallel_time:.2f}s")
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
        return {'alphavantage': [], 'nyt': [], 'rss': [], 'parallel_time': 0}

# ============================================================================
# ARTICLE PROCESSING
# ============================================================================

def score_articles(articles: List[Dict], company: str) -> List[Tuple[Dict, float]]:
    """Score articles based on relevance and source quality."""
    scored_articles = []
    
    for article in articles:
        score = 0.0
        
        source = article.get('source', '').lower()
        source_type = article.get('source_type', 'google_search')
        title = article.get('title', '').lower()
        snippet = article.get('snippet', '').lower()
        
        # Source penalties/bonuses
        if source in UNWANTED_SOURCES:
            score += UNWANTED_SOURCES[source]
        if source in PREMIUM_SOURCES:
            score += PREMIUM_SOURCES[source]
        
        # Source type bonuses
        if source_type == 'alphavantage_premium':
            score += 15
            if article.get('relevance_score'):
                score += float(article.get('relevance_score', 0)) * 10
        elif source_type == 'nyt_api':
            score += 25
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
        
        scored_articles.append((article, score))
    
    return sorted(scored_articles, key=lambda x: x[1], reverse=True)

def deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """Remove duplicate articles."""
    seen_urls = set()
    seen_titles = set()
    unique_articles = []
    
    for article in articles:
        url = article.get('link', '')
        title = article.get('title', '').lower().strip()
        
        # Skip if URL already seen
        if url and url in seen_urls:
            continue
        
        # Skip if very similar title
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
    
    return unique_articles

def assess_article_batch_relevance(articles: List[Dict], company: str) -> Tuple[List[Dict], Dict]:
    """Assess relevance for a batch of articles."""
    relevance_assessor = RelevanceAssessor()
    ticker, company_name = resolve_company_identifiers(company)
    
    relevant_articles = []
    total_articles = len(articles)
    relevance_scores = []
    company_specific_count = 0
    
    for article in articles:
        relevance = relevance_assessor.assess_article_relevance(article, company, ticker, company_name)
        article['relevance_assessment'] = relevance
        
        relevance_scores.append(relevance['overall_relevance'])
        
        if relevance['is_company_specific']:
            company_specific_count += 1
            relevant_articles.append(article)
        elif total_articles < 10 and relevance['overall_relevance'] >= config.MIN_RELEVANCE_SCORE:
            relevant_articles.append(article)
    
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0
    relevance_percentage = (company_specific_count / total_articles) if total_articles > 0 else 0
    
    stats = {
        'total_articles': total_articles,
        'relevant_articles': company_specific_count,
        'relevance_percentage': relevance_percentage,
        'average_relevance_score': avg_relevance
    }
    
    return relevant_articles, stats

def should_trigger_google_cse(all_articles: List[Dict], relevant_articles: List[Dict], 
                             relevance_stats: Dict) -> bool:
    """Decide whether to trigger Google CSE."""
    total_articles = len(all_articles)
    relevant_count = len(relevant_articles)
    relevance_percentage = relevance_stats.get('relevance_percentage', 0)
    
    logger.info(f"CSE Decision: {total_articles} total, {relevant_count} relevant ({relevance_percentage:.1%})")
    
    # Decision criteria
    has_sufficient_relevant = relevant_count >= config.MIN_RELEVANT_ARTICLES_BEFORE_GOOGLE
    has_good_relevance_rate = relevance_percentage >= config.MIN_RELEVANCE_PERCENTAGE
    is_low_volume_company = total_articles < 15
    
    if has_sufficient_relevant and has_good_relevance_rate:
        decision = False
        reason = f"Sufficient relevant content ({relevant_count} relevant, {relevance_percentage:.1%} rate)"
    elif is_low_volume_company:
        decision = True
        reason = f"Low volume company ({total_articles} articles)"
    elif relevant_count < config.MIN_RELEVANT_ARTICLES_BEFORE_GOOGLE:
        decision = True
        reason = f"Insufficient relevant articles ({relevant_count} < {config.MIN_RELEVANT_ARTICLES_BEFORE_GOOGLE})"
    else:
        decision = False
        reason = "Edge case - defaulting to no CSE"
    
    logger.info(f"🎯 CSE Decision: {'TRIGGER' if decision else 'SKIP'} - {reason}")
    return decision

# ============================================================================
# ANALYSIS GENERATION
# ============================================================================

def generate_enhanced_analysis(company: str, articles: List[Dict]) -> Dict[str, List[str]]:
    """Generate analysis using Claude Sonnet 4 with OpenAI fallback."""
    if not articles:
        return create_empty_summaries(company)
    
    # Try Claude Sonnet 4 first
    if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
        try:
            return generate_claude_analysis(company, articles)
        except Exception as claude_error:
            logger.error(f"Claude Sonnet 4 failed: {claude_error}")
            logger.info("Falling back to OpenAI...")
    
    # Fallback to OpenAI
    try:
        return generate_openai_analysis(company, articles)
    except Exception as openai_error:
        logger.error(f"OpenAI analysis failed: {openai_error}")
        return create_error_summaries(company, str(openai_error))

def generate_claude_analysis(company: str, articles: List[Dict]) -> Dict[str, List[str]]:
    """Generate analysis using Claude Sonnet 4."""
    anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Prepare article content
    article_text = ""
    for i, article in enumerate(articles[:30], 1):
        source_type = article.get('source_type', 'google_search')
        
        if source_type == 'alphavantage_premium':
            sentiment_label = article.get('sentiment_label', 'Neutral')
            sentiment_score = article.get('sentiment_score', 0)
            relevance_score = article.get('relevance_score', 0)
            
            article_text += f"\n{i}. [ALPHAVANTAGE+SENTIMENT] {article['title']}\n"
            article_text += f"   Source: {article['source']} | Sentiment: {sentiment_label} ({sentiment_score:.3f}) | Relevance: {relevance_score:.3f}\n"
            article_text += f"   Content: {article.get('full_content', article.get('snippet', ''))}\n"
        elif source_type == 'nyt_api':
            article_text += f"\n{i}. [NYT_PREMIUM] {article['title']}\n"
            article_text += f"   Source: {article['source']} (NYT Editorial Quality)\n"
            article_text += f"   Content: {article.get('full_content', article.get('snippet', ''))}\n"
        else:
            article_text += f"\n{i}. [PREMIUM_SOURCE] {article['title']}\n"
            article_text += f"   Source: {article['source']}\n"
            article_text += f"   Content: {article.get('snippet', '')}\n"
        
        article_text += f"   Link: {article['link']}\n"
    
    # Create prompt
    prompt = f"""You are a Managing Director of Equity Research at Goldman Sachs writing institutional-grade investment analysis for {company}.

COMPREHENSIVE DATA ({len(articles[:30])} articles):
{article_text}

Generate actionable insights for portfolio managers making investment decisions.

**EXECUTIVE SUMMARY** (4-5 bullets)
Strategic developments affecting fundamental business outlook with quantified impacts and timelines.

**INVESTOR INSIGHTS** (4-5 bullets)  
Valuation drivers, analyst actions, and market sentiment with specific metrics and price targets.

**CATALYSTS & RISKS** (4-5 bullets)
Near-term trading catalysts and risk factors with probability estimates and timelines.

REQUIREMENTS:
- Start each bullet with "•"
- Include specific financial metrics and timeline estimates
- Cite sources naturally (e.g., "according to reuters.com")
- Use professional investment commentary style
- Quantify everything possible with ranges and confidence levels"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=7500,
        temperature=0.07,
        messages=[{"role": "user", "content": prompt}]
    )
    
    analysis_text = response.content[0].text
    logger.info(f"Claude Sonnet 4 analysis generated: {len(analysis_text)} chars")
    
    return parse_analysis_response(analysis_text)

def generate_openai_analysis(company: str, articles: List[Dict]) -> Dict[str, List[str]]:
    """Generate analysis using OpenAI as fallback."""
    # Prepare article content (simplified for OpenAI)
    article_text = ""
    for i, article in enumerate(articles[:30], 1):
        article_text += f"\n{i}. {article['title']}\n"
        article_text += f"   Source: {article['source']}\n"
        article_text += f"   Content: {article.get('snippet', '')}\n"
    
    prompt = f"""You are a senior equity research analyst analyzing {company}.

ARTICLES TO ANALYZE:
{article_text}

Generate institutional-grade analysis in exactly this format:

**EXECUTIVE SUMMARY**
• [bullet point 1]
• [bullet point 2] 
• [bullet point 3]

**INVESTOR INSIGHTS**
• [bullet point 1]
• [bullet point 2]
• [bullet point 3]

**CATALYSTS & RISKS**  
• [bullet point 1]
• [bullet point 2]
• [bullet point 3]

Focus on actionable insights with specific metrics and timelines."""
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.05,
        max_tokens=2000
    )
    
    analysis_text = response.choices[0].message.content
    logger.info(f"OpenAI analysis generated: {len(analysis_text)} chars")
    
    return parse_analysis_response(analysis_text)

def parse_analysis_response(text: str) -> Dict[str, List[str]]:
    """Parse LLM response into structured summaries."""
    sections = {"executive": [], "investor": [], "catalysts": []}
    current_section = None
    
    # Section detection patterns
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
        if line.startswith(('•', '-', '*')) and current_section:
            bullet = line.lstrip('•-* ').strip()
            if bullet and len(bullet) > 10:
                sections[current_section].append(bullet)
    
    # Ensure each section has content
    for section_name, bullets in sections.items():
        if not bullets:
            sections[section_name] = ["No significant developments identified in this category."]
    
    return sections

# ============================================================================
# UTILITY FUNCTIONS  
# ============================================================================

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return "unknown"

def create_empty_summaries(company: str) -> Dict[str, List[str]]:
    """Create empty summaries when no articles available."""
    return {
        "executive": [f"No recent financial news found for {company}. Try expanding date range or verifying company ticker."],
        "investor": ["No recent investor-relevant developments identified."],
        "catalysts": ["No material catalysts or risks detected in recent coverage."]
    }

def create_error_summaries(company: str, error_msg: str) -> Dict[str, List[str]]:
    """Create error summaries when analysis fails."""
    return {
        "executive": [f"Analysis temporarily unavailable for {company}: {error_msg[:100]}..."],
        "investor": ["Please try again in a few moments or contact support."],
        "catalysts": ["Consider checking company's investor relations page directly."]
    }

def create_empty_result(company: str, days_back: int) -> Dict[str, Any]:
    """Create empty result structure."""
    return {
        'company': company,
        'articles': [],
        'summaries': create_empty_summaries(company),
        'metrics': {
            'total_articles': 0,
            'alphavantage_articles': 0,
            'nyt_articles': 0,
            'rss_articles': 0,
            'google_articles': 0,
            'analysis_quality': 'No Data',
            'response_time': 0
        },
        'success': False
    }

def create_error_result(company: str, days_back: int, error_msg: str) -> Dict[str, Any]:
    """Create error result structure."""
    return {
        'company': company,
        'articles': [],
        'summaries': create_error_summaries(company, error_msg),
        'metrics': {
            'total_articles': 0,
            'analysis_quality': 'Error',
            'response_time': 0
        },
        'success': False,
        'error': error_msg
    }

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def fetch_comprehensive_news_guaranteed_30_enhanced(company: str, days_back: int = 7, 
                                                   enable_quality_validation: bool = None) -> Dict[str, Any]:
    """
    MAIN ENTRY POINT - Comprehensive news analysis with quality validation.
    
    Features:
    - Parallel source fetching (AlphaVantage + NYT + RSS + Google CSE)
    - Company name resolution for better search results
    - Advanced relevance filtering and scoring
    - Claude Sonnet 4 quality validation with web search (optional)
    - OpenAI fallback for analysis generation
    - Dynamic Google CSE triggering based on content quality
    
    Args:
        company: Company name or ticker symbol
        days_back: Number of days to look back for articles
        enable_quality_validation: Enable Claude Sonnet 4 quality validation
                                  (default: auto-detect based on environment)
    
    Returns:
        Dict containing articles, summaries, metrics, and quality validation results
    """
    
    # Auto-detect quality validation if not specified
    if enable_quality_validation is None:
        enable_quality_validation = (
            config.QUALITY_VALIDATION_ENABLED and 
            ANTHROPIC_AVAILABLE and 
            os.getenv("ANTHROPIC_API_KEY")
        )
    
    start_time = time.time()
    logger.info(f"🚀 Starting comprehensive analysis for {company} (quality validation: {'enabled' if enable_quality_validation else 'disabled'})")
    
    try:
        # Run the async orchestration
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context, run in thread pool
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        _run_comprehensive_analysis(company, days_back, enable_quality_validation)
                    )
                    results = future.result(timeout=config.PARALLEL_TIMEOUT)
            else:
                # No running loop
                results = loop.run_until_complete(
                    _run_comprehensive_analysis(company, days_back, enable_quality_validation)
                )
        except RuntimeError:
            # No event loop
            results = asyncio.run(
                _run_comprehensive_analysis(company, days_back, enable_quality_validation)
            )
        
        execution_time = time.time() - start_time
        results['metrics']['response_time'] = execution_time
        
        logger.info(f"✅ Analysis complete for {company} in {execution_time:.2f}s")
        logger.info(f"   • Articles: {results['metrics']['total_articles']}")
        logger.info(f"   • Quality: {results['metrics']['analysis_quality']}")
        if enable_quality_validation and results.get('quality_validation', {}).get('score'):
            logger.info(f"   • Quality Score: {results['quality_validation']['score']:.1f}/10")
        
        return results
        
    except Exception as e:
        logger.error(f"Comprehensive analysis failed for {company}: {str(e)}")
        return create_error_result(company, days_back, str(e))

async def _run_comprehensive_analysis(company: str, days_back: int, 
                                    enable_quality_validation: bool) -> Dict[str, Any]:
    """Internal async function for comprehensive analysis."""
    
    # Phase 1: Parallel source fetching
    logger.info("⚡ Phase 1: Parallel source fetching...")
    source_results = await fetch_all_sources_parallel(company, days_back)
    
    # Combine all articles
    all_articles = []
    all_articles.extend(source_results['alphavantage'])
    all_articles.extend(source_results['nyt'])
    all_articles.extend(source_results['rss'])
    
    logger.info(f"📊 Combined {len(all_articles)} articles from all premium sources")
    
    # Phase 2: Relevance assessment and dynamic decision making
    logger.info("🧠 Phase 2: Relevance assessment...")
    relevant_articles, relevance_stats = assess_article_batch_relevance(all_articles, company)
    
    # Decide on Google CSE
    should_use_google = should_trigger_google_cse(all_articles, relevant_articles, relevance_stats)
    
    # Phase 3: Conditional Google CSE
    google_articles = []
    if should_use_google:
        logger.info("🔍 Phase 3: Google CSE gap-filling...")
        existing_urls = {a.get('link', '') for a in all_articles}
        google_articles = await fetch_google_cse_parallel(company, days_back, existing_urls)
        all_articles.extend(google_articles)
        
        # Re-assess relevance with Google articles
        relevant_articles, relevance_stats = assess_article_batch_relevance(all_articles, company)
    else:
        logger.info("✅ Phase 3: Skipping Google CSE - sufficient premium content")
    
    # Phase 4: Final article selection
    logger.info("🎯 Phase 4: Final article selection...")
    unique_articles = deduplicate_articles(all_articles)
    scored_articles = score_articles(unique_articles, company)
    final_articles = [article for article, score in scored_articles[:config.TARGET_ARTICLE_COUNT]]
    
    # Phase 5: Analysis generation
    logger.info("📝 Phase 5: Analysis generation...")
    initial_summaries = generate_enhanced_analysis(company, final_articles)
    
    # Phase 6: Optional quality validation
    final_summaries = initial_summaries
    quality_info = {'enabled': enable_quality_validation, 'passed': None, 'score': None}
    
    if enable_quality_validation and final_articles:
        logger.info("🔍 Phase 6: Quality validation...")
        quality_engine = QualityValidationEngine()
        
        try:
            quality_result = await quality_engine.validate_and_enhance_analysis(
                company, initial_summaries, final_articles
            )
            final_summaries = quality_result['analysis']
            quality_info = quality_result['quality_validation']
            logger.info(f"✅ Quality validation completed - Score: {quality_info.get('score', 'N/A')}")
        except Exception as quality_error:
            logger.error(f"❌ Quality validation failed: {quality_error}")
            quality_info = {
                'enabled': True,
                'passed': False,
                'error': str(quality_error),
                'score': None
            }
    else:
        logger.info("⚡ Phase 6: Quality validation disabled")
    
    # Calculate final metrics
    total_articles = len(final_articles)
    alphavantage_count = len(source_results['alphavantage'])
    nyt_count = len(source_results['nyt'])
    rss_count = len(source_results['rss'])
    google_count = len(google_articles)
    
    # Premium source calculation
    premium_sources_list = list(PREMIUM_SOURCES.keys())
    premium_count = sum(1 for a in final_articles if a.get('source', '') in premium_sources_list)
    premium_coverage = (premium_count / total_articles * 100) if total_articles > 0 else 0
    
    # Quality determination
    if quality_info.get('score') and quality_info['score'] >= 8.5:
        analysis_quality = "Premium+"
    elif alphavantage_count >= 8 and premium_coverage >= 40:
        analysis_quality = "Premium"
    elif alphavantage_count >= 5 and premium_coverage >= 30:
        analysis_quality = "Institutional"
    elif alphavantage_count >= 3 or premium_coverage >= 40:
        analysis_quality = "Professional"
    elif total_articles >= 10:
        analysis_quality = "Standard"
    else:
        analysis_quality = "Limited"
    
    return {
        'company': company,
        'articles': final_articles,
        'summaries': final_summaries,
        'metrics': {
            'total_articles': total_articles,
            'alphavantage_articles': alphavantage_count,
            'nyt_articles': nyt_count,
            'rss_articles': rss_count,
            'google_articles': google_count,
            'premium_sources_count': premium_count,
            'premium_coverage': round(premium_coverage, 1),
            'relevant_articles': relevance_stats['relevant_articles'],
            'relevance_percentage': round(relevance_stats['relevance_percentage'] * 100, 1),
            'analysis_quality': analysis_quality,
            'parallel_optimization': True,
            'quality_enhanced': enable_quality_validation
        },
        'source_performance': {
            'alphavantage': alphavantage_count,
            'nyt': nyt_count,
            'rss': rss_count,
            'google_cse': google_count
        },
        'relevance_metrics': relevance_stats,
        'google_cse_triggered': should_use_google,
        'quality_validation': quality_info,
        'success': len(final_articles) > 0
    }

# ============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================================================

# Deprecated function aliases for backward compatibility
def fetch_comprehensive_news_guaranteed_30_enhanced_PARALLEL_WITH_QUALITY(company: str, days_back: int = 7) -> Dict[str, Any]:
    """Deprecated - use fetch_comprehensive_news_guaranteed_30_enhanced() instead."""
    logger.warning("Function name deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.")
    return fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back, enable_quality_validation=True)

def fetch_comprehensive_news_guaranteed_30_enhanced_WITH_OPTIONAL_QUALITY(company: str, days_back: int = 7, 
                                                                         enable_quality_validation: bool = True) -> Dict[str, Any]:
    """Deprecated - use fetch_comprehensive_news_guaranteed_30_enhanced() instead."""
    logger.warning("Function name deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.")
    return fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back, enable_quality_validation)

def fetch_comprehensive_news_guaranteed_30_enhanced_WITH_ITERATIVE_QUALITY(company: str, days_back: int = 7) -> Dict[str, Any]:
    """Deprecated - use fetch_comprehensive_news_guaranteed_30_enhanced() instead."""
    logger.warning("Function name deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.")
    return fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back, enable_quality_validation=True)

def fetch_enhanced_news_with_parallel_sources(company: str, days_back: int = 7) -> Dict[str, Any]:
    """Deprecated - use fetch_comprehensive_news_guaranteed_30_enhanced() instead."""
    logger.warning("Function name deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.")
    return fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back, enable_quality_validation=False)

def fetch_enhanced_news_with_quality_validation(company: str, days_back: int = 7) -> Dict[str, Any]:
    """Deprecated - use fetch_comprehensive_news_guaranteed_30_enhanced() instead."""
    logger.warning("Function name deprecated. Use fetch_comprehensive_news_guaranteed_30_enhanced() instead.")
    return fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back, enable_quality_validation=True)

def generate_premium_analysis_upgraded_v2(company: str, articles: List[Dict], max_articles: int = 30) -> Dict[str, List[str]]:
    """Deprecated - functionality moved to generate_enhanced_analysis()."""
    logger.warning("Function name deprecated. Use generate_enhanced_analysis() instead.")
    return generate_enhanced_analysis(company, articles)

def generate_premium_analysis_claude_sonnet_4_enhanced(company: str, articles: List[Dict], max_articles: int = 30) -> Dict[str, List[str]]:
    """Deprecated - functionality moved to generate_enhanced_analysis()."""
    logger.warning("Function name deprecated. Use generate_enhanced_analysis() instead.")
    return generate_enhanced_analysis(company, articles)

def generate_premium_analysis_30_articles(company: str, articles: List[Dict]) -> Dict[str, List[str]]:
    """Deprecated - use generate_enhanced_analysis() instead."""
    logger.warning("Function name deprecated. Use generate_enhanced_analysis() instead.")
    return generate_enhanced_analysis(company, articles)

def create_empty_results_enhanced(company: str, days_back: int) -> Dict[str, Any]:
    """Deprecated - use create_empty_result() instead."""
    logger.warning("Function name deprecated. Use create_empty_result() instead.")
    return create_empty_result(company, days_back)

# Quality validation functions for backward compatibility
async def validate_analysis_quality(company: str, analysis: Dict[str, List[str]], articles: List[Dict]) -> Dict[str, Any]:
    """Backward compatibility function for quality validation."""
    logger.warning("Direct quality validation is deprecated. Use enable_quality_validation=True in main function instead.")
    quality_engine = QualityValidationEngine()
    return await quality_engine.validate_and_enhance_analysis(company, analysis, articles)

def is_quality_validation_available() -> bool:
    """Check if quality validation is available."""
    return ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY") is not None

# Configuration functions for backward compatibility
def get_analysis_config() -> NewsAnalysisConfig:
    """Get analysis configuration - for backward compatibility."""
    return NewsAnalysisConfig()

class ConfigurationManager:
    """Deprecated configuration manager - use NewsAnalysisConfig directly."""
    
    def __init__(self):
        logger.warning("ConfigurationManager is deprecated. Use NewsAnalysisConfig() directly.")
    
    def get_analysis_config(self) -> NewsAnalysisConfig:
        return NewsAnalysisConfig()

# ============================================================================
# OPTIONAL TESTING
# ============================================================================

def test_news_analysis(company: str = "AAPL") -> None:
    """Test the news analysis pipeline."""
    logger.info(f"🧪 Testing news analysis for {company}")
    
    result = fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back=7)
    
    print(f"\n🎯 Test Results for {company}:")
    print(f"Success: {result['success']}")
    print(f"Articles: {result['metrics']['total_articles']}")
    print(f"Quality: {result['metrics']['analysis_quality']}")
    
    if result['summaries']:
        print(f"\nExecutive Summary ({len(result['summaries']['executive'])} bullets):")
        for bullet in result['summaries']['executive']:
            print(f"  • {bullet[:100]}...")

if __name__ == "__main__":
    # Simple test when run directly
    test_news_analysis()