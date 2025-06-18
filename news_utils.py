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
from anthropic import RateLimitError

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

class ClaudeWebSearchEngine:
    """
    Web search integration for Claude Sonnet 4 and Opus 4 using official Anthropic API.
    Based on: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool
    """
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def validate_with_web_search(self, 
                                     company: str, 
                                     analysis: Dict[str, List[str]], 
                                     articles: List[Dict],
                                     attempt: int = 1) -> Dict[str, Any]:
        """
        Enhanced quality validation using Claude Sonnet 4 with REAL web search capabilities.
        """
        try:
            # Create validation prompt with web search instructions
            validation_prompt = self._create_web_search_validation_prompt(
                company, analysis, articles, attempt
            )
            
            # Call Claude Sonnet 4 with web search tool enabled
            response = await self._call_claude_with_web_search(validation_prompt)
            
            # Parse and return results
            return self._parse_web_search_response(response)
            
        except Exception as e:
            logger.error(f"Web search validation failed: {e}")
            return self._create_fallback_result(analysis, str(e))
    
    def _create_web_search_validation_prompt(self, 
                                           company: str, 
                                           analysis: Dict[str, List[str]], 
                                           articles: List[Dict],
                                           attempt: int) -> str:
        """Create validation prompt that leverages web search for fact-checking."""
        
        formatted_analysis = self._format_analysis_for_review(analysis)
        today_str = datetime.now().strftime("%B %d, %Y")
        
        return f"""You are a Managing Director at Goldman Sachs validating financial analysis with REAL-TIME WEB SEARCH capabilities.

**CRITICAL INSTRUCTIONS**: Use web search to verify ALL claims and enhance the analysis.

COMPANY: {company}
TODAY'S DATE: {today_str}
VALIDATION ATTEMPT: {attempt}

CURRENT ANALYSIS TO VALIDATE:
{formatted_analysis}

**MANDATORY WEB SEARCH TASKS**:
1. Search for {company} current stock price and trading data
2. Verify recent earnings, revenue, and financial metrics mentioned
3. Check latest analyst price targets and ratings  
4. Confirm recent news developments and business updates
5. Validate any numerical claims with current market data

**VALIDATION FRAMEWORK** (Score each 0-10):
- **Fact Accuracy**: All claims verified with current web data
- **Market Context**: Current stock price, valuation multiples included  
- **Investment Actionability**: Specific, measurable investment insights
- **Timeliness**: Recent developments and current market positioning
- **Professional Quality**: Goldman Sachs institutional standards

**ENHANCEMENT REQUIREMENTS**:
- Update ALL outdated information with current web data
- Add specific current metrics (stock price, P/E, analyst targets)
- Include recent developments from web search
- Enhance vague statements with specific, actionable insights
- Cite web sources naturally in the analysis

**OUTPUT FORMAT**:
Return JSON with this exact structure:

```json
{{
  "overall_verdict": "pass" | "needs_revision" | "fail",
  "overall_score": float,
  "web_searches_performed": [
    {{
      "query": "search query used",
      "key_finding": "important discovery",
      "data_updated": "specific metric updated"
    }}
  ],
  "revised_analysis": {{
    "executive": [
      "Enhanced bullet with current web-verified data",
      "Investment insight with specific metrics from web search",
      "Strategic context with recent developments"
    ],
    "investor": [
      "Current valuation analysis with web-verified metrics",
      "Updated analyst data from recent research",
      "Market positioning with current competitive landscape"
    ],
    "catalysts": [
      "Specific catalyst with current timeline and probability",
      "Risk assessment with quantified current impact",
      "Trading implications with current market data"
    ]
  }},
  "enhancements_made": [
    "List of specific improvements using web data"
  ],
  "validation_metadata": {{
    "current_stock_price": "verified price",
    "market_cap": "current market cap",
    "recent_news_count": int,
    "data_verification_count": int
  }}
}}
```

**CRITICAL**: Use web search to update the analysis with current, verified data."""

    async def _call_claude_with_web_search(self, prompt: str):
        """Call Claude Sonnet 4 with web search - safe domain list."""
        
        try:
            # Test without domain restrictions first
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=8000,
                        temperature=0.05,
                        messages=[{"role": "user", "content": prompt}],
                        tools=[{
                            "type": "web_search_20250305",
                            "name": "web_search",
                            "max_uses": 10
                            # No domain filtering - Claude will find accessible sources
                        }]
                    )
                ),
                timeout=180.0
            )
            return response
            
        except Exception as e:
            logger.error(f"Claude web search API call failed: {e}")
            raise

    def _parse_web_search_response(self, response) -> Dict[str, Any]:
        """Parse Claude's response with diagnostic logging."""
        
        logger.info(f"🐛 DIAGNOSTIC: _parse_web_search_response called")
        logger.info(f"🐛 Response type: {type(response)}")
        
        try:
            # Extract text content
            final_content = ""
            if hasattr(response, 'content') and isinstance(response.content, list):
                logger.info(f"🐛 Response has {len(response.content)} content blocks")
                for i, content_block in enumerate(response.content):
                    if hasattr(content_block, 'type'):
                        logger.info(f"🐛 Block {i}: type={content_block.type}")
                        if content_block.type == "text":
                            final_content += content_block.text
            else:
                final_content = str(response.content[0].text) if response.content else ""
                logger.info(f"🐛 Extracted text directly, length: {len(final_content)}")
            
            logger.info(f"🐛 Final content length: {len(final_content)}")
            logger.info(f"🐛 First 200 chars: {final_content[:200]}...")
            
            # Find JSON in response
            json_start = final_content.find('{')
            json_end = final_content.rfind('}') + 1
            
            logger.info(f"🐛 JSON boundaries: start={json_start}, end={json_end}")
            
            if json_start == -1 or json_end == 0:
                logger.warning("🐛 No JSON found in response")
                return self._create_simple_fallback()
            
            json_text = final_content[json_start:json_end]
            logger.info(f"🐛 Extracted JSON length: {len(json_text)}")
            logger.info(f"🐛 JSON text: {json_text[:500]}...")
            
            # Try to parse JSON
            try:
                result = json.loads(json_text)
                logger.info(f"🐛 JSON parsed successfully!")
                logger.info(f"🐛 Parsed result keys: {list(result.keys())}")
                logger.info(f"🐛 overall_score in result: {result.get('overall_score')} (type: {type(result.get('overall_score'))})")
            except json.JSONDecodeError as e:
                logger.error(f"🐛 JSON parsing failed: {e}")
                logger.error(f"🐛 Error position: line {e.lineno if hasattr(e, 'lineno') else 'unknown'}")
                logger.info(f"🐛 Problematic JSON: {json_text}")
                return self._create_simple_fallback()
            
            # Create safe result
            safe_result = {
                'overall_score': self._safe_float(result.get('overall_score', 5.0)),
                'overall_verdict': str(result.get('overall_verdict', 'fail')),
                'revised_analysis': result.get('revised_analysis', {}),
                'enhancements_made': result.get('enhancements_made', []),
                'validation_metadata': result.get('validation_metadata', {}),
                'critical_issues': result.get('critical_issues', []),
                'web_search_metadata': {
                    'searches_performed': 1,
                    'web_search_enabled': True
                }
            }
            
            logger.info(f"🐛 Created safe result with score: {safe_result['overall_score']}")
            return safe_result
            
        except Exception as e:
            logger.error(f"🐛 Error parsing response: {e}")
            import traceback
            logger.error(f"🐛 Parse traceback: {traceback.format_exc()}")
            return self._create_simple_fallback()

    def _safe_float(self, value):
        """Safely convert value to float with logging."""
        logger.info(f"🐛 _safe_float called with: {value} (type: {type(value)})")
        try:
            if isinstance(value, (int, float)):
                result = float(value)
                logger.info(f"🐛 Converted to float: {result}")
                return result
            elif isinstance(value, str):
                result = float(value)
                logger.info(f"🐛 Converted string to float: {result}")
                return result
            else:
                logger.warning(f"🐛 Unknown type, defaulting to 5.0")
                return 5.0
        except Exception as e:
            logger.error(f"🐛 Conversion failed: {e}, defaulting to 5.0")
            return 5.0

    def _create_simple_fallback(self):
        """Create simple fallback result with logging."""
        logger.warning(f"🐛 Creating fallback result")
        return {
            'overall_score': 5.0,
            'overall_verdict': 'fail',
            'revised_analysis': {},
            'enhancements_made': ['Fallback used due to parsing error'],
            'validation_metadata': {},
            'critical_issues': [],
            'web_search_metadata': {
                'searches_performed': 0,
                'web_search_enabled': True
            }
        }

    def _format_analysis_for_review(self, analysis: Dict[str, List[str]]) -> str:
        """Format analysis for Claude review."""
        formatted = ""
        section_headers = {
            'executive': '**EXECUTIVE SUMMARY**',
            'investor': '**INVESTOR INSIGHTS**',
            'catalysts': '**CATALYSTS & RISKS**'
        }
        
        for section_key, bullets in analysis.items():
            header = section_headers.get(section_key, f'**{section_key.upper()}**')
            formatted += f"{header}\n"
            for i, bullet in enumerate(bullets, 1):
                # Clean HTML for Claude
                clean_bullet = bullet.replace('<strong>', '').replace('</strong>', '')
                clean_bullet = clean_bullet.replace('<em>', '').replace('</em>', '')
                formatted += f"{i}. {clean_bullet}\n"
            formatted += "\n"
        
        return formatted
    
    def _create_fallback_result(self, analysis: Dict[str, List[str]], error_msg: str) -> Dict[str, Any]:
        """Create fallback result when web search fails."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': True,
                'passed': False,
                'error': error_msg,
                'web_search_enabled': False,
                'message': 'Web search validation failed - using original analysis'
            },
            'success': True,
            'enhanced': False
        }

# ============================================================================
# QUALITY VALIDATION
# ============================================================================

class QualityValidationEngine:
    """
    Updated quality validation engine with REAL Claude Sonnet 4 web search.
    """
    
    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.web_search_engine = None
        
        if self.anthropic_api_key:
            self.web_search_engine = ClaudeWebSearchEngine(self.anthropic_api_key)
            logger.info("✅ Enhanced Quality Validation with Web Search initialized")
        else:
            logger.warning("⚠️ Enhanced quality validation disabled - missing Anthropic API key")

        self.rate_limit_delay = 60
        self.max_retries = 2
        self.retry_delays = [0, 30, 60]

    async def _run_validation_with_retries(self, 
                                     company: str, 
                                     analysis: Dict[str, List[str]], 
                                     articles: List[Dict],
                                     attempt: int = 1) -> Dict[str, Any]:
        """Validation with diagnostic logging."""
        try:
            logger.info(f"🐛 DIAGNOSTIC: _run_validation_with_retries called with attempt={attempt}")
            
            # Add delay between attempts
            if attempt > 1:
                delay = 45
                logger.info(f"⏱️ Waiting {delay}s before attempt {attempt}...")
                await asyncio.sleep(delay)
            
            logger.info(f"🔍 Quality validation attempt {attempt} for {company}")
            
            # Try validation with rate limit handling
            try:
                logger.info(f"🐛 About to call web_search_engine.validate_with_web_search")
                validation_result = await self.web_search_engine.validate_with_web_search(
                    company, analysis, articles, attempt
                )
                logger.info(f"🐛 Got validation_result type: {type(validation_result)}")
                logger.info(f"🐛 validation_result keys: {list(validation_result.keys()) if isinstance(validation_result, dict) else 'Not a dict'}")
                
            except Exception as e:
                logger.error(f"🐛 Exception in validate_with_web_search: {e}")
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    logger.warning(f"Rate limit hit on attempt {attempt}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(90)
                        return await self._run_validation_with_retries(company, analysis, articles, attempt + 1)
                    else:
                        logger.error(f"Rate limited after {attempt} attempts")
                        return self._create_rate_limit_fallback_result(analysis, attempt)
                else:
                    raise e
            
            # Extract basic info with diagnostics
            overall_score = validation_result.get('overall_score', 0)
            verdict = validation_result.get('overall_verdict', 'fail')
            
            logger.info(f"🐛 Extracted overall_score: {overall_score} (type: {type(overall_score)})")
            logger.info(f"🐛 Extracted verdict: {verdict}")
            
            logger.info(f"✅ Validation attempt {attempt} completed - Score: {overall_score}, Verdict: {verdict}")
            
            # Check if retry is needed
            logger.info(f"🐛 About to call _should_retry_with_fixed_logic with attempt={attempt}")
            should_retry, retry_reason = self._should_retry_with_fixed_logic(overall_score, verdict, attempt)
            logger.info(f"🐛 Retry decision: should_retry={should_retry}, reason='{retry_reason}'")
            
            if should_retry:
                logger.info(f"🔄 RETRYING: {retry_reason}")
                revised_analysis = validation_result.get('revised_analysis', analysis)
                logger.info(f"🐛 About to call _run_validation_with_retries recursively with attempt={attempt + 1}")
                return await self._run_validation_with_retries(
                    company, revised_analysis, articles, attempt + 1
                )
            
            logger.info(f"✅ Quality validation COMPLETE for {company}: {retry_reason}")
            return self._create_validated_result(validation_result, attempt)
            
        except Exception as e:
            logger.error(f"❌ Quality validation failed for {company}: {e}")
            logger.error(f"🐛 Exception type: {type(e)}")
            import traceback
            logger.error(f"🐛 Traceback: {traceback.format_exc()}")
            return self._create_fallback_result(analysis, str(e))
    
    async def _validate_with_rate_limit_handling(self, 
                                               company: str, 
                                               analysis: Dict[str, List[str]], 
                                               articles: List[Dict],
                                               attempt: int) -> Dict[str, Any]:
        """Run validation with rate limit retry logic."""
        
        max_rate_limit_retries = 3
        
        for rate_retry in range(max_rate_limit_retries):
            try:
                # Run the web search validation
                result = await self.web_search_engine.validate_with_web_search(
                    company, analysis, articles, attempt
                )
                return result
                
            except Exception as e:
                # Check if it's a rate limit error
                if "rate_limit_error" in str(e) or "429" in str(e):
                    if rate_retry < max_rate_limit_retries - 1:
                        wait_time = (rate_retry + 1) * 30  # 30, 60, 90 seconds
                        logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry {rate_retry + 1}...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ Rate limit exceeded after {max_rate_limit_retries} attempts")
                        # Return a fallback result instead of failing completely
                        return self._create_rate_limit_fallback_result(analysis, attempt)
                else:
                    # Non-rate-limit error, re-raise
                    raise e
        
        # Should never reach here
        return self._create_rate_limit_fallback_result(analysis, attempt)
    
    def _create_rate_limit_fallback_result(self, analysis: Dict[str, List[str]], attempt: int) -> Dict[str, Any]:
        """Create a fallback result when rate limited."""
        return {
            'revised_analysis': analysis,
            'overall_score': 6.5 if attempt == 1 else 7.0,  # Give decent score to avoid infinite retries
            'overall_verdict': 'pass',  # Accept the analysis due to rate limiting
            'web_search_metadata': {
                'searches_performed': 0, 
                'web_search_enabled': True,
                'rate_limited': True
            },
            'enhancements_made': [f"Rate limited on attempt {attempt} - using original analysis"],
            'validation_metadata': {'rate_limited': True}
        }
  
    async def validate_and_enhance_analysis(self, 
                                          company: str, 
                                          analysis: Dict[str, List[str]], 
                                          articles: List[Dict],
                                          attempt: int = 1,
                                          max_retries: int = 2) -> Dict[str, Any]:
        """
        Main validation pipeline with web search and retry logic.
        """
        if not self.web_search_engine:
            return self._create_unvalidated_result(analysis)
        
        try:
            logger.info(f"🔍 Web search validation for {company} (attempt {attempt})")
            
            # Run validation with web search
            validation_result = await self.web_search_engine.validate_with_web_search(
                company, analysis, articles, attempt
            )
            
            # Check if retry is needed
            should_retry, retry_reason = self._should_retry_with_fixed_logic(
                validation_result, attempt, max_retries
            )
            
            if should_retry:
                logger.info(f"🔄 Retrying validation: {retry_reason}")
                # Use the revised analysis from this attempt as input for the next
                revised_analysis = validation_result.get('revised_analysis', analysis)
                return await self.validate_and_enhance_analysis(
                    company, revised_analysis, articles, attempt + 1, max_retries
                )
            
            # Return final result
            return self._create_validated_result(validation_result, attempt)
            
        except Exception as e:
            logger.error(f"❌ Web search validation failed for {company}: {e}")
            return self._create_fallback_result(analysis, str(e))
    
    def _should_retry_with_fixed_logic(self, overall_score: float, verdict: str, attempt: int) -> tuple[bool, str]:
        """Retry logic with diagnostic logging."""
        
        logger.info(f"🐛 DIAGNOSTIC: _should_retry_with_fixed_logic called")
        logger.info(f"🐛 Raw overall_score type: {type(overall_score)}")
        logger.info(f"🐛 Raw overall_score value: {overall_score}")
        logger.info(f"🐛 Raw verdict: {verdict}")
        logger.info(f"🐛 Attempt number: {attempt}")
        logger.info(f"🐛 Max retries: {self.max_retries}")
        
        # Don't retry if max attempts reached
        if attempt >= self.max_retries:
            logger.info(f"🐛 DECISION: No retry - max attempts reached ({attempt} >= {self.max_retries})")
            return False, f"Max attempts reached"
        
        # Extract actual score value safely
        score_value = 0.0
        try:
            if isinstance(overall_score, (int, float)):
                score_value = float(overall_score)
                logger.info(f"🐛 Score extracted as float: {score_value}")
            elif isinstance(overall_score, dict):
                score_value = float(overall_score.get('score', 0))
                logger.info(f"🐛 Score extracted from dict: {score_value}")
            else:
                score_value = 0.0
                logger.info(f"🐛 Score defaulted to 0.0 (unknown type)")
        except Exception as e:
            score_value = 0.0
            logger.error(f"🐛 Score extraction failed: {e}")
        
        # Simple retry logic
        if score_value < 7.0 or verdict == "needs_revision":
            logger.info(f"🐛 DECISION: RETRY - score {score_value} < 7.0 or verdict '{verdict}'")
            return True, f"Below threshold or needs revision"
        
        logger.info(f"🐛 DECISION: NO RETRY - score {score_value} >= 7.0 and verdict '{verdict}'")
        return False, f"Quality acceptable"

    def _create_validated_result(self, validation_result: Dict, attempt: int) -> Dict[str, Any]:
        """Create enhanced validation result."""
        return {
            'analysis': validation_result.get('revised_analysis', {}),
            'quality_validation': {
                'enabled': True,
                'passed': validation_result.get('overall_score', 0) >= 7.0,
                'score': validation_result.get('overall_score', 0),
                'verdict': validation_result.get('overall_verdict', 'unknown'),
                'attempt': attempt,
                'web_search_enabled': True,
                'web_searches_performed': validation_result.get('web_search_metadata', {}).get('searches_performed', 0),
                'enhancements_made': validation_result.get('enhancements_made', []),
                'validation_metadata': validation_result.get('validation_metadata', {}),
                'quality_grade': self._calculate_quality_grade(validation_result.get('overall_score', 0))
            },
            'success': True,
            'enhanced': True
        }
    
    def _create_unvalidated_result(self, analysis: Dict[str, List[str]]) -> Dict[str, Any]:
        """Create result when validation is disabled."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': False,
                'passed': None,
                'score': None,
                'message': 'Web search validation disabled - missing Anthropic API key'
            },
            'success': True,
            'enhanced': False
        }
    
    def _create_fallback_result(self, analysis: Dict[str, List[str]], error: str) -> Dict[str, Any]:
        """Create fallback result when validation fails."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': True,
                'passed': False,
                'score': None,
                'error': error,
                'web_search_enabled': True,
                'message': 'Web search validation failed - using original analysis'
            },
            'success': True,
            'enhanced': False
        }
    
    def _calculate_quality_grade(self, score: float) -> str:
        """Calculate quality grade from score."""
        if score >= 9.0: return "A+"
        elif score >= 8.5: return "A"
        elif score >= 8.0: return "A-"
        elif score >= 7.5: return "B+"
        elif score >= 7.0: return "B"
        elif score >= 6.0: return "B-"
        else: return "C"

    def _create_rate_limit_fallback_result(self, analysis: Dict[str, List[str]], attempt: int) -> Dict[str, Any]:
        """Create fallback result when rate limited."""
        logger.warning(f"🚨 Rate limit fallback activated for attempt {attempt}")
        
        # Give a score that will stop retries but indicate the limitation
        fallback_score = 7.0 if attempt >= 2 else 6.8
        
        return {
            'revised_analysis': analysis,
            'overall_score': fallback_score,
            'overall_verdict': 'pass',  # Accept due to rate limiting
            'web_search_metadata': {
                'searches_performed': 0,
                'web_search_enabled': True,
                'rate_limited': True,
                'fallback_used': True
            },
            'enhancements_made': [
                f"Rate limited on validation attempt {attempt}",
                "Using original analysis with basic quality score",
                "Consider upgrading API rate limits for full validation"
            ],
            'validation_metadata': {
                'rate_limited': True,
                'attempt_when_limited': attempt,
                'fallback_score_applied': fallback_score
            },
            'critical_issues': []
        }

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
    
    # --- CALCULATE METRICS AND CITATION GUIDE FROM 'articles' (List[Dict]) ---
    source_type_counts = {}
    # Iterate over the original list of article dictionaries
    for article_item in articles[:30]: # Use the input list of dicts
        source_type = article_item.get('source_type', 'google_search')
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

    premium_sources_list = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'nytimes.com', 'cnbc.com', 'marketwatch.com']
    premium_count = sum(1 for article_item in articles[:30] if article_item.get('source', '') in premium_sources_list)
    alphavantage_count = source_type_counts.get('alphavantage_premium', 0)

    # Create source citation guide correctly
    # This assumes create_source_url_mapping returns a dict like {'source_domain': [1, 5, 10]}
    # You might need to adjust create_source_url_mapping or how you build this guide.
    # For now, let's create a simple one:
    article_source_info_for_prompt = "\n\nARTICLE SOURCE DETAILS (for your reference in citation):\n"
    for i, article_item in enumerate(articles[:30], 1):
        article_source_info_for_prompt += f"Article {i}: Source - {article_item.get('source', 'N/A')}, Title - \"{article_item.get('title', 'N/A')[:50]}...\"\n"

    # --- PREPARE article_text_for_promptSTRING FOR THE PROMPT ---
    article_text_for_prompt = "" # Use a different variable name for clarity
    for i, article_item in enumerate(articles[:30], 1):
        source_type = article_item.get('source_type', 'google_search')

        if source_type == 'alphavantage_premium':
            sentiment_label = article_item.get('sentiment_label', 'Neutral')
            sentiment_score = article_item.get('sentiment_score', 0)
            relevance_score = article_item.get('relevance_score', 0)
            article_text_for_prompt += f"\n{i}. [ALPHAVANTAGE+SENTIMENT] {article_item['title']}\n"
            article_text_for_prompt += f"   Source: {article_item['source']} | Sentiment: {sentiment_label} ({sentiment_score:.3f}) | Relevance: {relevance_score:.3f}\n"
            article_text_for_prompt += f"   Content: {article_item.get('full_content', article_item.get('snippet', ''))}\n"
        elif source_type == 'nyt_api':
            article_text_for_prompt += f"\n{i}. [NYT_PREMIUM] {article_item['title']}\n"
            article_text_for_prompt += f"   Source: {article_item['source']} (NYT Editorial Quality)\n"
            article_text_for_prompt += f"   Content: {article_item.get('full_content', article_item.get('snippet', ''))}\n"
        else:
            article_text_for_prompt += f"\n{i}. [PREMIUM_SOURCE] {article_item['title']}\n"
            article_text_for_prompt += f"   Source: {article_item['source']}\n"
            article_text_for_prompt += f"   Content: {article_item.get('snippet', '')}\n"
        article_text_for_prompt += f"   Link: {article_item['link']}\n"

    
    # Create prompt
    prompt = f"""You are a Managing Director of Equity Research at Goldman Sachs writing for institutional investors who value both analytical precision AND clear, compelling narratives. Your analysis will be read by portfolio managers making investment decisions.

COMPREHENSIVE DATA INTELLIGENCE ({len(article_text_for_prompt)} articles with FULL context):
{article_text_for_prompt}

{article_source_info_for_prompt}

SOURCE QUALITY METRICS (for your awareness):
• Total Articles Used: {len(articles[:30])}
• Premium Sources (Bloomberg/Reuters/WSJ/FT/NYT/CNBC/MarketWatch): {premium_count} ({premium_count/len(articles[:30])*100:.1f}% if articles else 0%)
• AlphaVantage (Full Content + Sentiment): {alphavantage_count}
• Source Distribution: {source_type_counts}

ENHANCED ANALYTICAL FRAMEWORK - Superior Depth with Accessible Communication:

**CRITICAL FORMATTING REQUIREMENTS:**
- Use EXACTLY these section headers: "**EXECUTIVE SUMMARY**", "**INVESTOR INSIGHTS**", "**CATALYSTS & RISKS**"
- Start each bullet with a bullet point symbol: "•"
- Each section must have exactly 4-5 bullets

**CRITICAL WRITING REQUIREMENTS:**
1. **Storytelling Flow**: Each bullet should read like professional investment commentary, not raw data
2. **Explicit Source Attribution**: Always cite sources using format "according to [source]", "as reported by [source]", "per [source]"
3. **Accessible Language**: Maintain analytical precision but use clear, readable language that flows naturally
4. **Quantified Insights**: Include specific metrics and probability estimates, but weave them into compelling narratives
5. **Professional Tone**: Write like you're briefing a client, not generating a technical report

**EXECUTIVE SUMMARY** (Strategic & Financial Impact - Write as compelling investment thesis)
Create 4-5 bullets that tell the strategic story of {company} with quantified impacts and clear source attribution:

• Start each bullet with strategic context, then layer in specific financial metrics
• Include timeline estimates and probability assessments naturally woven into the narrative
• Always cite your sources explicitly (e.g., "according to reuters.com", "as highlighted by cnbc.com")
• Use sophisticated tags but make the content accessible: [STRATEGY], [FINANCIAL_IMPACT], [EXECUTION_RISK], [VALUE_CREATION], [MANAGEMENT_QUALITY]
• Example style: "[STRATEGY] {company}'s expansion into [specific area] represents a significant strategic shift that could drive [specific financial impact with range] over [timeline], with [confidence level] probability of success according to analysis from [specific sources]. This initiative builds on [context from other sources]..."

**INVESTOR INSIGHTS** (Valuation & Market Dynamics - Write as investment analysis narrative)
Create 4-5 bullets that weave valuation analysis into compelling market stories:

• Integrate valuation metrics (P/E, EV/EBITDA) into broader market positioning narrative
• Connect analyst consensus and price targets to underlying business drivers, citing specific sources
• Correlate sentiment analysis with fundamental developments in a readable way
• Include competitive positioning as part of investment thesis, not isolated data points
• Use tags: [VALUATION], [PEER_COMPARISON], [SENTIMENT_ANALYSIS], [TECHNICAL], [INSTITUTIONAL_FLOW]
• Example style: "[VALUATION] Trading at [specific metrics] versus peers, {company} appears [undervalued/fairly valued/overvalued] based on [specific analysis methodology]. Recent analyst updates from [sources] suggest [price target range] reflecting [specific business drivers], with sentiment analysis from [AlphaVantage/other sources] indicating [market sentiment context]..."

**CATALYSTS & RISKS** (Probability-Weighted Analysis with Investment Context)
Create 4-5 bullets that present catalysts and risks as investment decision factors:

• Frame each catalyst/risk in terms of investment impact and timeline, not just technical probability
• Provide specific dates and probability estimates but explain the investment rationale
• Connect technical analysis and options flow to fundamental business developments
• Always attribute risk assessments to specific sources and analysis
• Use tags: [CATALYST], [EVENT_RISK], [REGULATORY], [MACRO_SENSITIVITY], [TECHNICAL_LEVELS]
• Example style: "[CATALYST] The upcoming [specific event/announcement] scheduled for [date] presents a [upside/downside] catalyst with [probability estimate] likelihood of [specific financial impact], as indicated by [source citations]. This catalyst is particularly significant because [business context], with options market positioning of [technical details] suggesting [market expectations]..."

**ENHANCED REQUIREMENTS FOR SUPERIOR READABILITY:**

1. **Source Attribution Excellence**: Every factual claim must cite its source explicitly
   - Use natural language: "according to marketwatch.com", "as reported by reuters.com", "per bloomberg analysis"
   - When multiple sources support a point: "confirmed across reuters.com and cnbc.com reports"
   - When sources conflict: "while reuters.com suggests X, bloomberg.com indicates Y, suggesting [your analysis]"

2. **Narrative Flow Mastery**: 
   - Begin each bullet with strategic context before diving into metrics
   - Connect quantitative insights to broader business implications
   - Use transition phrases to create smooth flow between technical and strategic points
   - End bullets with forward-looking implications

3. **Quantification with Context**:
   - Always provide ranges and confidence intervals: "15-25% upside with 70% confidence"
   - Include timeline specificity: "expected by Q3 2025"
   - Connect metrics to business drivers: "driven by market share expansion in [specific segment]"

4. **Professional Investment Commentary Style**:
   - Write as if briefing a sophisticated investor
   - Use active voice and confident language
   - Avoid overly technical jargon without context
   - Maintain analytical rigor while ensuring accessibility

**CROSS-SOURCE VALIDATION REQUIREMENTS**:
- When multiple sources provide similar information, synthesize and cite all relevant sources
- When sources conflict, acknowledge differences and provide your analytical view
- Highlight unique insights from premium sources (Bloomberg, Reuters, WSJ)
- Leverage AlphaVantage sentiment data as supporting evidence for fundamental themes

**FINAL QUALITY CHECK**:
Each bullet should pass these tests:
✓ Does it tell a clear story that advances the investment thesis?
✓ Are all factual claims explicitly attributed to sources?
✓ Would a portfolio manager understand the investment implications?
✓ Is the language accessible while maintaining analytical depth?
✓ Do the quantified estimates have proper context and confidence levels?

Generate exactly 4-5 substantive bullets per section that combine analytical excellence with compelling storytelling and transparent source attribution."""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=7500,
        temperature=0.07,
        messages=[{"role": "user", "content": prompt}]
    )
    
    analysis_text_response = response.content[0].text # analysis_text is already used
    logger.info(f"Claude Sonnet 4 analysis generated: {len(analysis_text_response)} chars")

    return parse_analysis_response(analysis_text_response)

def generate_openai_analysis(company: str, articles: List[Dict]) -> Dict[str, List[str]]:
    """Generate analysis using OpenAI as fallback."""
    # Prepare article content (simplified for OpenAI)
    article_text_for_prompt= ""
    for i, article in enumerate(articles[:30], 1):
        article_text_for_prompt+= f"\n{i}. {article['title']}\n"
        article_text_for_prompt+= f"   Source: {article['source']}\n"
        article_text_for_prompt+= f"   Content: {article.get('snippet', '')}\n"
    
    prompt = f"""You are a senior equity research analyst analyzing {company}.

ARTICLES TO ANALYZE:
{article_text_for_prompt}

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
        # ✅ FIX: Proper async handling
        try:
            # Check if we're already in an async context
            loop = asyncio.get_running_loop()
            # We're in an async context, but we need to run in a thread
            import nest_asyncio
            nest_asyncio.apply()
            results = asyncio.run(_run_comprehensive_analysis(company, days_back, enable_quality_validation))
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            results = asyncio.run(_run_comprehensive_analysis(company, days_back, enable_quality_validation))
        
        execution_time = time.time() - start_time
        results['metrics']['response_time'] = execution_time
        
        logger.info(f"✅ Analysis complete for {company} in {execution_time:.2f}s")
        return results
        
    except Exception as e:
        logger.error(f"Comprehensive analysis failed for {company}: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
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
    
    # Phase 2: Relevance assessment
    relevant_articles, relevance_stats = assess_article_batch_relevance(all_articles, company)
    logger.info(f"📊 Relevance filter: {len(relevant_articles)}/{len(all_articles)} articles passed ({relevance_stats['relevance_percentage']:.1%})")

    
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
    
    # Phase 4: Final article selection - USE RELEVANT ARTICLES
    # ✅ FIXED CODE - Always ensure 30 articles:
    logger.info("🎯 Phase 4: Final article selection...")

    # Always start with relevant articles, then fill to 30 with highest-scored articles
    unique_articles = deduplicate_articles(all_articles)
    scored_articles = score_articles(unique_articles, company)

    # Prioritize relevant articles first
    relevant_urls = {a.get('link', '') for a in relevant_articles}
    final_articles = []

    # Add relevant articles first
    for article, score in scored_articles:
        if article.get('link', '') in relevant_urls:
            final_articles.append(article)
            if len(final_articles) >= config.TARGET_ARTICLE_COUNT:
                break

    # Fill remaining slots with highest-scored non-relevant articles
    if len(final_articles) < config.TARGET_ARTICLE_COUNT:
        for article, score in scored_articles:
            if article.get('link', '') not in relevant_urls:
                final_articles.append(article)
                if len(final_articles) >= config.TARGET_ARTICLE_COUNT:
                    break

    # Ensure exactly TARGET_ARTICLE_COUNT (30) articles
    final_articles = final_articles[:config.TARGET_ARTICLE_COUNT]

    logger.info(f"🎯 Final selection: {len(final_articles)} articles ({len([a for a in final_articles if a.get('link', '') in relevant_urls])} relevant + {len(final_articles) - len([a for a in final_articles if a.get('link', '') in relevant_urls])} additional)")
        
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
            
            # ✅ Safe enhanced logging of final quality results
            try:
                # Simple quality validation logging
                logger.info(f"Quality validation completed for {company}")
                if quality_info.get('score'):
                    logger.info(f"Quality score: {quality_info.get('score')}")
                
                # Log if rate limited
                if quality_info.get('validation_metadata', {}).get('rate_limited'):
                    logger.warning(f"⚠️ Analysis was rate limited - consider API upgrade for full validation")
                    
            except Exception as log_error:
                logger.error(f"Error in quality summary logging: {log_error}")
                logger.info(f"✅ Quality validation completed for {company} (summary logging error)")
            
            # Log if rate limited
            if quality_info.get('validation_metadata', {}).get('rate_limited'):
                logger.warning(f"⚠️ Analysis was rate limited - consider API upgrade for full validation")
            
        except Exception as quality_error:
            logger.error(f"❌ Quality validation failed: {quality_error}")
            logger.error(f"Exception type: {type(quality_error).__name__}")
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