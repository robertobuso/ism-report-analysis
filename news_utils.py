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

from typing import Dict, List, Tuple, Optional, Any, TypedDict

class UICitation(TypedDict, total=False):
    # From Anthropic citation object:
    document_index: int
    type: str
    document_title: Optional[str]
    cited_text: Optional[str]
    start_char_index: Optional[int]
    end_char_index: Optional[int]
    start_page_number: Optional[int]
    end_page_number: Optional[int]
    start_block_index: Optional[int]
    end_block_index: Optional[int]
    # Enriched with our article metadata (from article_index_map):
    url: Optional[str]
    source: Optional[str]
    title: Optional[str]
    source_type: Optional[str]

class UIBullet(TypedDict):
    text: str
    text_block_index: int             # which Claude text block this bullet came from
    citations: list[UICitation]       # zero or more normalized citations

UISections = dict[str, list[UIBullet]]  # keys: 'executive' | 'investor' | 'catalysts'

def _normalize_citation(cit, article_index_map) -> UICitation:
    # Anthropic SDK objects can be attr- or dict-like; use getattr with fallback
    def g(obj, name, default=None):
        return getattr(obj, name, obj.get(name, default)) if isinstance(obj, dict) else getattr(obj, name, default)

    doc_index = g(cit, "document_index")
    ui: UICitation = {
        "document_index": doc_index,
        "type": g(cit, "type"),
        "document_title": g(cit, "document_title"),
        "cited_text": g(cit, "cited_text"),
        "start_char_index": g(cit, "start_char_index"),
        "end_char_index": g(cit, "end_char_index"),
        "start_page_number": g(cit, "start_page_number"),
        "end_page_number": g(cit, "end_page_number"),
        "start_block_index": g(cit, "start_block_index"),
        "end_block_index": g(cit, "end_block_index"),
    }

    # Enrich with our article metadata
    if doc_index in article_index_map:
        meta = article_index_map[doc_index]
        ui.update({
            "url": meta.get("url"),
            "source": meta.get("source"),
            "title": meta.get("title"),
            "source_type": meta.get("source_type"),
        })
    return ui

def _mk(obj_or_str) -> UIBullet:
    # convenience for single-string fallbacks
    return {"text": obj_or_str, "text_block_index": -1, "citations": []}

def legacy_to_ui(sections_legacy: dict[str, list[str]]) -> UISections:
    """Convert legacy string format to UI format."""
    return {k: [{"text": t, "text_block_index": -1, "citations": []} for t in v]
            for k, v in (sections_legacy or {}).items()}

def ui_to_legacy(sections_ui: UISections) -> dict[str, list[str]]:
    """Convert UI format to legacy string format."""
    return {k: [b["text"] for b in (sections_ui.get(k) or [])] for k in ["executive","investor","catalysts"]}

def as_legacy_string_sections(sections: UISections) -> dict[str, list[str]]:
    """Compatibility adapter for old callers expecting string sections."""
    return {k: [b["text"] for b in v] for k, v in sections.items()}

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
    PARALLEL_TIMEOUT: int = 360
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
        self.api_key = api_key  # ✅ Store API key instead of client
        self.client = anthropic.Anthropic(
            api_key=self.api_key,
            default_headers={"anthropic-beta": "token-efficient-tools-2025-02-19"}
        )
    
    def _create_fresh_client(self):
        """Create a fresh Anthropic client to reset conversation context."""
        return anthropic.Anthropic(api_key=self.api_key)
    
    def _prepare_articles_for_validation_ADAPTIVE(self, articles: List[Dict], company: str) -> List[Dict]:
            """Adaptive article preparation - smart token allocation."""
            
            # Separate by relevance
            relevant_articles = []
            other_articles = []
            
            for article in articles:
                relevance = article.get('relevance_assessment', {})
                if relevance.get('is_company_specific', False) or relevance.get('overall_relevance', 0) > 0.5:
                    relevant_articles.append(article)
                else:
                    other_articles.append(article)
            
            prepared_articles = []
            total_estimated_tokens = 0
            
            # Include relevant articles with more detail (up to 12)
            for article in relevant_articles[:12]:
                if total_estimated_tokens > 10000:  # Token budget check
                    break
                    
                prepared_article = {
                    'title': article.get('title', ''),
                    'snippet': article.get('snippet', '')[:400],  # Longer for relevant
                    'source': article.get('source', ''),
                    'source_type': article.get('source_type', 'google_search'),
                    'relevance_level': 'high'
                }
                
                # Include AlphaVantage sentiment data
                if article.get('source_type') == 'alphavantage_premium':
                    prepared_article['sentiment_label'] = article.get('sentiment_label')
                    prepared_article['relevance_score'] = article.get('relevance_score')
                
                prepared_articles.append(prepared_article)
                total_estimated_tokens += 200  # Rough estimate per article
            
            # Fill remaining budget with other articles (shorter content)
            for article in other_articles:
                if len(prepared_articles) >= 18 or total_estimated_tokens > 12000:
                    break
                    
                prepared_article = {
                    'title': article.get('title', '')[:80],
                    'snippet': article.get('snippet', '')[:120],  # Shorter for non-relevant
                    'source': article.get('source', ''),
                    'source_type': article.get('source_type', 'google_search'),
                    'relevance_level': 'standard'
                }
                
                prepared_articles.append(prepared_article)
                total_estimated_tokens += 100
            
            logger.info(f"🎯 Adaptive validation: {len(prepared_articles)} articles (~{total_estimated_tokens} tokens)")
            logger.info(f"   • {len([a for a in prepared_articles if a.get('relevance_level') == 'high'])} high-relevance with detailed content")
            logger.info(f"   • {len([a for a in prepared_articles if a.get('relevance_level') == 'standard'])} standard articles with basic content")
            
            return prepared_articles

    # 1. WEB SEARCH TOOL DEFINITION - Could be massive
    def debug_web_search_tool_tokens():
        """Check if the web search tool definition is huge."""
        
        # The tool definition we're sending
        tool_definition = {
            "type": "web_search_20250305",
            "name": "web_search", 
            "max_uses": 10
            # ❓ Are there hidden fields here?
        }
        
        # ✅ ADD: Log the FULL tool definition
        import json
        tool_json = json.dumps(tool_definition, indent=2)
        logger.info(f"🔧 FULL TOOL DEFINITION:")
        logger.info(f"   JSON: {tool_json}")
        logger.info(f"   Size: {len(tool_json):,} characters")
        logger.info(f"   Estimated tokens: {len(tool_json)//4:,}")

    # 2. ARTICLES NOT ACTUALLY TRUNCATED
    def debug_actual_articles_sent(articles):
        """Check if articles are actually truncated or still full size."""
        
        total_article_chars = 0
        logger.info(f"🔍 ARTICLE DEBUG - Checking actual article sizes:")
        
        for i, article in enumerate(articles):
            title_size = len(article.get('title', ''))
            snippet_size = len(article.get('snippet', ''))
            full_content_size = len(article.get('full_content', ''))
            
            total_chars = title_size + snippet_size + full_content_size
            total_article_chars += total_chars
            
            logger.info(f"   Article {i+1}: {total_chars:,} chars (title:{title_size}, snippet:{snippet_size}, full:{full_content_size})")
            
            # ❓ Are we accidentally sending full_content instead of snippet?
            if full_content_size > 1000:
                logger.warning(f"   ⚠️ Article {i+1} has large full_content: {full_content_size:,} chars")
        
        logger.info(f"📊 TOTAL ARTICLE CONTENT: {total_article_chars:,} characters ({total_article_chars//4:,} tokens)")

    # 3. PROMPT TEMPLATE ISSUES
    def debug_prompt_template_hidden_content(prompt):
        """Check for hidden content in prompt template."""
        
        # Check for repeated content
        lines = prompt.split('\n')
        line_lengths = [len(line) for line in lines]
        
        logger.info(f"📄 PROMPT LINE ANALYSIS:")
        logger.info(f"   Total lines: {len(lines):,}")
        logger.info(f"   Average line length: {sum(line_lengths)/len(line_lengths):.1f} chars")
        logger.info(f"   Longest line: {max(line_lengths):,} chars")
        
        # Look for suspiciously long lines
        for i, line in enumerate(lines):
            if len(line) > 1000:
                logger.warning(f"   ⚠️ Line {i+1}: {len(line):,} chars - {line[:100]}...")
        
        # Check for repeated sections
        import collections
        line_counts = collections.Counter(lines)
        for line, count in line_counts.most_common(5):
            if count > 1 and len(line) > 100:
                logger.warning(f"   🔄 REPEATED: '{line[:50]}...' appears {count} times ({len(line)*count:,} chars)")

    # 4. SYSTEM PROMPT OR HIDDEN CONTEXT
    def debug_system_context():
        """Check for hidden system prompts or context."""
        
        logger.info(f"🔍 CHECKING FOR HIDDEN CONTEXT:")
        
        # ❓ Is there a system prompt we're not seeing?
        # ❓ Is the web search tool adding context automatically?
        # ❓ Are there hidden instructions in the tool?
        
        logger.warning(f"   Possible sources of 214,550 hidden tokens:")
        logger.warning(f"   1. Web search tool has massive hidden documentation")
        logger.warning(f"   2. System prompt is being added automatically") 
        logger.warning(f"   3. Articles contain full_content instead of snippets")
        logger.warning(f"   4. Prompt template has hidden repeated content")
        logger.warning(f"   5. Anthropic API is adding context we don't see")

    # 5. UPDATED DEBUG LOGGING TO FIND THE CULPRIT
    def _debug_log_prompt_details(self, prompt: str, attempt: int, company: str):
        """Log comprehensive prompt details for debugging - CLEAN VERSION."""
        
        # Basic metrics
        char_count = len(prompt)
        estimated_tokens = char_count // 4  # Rough estimation
        line_count = prompt.count('\n')
        word_count = len(prompt.split())
        
        logger.info(f"🔍 PROMPT DEBUG - Attempt {attempt} for {company}")
        logger.info(f"   📏 Characters: {char_count:,}")
        logger.info(f"   🔢 Estimated tokens: {estimated_tokens:,}")
        logger.info(f"   📄 Lines: {line_count:,}")
        logger.info(f"   📝 Words: {word_count:,}")
        
        # ✅ CRITICAL: Look for article content in the prompt
        if 'ARTICLE CONTEXT' in prompt:
            article_start = prompt.find('ARTICLE CONTEXT')
            article_end = prompt.find('VALIDATION TASK', article_start)
            if article_end == -1:
                article_end = len(prompt)
            
            article_section = prompt[article_start:article_end]
            article_tokens = len(article_section) // 4
            article_lines = article_section.count('\n')
            
            logger.info(f"📰 ARTICLE SECTION FOUND:")
            logger.info(f"   📊 Article section: {article_tokens:,} tokens ({len(article_section):,} chars)")
            logger.info(f"   📄 Article lines: {article_lines:,}")
            
            # Count numbered articles
            article_numbers = []
            for i in range(1, 31):  # Check for articles 1-30
                if f"{i}. " in article_section:
                    article_numbers.append(i)
            
            logger.info(f"   🔢 Articles found: {len(article_numbers)} ({article_numbers[:10]}...)")
            
            # Check for very long lines (indicates full content)
            long_lines = 0
            for line in article_section.split('\n'):
                if len(line) > 500:
                    long_lines += 1
            
            if long_lines > 0:
                logger.warning(f"   ⚠️ {long_lines} very long lines detected (>500 chars) - may contain full article content!")
        
        else:
            logger.info(f"📰 No 'ARTICLE CONTEXT' section found in prompt")
        
        # ✅ Check for repeated content
        lines = prompt.split('\n')
        unique_lines = set(lines)
        if len(lines) != len(unique_lines):
            duplicates = len(lines) - len(unique_lines)
            logger.warning(f"🔄 {duplicates} duplicate lines found - may indicate repeated content")
        
        # ✅ Look for suspicious patterns
        if prompt.count('full_content') > 5:
            logger.warning(f"⚠️ 'full_content' mentioned {prompt.count('full_content')} times - may be sending full article text")
        
        # ✅ SAVE FULL PROMPT TO FILE
        try:
            import os
            os.makedirs("debug_logs", exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_logs/validation_prompt_{company}_{attempt}_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"=== VALIDATION PROMPT DEBUG ===\n")
                f.write(f"Company: {company}\n")
                f.write(f"Attempt: {attempt}\n")
                f.write(f"Timestamp: {datetime.now()}\n")
                f.write(f"Characters: {char_count:,}\n")
                f.write(f"Estimated tokens: {estimated_tokens:,}\n")
                f.write(f"Lines: {line_count:,}\n")
                f.write(f"Words: {word_count:,}\n")
                f.write(f"="*50 + "\n\n")
                f.write(prompt)
            
            logger.info(f"💾 Full prompt saved to: {filename}")
            
            # ✅ Also save a summary file
            summary_filename = f"debug_logs/prompt_summary_{company}_{attempt}_{timestamp}.txt"
            with open(summary_filename, 'w', encoding='utf-8') as f:
                f.write(f"PROMPT ANALYSIS SUMMARY\n")
                f.write(f"======================\n")
                f.write(f"Characters: {char_count:,}\n")
                f.write(f"Estimated tokens: {estimated_tokens:,}\n")
                f.write(f"Lines: {line_count:,}\n")
                f.write(f"Unique lines: {len(unique_lines):,}\n")
                f.write(f"Duplicate lines: {len(lines) - len(unique_lines):,}\n")
                
                if 'ARTICLE CONTEXT' in prompt:
                    f.write(f"Article section found: YES\n")
                    f.write(f"Article section tokens: {article_tokens:,}\n")
                    f.write(f"Articles detected: {len(article_numbers)}\n")
                else:
                    f.write(f"Article section found: NO\n")
            
            logger.info(f"📋 Summary saved to: {summary_filename}")
            
        except Exception as e:
            logger.warning(f"Could not save prompt debug files: {e}")

    def count_actual_tokens(text: str) -> int:
        """More accurate token counting using Anthropic's estimation."""
        try:
            # Use Anthropic's token counting if available
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            
            response = client.messages.count_tokens(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": text}]
            )
            
            return response.input_tokens
            
        except Exception as e:
            logger.warning(f"Could not get accurate token count: {e}")
            # Fallback to estimation
            return len(text) // 4

    def _create_web_search_validation_prompt(self, 
                                       company: str, 
                                       analysis: Dict[str, List[str]], 
                                       articles: List[Dict],
                                       attempt: int) -> str:
        """Create validation prompt that scores BOTH original and revised analysis."""
        
        formatted_analysis = self._format_analysis_for_review(analysis)
        today_str = datetime.now().strftime("%B %d, %Y")

        # Create article summaries (existing code)
        article_summaries = ""
        for i, article in enumerate(articles, 1):
            title = article.get('title', '')
            snippet = article.get('snippet', '')
            source = article.get('source', '')
            source_type = article.get('source_type', 'google_search')
            relevance_level = article.get('relevance_level', 'standard')
            
            # Format based on source type and relevance
            if source_type == 'alphavantage_premium':
                sentiment = article.get('sentiment_label', 'Neutral')
                relevance = article.get('relevance_score', 0)
                article_summaries += f"{i}. [AV+SENTIMENT] {title}\n   {source} | {sentiment} | Rel:{relevance:.2f}\n   {snippet}\n\n"
            elif source_type == 'nyt_api':
                article_summaries += f"{i}. [NYT-{relevance_level.upper()}] {title}\n   {source}\n   {snippet}\n\n"
            else:
                article_summaries += f"{i}. [PREMIUM-{relevance_level.upper()}] {title}\n   {source}\n   {snippet}\n\n"
        
        return f"""You are a Managing Director at Goldman Sachs conducting a BEFORE/AFTER quality assessment with REAL-TIME WEB SEARCH capabilities.

    **CRITICAL CITATION REQUIREMENT**: 
    When providing revised analysis, EVERY bullet must end with [Sources: X,Y,Z] format using article numbers 1-{len(articles)} ONLY.

    **CRITICAL INSTRUCTIONS**: 
    1. First score the ORIGINAL analysis as-is (baseline)
    2. Use web search to find current data and create improvements  
    3. Score the REVISED analysis after improvements
    4. Show the improvement delta

    COMPANY: {company}
    TODAY'S DATE: {today_str}

    ORIGINAL ANALYSIS TO ASSESS:
    {formatted_analysis}

    **REVISED ANALYSIS OUTPUT REQUIREMENTS**:
    - Use EXACT format: [Sources: X,Y,Z] where X,Y,Z are numbers 1-{len(articles)}
    - Every bullet must end with [Sources: X,Y,Z]
    - DO NOT use <cite>, "index=", or any other citation format
    - Example: "Revenue increased 15% [Sources: 1,5,8]"

    **MANDATORY DUAL ASSESSMENT PROCESS**:

    **STEP 1: BASELINE SCORING** (Score the original analysis 0-10):
    - Fact accuracy with available data
    - Market context completeness  
    - Investment actionability
    - Timeliness of information
    - Professional quality

    **STEP 2: WEB SEARCH ENHANCEMENT**:
    1. Search for {company} current stock price and trading data
    2. Verify recent earnings, revenue, and financial metrics
    3. Check latest analyst price targets and ratings  
    4. Confirm recent news developments and business updates
    5. Validate any numerical claims with current market data

    **STEP 3: REVISED SCORING** (Score the enhanced analysis 0-10):
    - Same criteria as baseline but with web search enhancements

    **OUTPUT FORMAT**:
    Return JSON with this exact structure:

    ```json
    {{
    "baseline_assessment": {{
        "original_score": float,
        "original_verdict": "pass" | "needs_revision" | "fail",
        "original_issues": ["list of issues found in original"],
        "baseline_summary": "2-3 sentence assessment of original quality"
    }},
    "web_searches_performed": [
        {{
        "query": "search query used",
        "key_finding": "important discovery",
        "data_updated": "specific metric updated",
        "improvement_type": "fact_correction" | "data_refresh" | "context_addition"
        }}
    ],
    "revised_assessment": {{
        "revised_score": float,
        "revised_verdict": "pass" | "needs_revision" | "fail", 
        "improvements_made": ["specific improvements from web search"],
        "remaining_issues": ["issues still present after revision"]
    }},
    "improvement_analysis": {{
        "score_delta": float,
        "improvement_percentage": float,
        "quality_trajectory": "significant_improvement" | "moderate_improvement" | "minimal_improvement" | "no_improvement" | "degradation",
        "web_search_effectiveness": "high" | "medium" | "low"
    }},
    "revised_analysis": {{
        "executive": ["Enhanced bullets with current web-verified data"],
        "investor": ["Updated valuation analysis with recent metrics"],
        "catalysts": ["Current catalyst assessment with verified timelines"]
    }},
    "validation_metadata": {{
        "current_stock_price": "verified price",
        "market_cap": "current market cap", 
        "recent_news_count": int,
        "data_verification_count": int,
        "baseline_date_issues": int,
        "revised_date_freshness": "current" | "recent" | "stale"
    }}
    }}
    ```

    **SCORING CRITERIA FOR BOTH ASSESSMENTS**:
    - 9.0-10.0: Institutional excellence with current data and actionable insights
    - 8.0-8.9: Professional quality with good context and recent information  
    - 7.0-7.9: Acceptable quality with some current data and clear insights
    - 6.0-6.9: Below standard with outdated info or vague recommendations
    - 5.0-5.9: Poor quality with significant factual or timeliness issues
    - 0.0-4.9: Unacceptable quality requiring major revision

    Focus on IMPROVEMENT MEASUREMENT - show how web search enhanced the analysis quality."""

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
                timeout=360.0
            )
            return response
            
        except Exception as e:
            logger.error(f"Claude web search API call failed: {e}")
            raise

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

    def _format_analysis_for_review(self, analysis: UISections) -> str:
        """
        Format analysis for Claude review, embedding original citation data
        directly into the text for the model to see and preserve.
        """
        formatted = ""
        section_headers = {
            'executive': '**EXECUTIVE SUMMARY**',
            'investor': '**INVESTOR INSIGHTS**',
            'catalysts': '**CATALYSTS & RISKS**'
        }

        for section_key, ui_bullets in analysis.items():
            header = section_headers.get(section_key, f'**{section_key.upper()}**')
            formatted += f"{header}\n"
            
            for i, bullet_data in enumerate(ui_bullets, 1):
                text = bullet_data.get("text", "")
                citations = bullet_data.get("citations", [])
                
                # Extract unique document indices from the original citations
                if citations:
                    doc_indices = sorted(list(set(
                        c['document_index'] for c in citations if 'document_index' in c
                    )))
                    
                    # Create a clear marker for the model to understand
                    if doc_indices:
                        citation_marker = f" [Original Sources: {','.join(map(str, doc_indices))}]"
                        formatted += f"{i}. {text}{citation_marker}\n"
                    else:
                        formatted += f"{i}. {text}\n"
                else:
                    formatted += f"{i}. {text}\n"
            
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

    async def chat_with_web_search(self, question: str, context: str, company: str, 
                                conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Handle chat questions with web search capabilities and conversation history."""
        try:
            # Build conversation context from history
            conversation_context = ""
            if conversation_history:
                # Include last 4 exchanges to maintain context but control token usage
                recent_history = conversation_history[-8:]  # Last 4 Q&A pairs
                for i, msg in enumerate(recent_history):
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if role == 'user':
                        conversation_context += f"\nPrevious Question {(i//2)+1}: {content}"
                    elif role == 'assistant':
                        # Truncate previous answers to save tokens
                        truncated_content = content[:200] + "..." if len(content) > 200 else content
                        conversation_context += f"\nPrevious Answer {(i//2)+1}: {truncated_content}"
            
            # Create enhanced chat prompt with conversation history
            chat_prompt = f"""You are a financial analysis assistant with real-time web search capabilities.

    CRITICAL: When the user asks about current data, recent developments, or anything that might have changed recently, use web search to find the latest information about {company}.

    COMPANY ANALYSIS CONTEXT:
    {context}

    {conversation_context}

    CURRENT USER QUESTION: {question}

    Instructions:
    1. Consider the conversation history to understand context and follow-up questions
    2. Use the existing analysis context to answer when sufficient
    3. When recent/current data is needed, use web search to find latest information about {company}
    4. For follow-up questions, build upon previous answers while providing new insights
    5. Combine analysis context with any new web search findings
    6. Provide a comprehensive answer citing both existing analysis and new findings

    Focus on being helpful and thorough. Use web search when needed to provide current information."""

            # Call Claude with web search enabled (rest of method unchanged)
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=1200,  # Increased for more detailed responses
                        temperature=0.2,
                        messages=[{"role": "user", "content": chat_prompt}],
                        tools=[{
                            "type": "web_search_20250305", 
                            "name": "web_search",
                            "max_uses": 5
                        }]
                    )
                ),
                timeout=60.0  # Increased timeout for web search
            )
            
            # Extract response text (unchanged)
            answer_text = ""
            if hasattr(response, 'content') and isinstance(response.content, list):
                for content_block in response.content:
                    if hasattr(content_block, 'type') and content_block.type == "text":
                        answer_text += content_block.text
            
            return {
                'answer': answer_text.strip(),
                'web_search_used': True,
                'citations': []
            }
            
        except Exception as e:
            logger.error(f"Chat with web search failed: {e}")
            raise e
        
    async def annotate_analysis(self, company: str, analysis: UISections, articles: List[Dict]) -> Dict:
        """
        New validation entry point. Performs an annotation task to add citations
        to the original analysis without rewriting it.
        """
        logger.info(f"🔍 Starting V4 ANNOTATION validation for {company}")
        try:
            message_content, article_index_map = self._create_annotation_prompt(company, analysis, articles)
            response = await self._call_claude_for_annotation(message_content)
            return self._parse_annotation_response(response, analysis, article_index_map)
        except Exception as e:
            logger.error(f"❌ V4 Annotation validation failed for {company}: {e}", exc_info=True)
            return {'validation_passed': False, 'annotated_analysis': analysis, 'error': str(e)}

    def _create_annotation_prompt(self, company: str, analysis: UISections, articles: List[Dict]) -> Tuple[List, Dict]:
        """Final V5: A forceful, unambiguous prompt with a self-correction clause."""
        
        document_blocks, article_index_map = [], {}
        for i, article in enumerate(articles[:30]):
            content = f"Title: {article.get('title', '')}\nSnippet: {article.get('snippet', '')}\nSource: {article.get('source', '')}"
            article_index_map[i] = {
                'url': article.get('link', '#'), 
                'source': article.get('source', 'Unknown'), 
                'title': article.get('title', 'Unknown')
            }
            document_blocks.append({
                "type": "document", 
                "source": {"type": "text", "media_type": "text/plain", "data": content},
                "citations": {"enabled": True}, 
                "title": f"Doc {i}: {article.get('source', 'N/A')}"
            })

        analysis_for_prompt = []
        bullet_counter = 0
        for section in ["executive", "investor", "catalysts"]:
            for bullet_data in analysis.get(section, []):
                clean_text = bullet_data['text'].replace('"', "'") # Use single quotes for safety
                analysis_for_prompt.append(f"  {{\"bullet_id\": {bullet_counter}, \"text\": \"{clean_text}\"}}")
                bullet_counter += 1
        analysis_json_string = "[\n" + ",\n".join(analysis_for_prompt) + "\n]"

        annotation_prompt = f"""You are a citation bot. Your only function is to add citations. You will be penalized for failing to add citations.

**PRIMARY DIRECTIVE:**
Your task is to read each bullet point in the `ANALYSIS_BULLETS` JSON array. For each bullet, you MUST find supporting evidence in the provided source documents and use the Citations API to add a citation.

**MANDATORY SELF-CORRECTION AND FAILURE CONDITION:**
- Before you output your final JSON, review your work.
- IF ANY BULLET IN YOUR `cited_bullets` ARRAY LACKS A CITATION, IT IS A TASK FAILURE.
- You MUST find a relevant source for EVERY bullet. If a source is only tangentially related, use it. An imperfect citation is infinitely better than no citation. A bullet without a citation is an error.

**BULLETS TO CITE:**
```json
{analysis_json_string}
OUTPUT FORMAT:
Return ONLY a single, valid JSON object. Do not include any other text, apologies, or explanations.
code
JSON
{{
  "cited_bullets": [
    {{
      "bullet_id": 0,
      "cited_text": "The text from bullet 0, now with citations attached via the API."
    }},
    {{
      "bullet_id": 1,
      "cited_text": "The text from bullet 1, also with citations attached via the API."
    }}
  ]
}}
```"""
        
        message_content = document_blocks + [{"type": "text", "text": annotation_prompt}]
        return message_content, article_index_map

    async def _call_claude_for_annotation(self, message_content: List) -> Any:
        logger.info("🌐 Calling Claude for V4 annotation task...")
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: self.client.messages.create(
                model="claude-sonnet-4-20250514", max_tokens=4000, temperature=0.0,
                messages=[{"role": "user", "content": message_content}]
            )), timeout=120.0
        )

    def _parse_annotation_response(self, response, original_analysis: UISections, article_index_map: Dict) -> Dict:
        raw_text_content = ""
        citations_by_text_block_index = {}
        for i, block in enumerate(response.content):
            if block.type == 'text':
                raw_text_content += block.text
                if hasattr(block, 'citations') and block.citations:
                    citations_by_text_block_index[i] = block.citations

        try:
            json_start = raw_text_content.find('{')
            json_end = raw_text_content.rfind('}') + 1
            result = json.loads(raw_text_content[json_start:json_end])
            annotated_bullets = result.get("cited_bullets", [])
        except Exception:
            logger.error("❌ Could not parse JSON from annotation response. Reverting.")
            return {'validation_passed': False, 'annotated_analysis': original_analysis, 'error': 'JSON parse error'}

        citations_by_id = {}
        for bullet_info in annotated_bullets:
            bullet_id = bullet_info.get("bullet_id")
            bullet_text = bullet_info.get("cited_text")
            for block_index, raw_citations in citations_by_text_block_index.items():
                if bullet_text and bullet_text in response.content[block_index].text:
                    # Normalize the citations right here
                    citations_by_id[bullet_id] = [_normalize_citation(c, article_index_map) for c in raw_citations]
                    break
        
        bullet_counter = 0
        final_analysis = {"executive": [], "investor": [], "catalysts": []}
        for section, bullets in original_analysis.items():
            for bullet_data in bullets:
                # ============================================================================
                # THIS IS THE ONE-LINE FIX
                # ============================================================================
                final_citations = bullet_data.get("citations", []) + citations_by_id.get(bullet_counter, [])
                
                final_analysis[section].append({
                    "text": bullet_data["text"],
                    "text_block_index": bullet_data.get("text_block_index", -1),
                    "citations": final_citations # ✅ USE THE MERGED CITATIONS
                })
                bullet_counter += 1
        
        total_merged_citations = sum(len(c) for c in citations_by_id.values())
        logger.info(f"✅ V5 Annotation successful. Merged {total_merged_citations} new citations.")
        
        return {
            'validation_passed': True,
            'annotated_analysis': final_analysis
        }

# ============================================================================
# QUALITY VALIDATION
# ============================================================================

class QualityValidationEngine:
    """
    SIMPLIFIED quality validation engine - EXACTLY ONE web search call.
    No retries, no complex logic - just one call and proper logging.
    """
    
    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.web_search_engine = None
        
        if self.anthropic_api_key:
            self.web_search_engine = ClaudeWebSearchEngine(self.anthropic_api_key)
            logger.info("✅ SIMPLIFIED Quality Validation with Web Search initialized")
        else:
            logger.warning("⚠️ Quality validation disabled - missing Anthropic API key")

    async def validate_and_enhance_analysis_SINGLE_CALL(self, 
                                                       company: str, 
                                                       analysis: UISections, # It now receives the UI object
                                                       articles: List[Dict]) -> Dict[str, Any]:
        """
        REFACTORED V4: No longer enhances/rewrites. It now orchestrates
        a simple, reliable annotation call to add citations.
        """
        if not self.web_search_engine:
            return {'analysis': analysis, 'quality_validation': {'enabled': False}}
        
        logger.info(f"🔍 Orchestrating V4 annotation for {company}")
        
        try:
            # Call the new, reliable annotation method
            annotation_result = await self.web_search_engine.annotate_analysis(
                company, analysis, articles
            )
            
            # Build the result object based on annotation success
            if annotation_result.get('validation_passed'):
                logger.info(f"✅ Annotation successful for {company}.")
                return {
                    'analysis': annotation_result['annotated_analysis'],
                    'quality_validation': {
                        'enabled': True,
                        'passed': True,
                        'score': 9.0, # Assign a high static score for success
                        'verdict': 'annotated',
                        'used_enhanced_analysis': True, # This flag now means "annotation applied"
                        'message': 'Analysis successfully annotated with citations.'
                    },
                    'success': True,
                    'enhanced': True
                }
            else:
                logger.warning(f"⚠️ Annotation failed for {company}. Reverting to original.")
                return {
                    'analysis': analysis, # Return original on failure
                    'quality_validation': {
                        'enabled': True,
                        'passed': False,
                        'score': 4.0,
                        'verdict': 'annotation_failed',
                        'used_enhanced_analysis': False,
                        'error': annotation_result.get('error', 'Unknown annotation error')
                    },
                    'success': True,
                    'enhanced': False
                }

        except Exception as e:
            logger.error(f"❌ Annotation process crashed for {company}: {e}", exc_info=True)
            return {
                'analysis': analysis,
                'quality_validation': {
                    'enabled': True, 'passed': False, 'score': 4.0,
                    'error': str(e), 'used_enhanced_analysis': False
                },
                'success': True,
                'enhanced': False
            }

    def _create_enhanced_validated_result(self, validation_result: Dict, 
                            score: float, passed: bool, company: str, 
                            original_articles: List[Dict]) -> Dict[str, Any]:
        """Create result with dual scoring and improvement tracking."""
        
        # Extract dual scoring data
        baseline = validation_result.get('baseline_assessment', {})
        improvement = validation_result.get('improvement_analysis', {})
        
        original_score = improvement.get('original_score', 0)
        revised_score = improvement.get('revised_score', score)
        score_delta = revised_score - original_score
        
        # Use enhanced analysis if improvements were made
        revised_analysis = validation_result.get('revised_analysis', {})
        web_searches = validation_result.get('web_searches_performed', [])
        enhancements = validation_result.get('enhancements_made', [])

        # ✅ IMPROVED LOGIC: Use enhanced if we have meaningful improvements
        meaningful_improvement = score_delta >= 0.5 or len(web_searches) >= 3

        if revised_analysis and meaningful_improvement:
            # Check if the revised analysis has meaningful content in all sections
            has_content = all(
                revised_analysis.get(section) and len(revised_analysis[section]) > 0 
                for section in ['executive', 'investor', 'catalysts']
            )
            
            if has_content:
                final_analysis = revised_analysis
                used_enhanced = True
                logger.info(f"   📝 Using ENHANCED analysis for {company}")
                logger.info(f"   📊 Quality improvement: {original_score:.1f} → {revised_score:.1f} (+{score_delta:.1f})")
            else:
                final_analysis = {}
                used_enhanced = False
                logger.warning(f"   📝 Enhanced analysis empty, falling back to original for {company}")
        else:
            final_analysis = {}
            used_enhanced = False
            logger.warning(f"   📝 Using ORIGINAL analysis for {company} (insufficient improvement)")
        
        # ✅ NEW: Enhanced pass/fail logic considering improvement
        if revised_score >= 7.0:
            validation_passed = True
            pass_reason = "revised_analysis_meets_threshold"
        elif score_delta >= 1.0 and revised_score >= 6.0:
            validation_passed = True  
            pass_reason = "significant_improvement_with_acceptable_quality"
        else:
            validation_passed = False
            pass_reason = "insufficient_quality_and_improvement"
        
        return {
            'analysis': final_analysis,
            'quality_validation': {
                'enabled': True,
                'passed': validation_passed,
                'score': float(revised_score),
                'verdict': validation_result.get('overall_verdict', 'unknown'),
                
                # ✅ NEW: Dual scoring transparency
                'baseline_score': float(original_score),
                'revised_score': float(revised_score), 
                'improvement_delta': float(score_delta),
                'quality_trajectory': improvement.get('quality_trajectory', 'unknown'),
                'web_search_effectiveness': improvement.get('web_search_effectiveness', 'unknown'),
                
                'web_searches_performed': len(web_searches),
                'enhancements_made': enhancements,
                'used_enhanced_analysis': used_enhanced,
                'pass_reason': pass_reason,
                
                # ✅ NEW: Improvement details
                'original_issues': baseline.get('original_issues', []),
                'improvements_applied': len(enhancements),
                'baseline_summary': baseline.get('baseline_summary', ''),
                
                'single_call_validation': True,
                'dual_scoring_enabled': True
            },
            'success': True,
            'enhanced': used_enhanced
        }
    
    def _create_improvement_summary(self, validation_result: Dict) -> Dict[str, Any]:
        """Create summary of improvements made."""
        enhancements = validation_result.get('enhancements_made', [])
        web_searches = validation_result.get('web_searches_performed', [])
        
        return {
            'enhancements_count': len(enhancements),
            'web_searches_count': len(web_searches),
            'top_enhancements': enhancements[:3],
            'key_data_updates': [
                search.get('data_updated', 'N/A') 
                for search in web_searches[:3] 
                if search.get('data_updated')
            ]
        }
    
    def _create_web_search_summary(self, validation_result: Dict) -> Dict[str, Any]:
        """Create summary of web search results."""
        searches = validation_result.get('web_searches_performed', [])
        
        return {
            'searches_performed': len(searches),
            'search_queries': [s.get('query', 'N/A') for s in searches],
            'key_findings': [s.get('key_finding', 'N/A') for s in searches],
            'data_freshness_updates': sum(1 for s in searches if 'current' in s.get('key_finding', '').lower())
        }
    
    def _create_rate_limit_result(self, analysis: Dict[str, List[str]], company: str) -> Dict[str, Any]:
        """Create result when rate limited due to web search tokens."""
        logger.warning(f"   ⚠️ Rate limited on {company} - web search adds ~210k hidden tokens")
        
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': True,
                'passed': False,
                'score': None,
                'verdict': 'rate_limited',
                'web_search_enabled': True,
                'rate_limited': True,
                'error': 'Rate limited due to web search hidden tokens (~210k)',
                'message': 'Web search validation failed - using original analysis',
                'single_call_validation': True
            },
            'success': True,
            'enhanced': False
        }
    
    def _create_unvalidated_result(self, analysis: Dict[str, List[str]]) -> Dict[str, Any]:
        """Create result when validation is disabled."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': False,
                'passed': None,
                'score': None,
                'message': 'Web search validation disabled - missing Anthropic API key',
                'single_call_validation': True
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
                'message': 'Web search validation failed - using original analysis',
                'single_call_validation': True
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
    """Score articles based on relevance and source quality - IMPROVED VERSION."""
    scored_articles = []
    
    for article in articles:
        score = 0.0
        
        source = article.get('source', '').lower()
        source_type = article.get('source_type', 'google_search')
        title = article.get('title', '').lower()
        snippet = article.get('snippet', '').lower()
        
        # ✅ CHECK COMPANY RELEVANCE FIRST
        company_lower = company.lower()
        content = title + ' ' + snippet
        
        # Count company mentions
        company_mentions = content.count(company_lower)
        title_mentions = title.count(company_lower)
        
        # ✅ HEAVY PENALTY: No company mentions at all
        if company_mentions == 0 and not any(word in content for word in ['apple', 'aapl', 'iphone', 'ios', 'mac']):
            score -= 50  # Heavy penalty for completely irrelevant articles
            logger.debug(f"❌ No company relevance: {title[:50]}...")
        
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
        
        # ✅ COMPANY RELEVANCE BONUSES (after checking for mentions)
        if company_mentions > 0:
            if title_mentions > 0:
                score += 10  # Title mentions are valuable
            score += min(company_mentions * 3, 15)  # Up to 15 points for multiple mentions
        
        # Financial relevance
        financial_keywords = ['earnings', 'revenue', 'stock', 'analyst', 'price target']
        financial_score = sum(1 for keyword in financial_keywords if keyword in content)
        score += financial_score * 2
        
        # ✅ MINIMUM SCORE: Don't include articles with very negative scores
        if score < -30:
            continue  # Skip completely irrelevant articles
        
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
    """Decide whether to trigger Google CSE - IMPROVED VERSION."""
    total_articles = len(all_articles)
    relevant_count = len(relevant_articles)
    relevance_percentage = relevance_stats.get('relevance_percentage', 0)
    
    logger.info(f"CSE Decision: {total_articles} total, {relevant_count} relevant ({relevance_percentage:.1%})")
    
    # ✅ NEW LOGIC: If we'll need to fill >50% with non-relevant articles, use Google CSE
    target_articles = 30
    if relevant_count < (target_articles * 0.5):  # Less than 15 relevant articles
        decision = True
        reason = f"Need Google CSE to avoid filling with irrelevant content ({relevant_count} relevant < {target_articles//2} threshold)"
    
    # ✅ KEEP EXISTING: Low volume companies always get CSE
    elif total_articles < 15:
        decision = True
        reason = f"Low volume company ({total_articles} articles)"
    
    # ✅ KEEP EXISTING: Very few relevant articles
    elif relevant_count < config.MIN_RELEVANT_ARTICLES_BEFORE_GOOGLE:
        decision = True
        reason = f"Insufficient relevant articles ({relevant_count} < {config.MIN_RELEVANT_ARTICLES_BEFORE_GOOGLE})"
    
    # ✅ IMPROVED: Good relevant count AND good rate
    elif relevant_count >= 15 and relevance_percentage >= config.MIN_RELEVANCE_PERCENTAGE:
        decision = False
        reason = f"Sufficient relevant content ({relevant_count} relevant, {relevance_percentage:.1%} rate)"
    
    # ✅ DEFAULT: When in doubt, use CSE to avoid irrelevant filler
    else:
        decision = True
        reason = f"Use CSE to find more company-specific content (avoid irrelevant filler)"
    
    logger.info(f"🎯 CSE Decision: {'TRIGGER' if decision else 'SKIP'} - {reason}")
    return decision

# ============================================================================
# ANALYSIS GENERATION
# ============================================================================

def generate_enhanced_analysis(company: str, articles: List[Dict]) -> Tuple[UISections, Dict]:
    """Generate analysis using Claude Sonnet 4 with OpenAI fallback."""
    if not articles:
        return create_empty_summaries(company), {}
    
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
        return create_error_summaries(company, str(openai_error)), {}

def generate_claude_analysis(company: str, articles: List[Dict]) -> Tuple[UISections, Dict]:
    """Generate analysis using Claude Sonnet 4 with Citations API and fallback."""
    
    try:
        # Try Citations API first
        return generate_claude_analysis_with_citations(company, articles)
    except Exception as e:
        logger.warning(f"Citations API failed: {e}, falling back to manual system")
        return generate_claude_analysis_manual(company, articles)

def generate_claude_analysis_manual(company: str, articles: List[Dict]) -> Tuple[UISections, Dict]:
    """Fallback to original manual citation system"""
    anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Prepare articles as document blocks for Citations API
    document_blocks = []
    article_index_map = {}  # Map document index to article data

    for i, article_item in enumerate(articles[:30]):
        content = f"Title: {article_item['title']}\n"
        content += f"Content: {article_item.get('full_content', article_item.get('snippet', ''))}\n"
        content += f"Source: {article_item['source']}\n"
        content += f"Published: {article_item.get('published', '')}\n"
        
        if article_item.get('source_type') == 'alphavantage_premium':
            content += f"Sentiment: {article_item.get('sentiment_label', 'Neutral')} ({article_item.get('sentiment_score', 0):.3f})\n"
            content += f"Relevance: {article_item.get('relevance_score', 0):.3f}\n"
        
        # Store mapping for later citation processing
        article_index_map[i] = {
            'article': article_item,
            'url': article_item.get('link', '#'),
            'source': article_item.get('source', 'Unknown'),
            'title': article_item.get('title', 'Unknown'),
            'source_type': article_item.get('source_type', 'google_search')
        }
        
        document_blocks.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain", 
                "data": content
            },
            "citations": {"enabled": True},
            "title": f"{article_item['source']} - {article_item['title'][:50]}..."
        })

    # Create enhanced analysis prompt (your existing enhanced prompt without manual citations)
    analysis_prompt = f"""You are a Managing Director of Equity Research at Goldman Sachs writing for institutional investors.

**CRITICAL: Use the provided source documents to support all claims. Claude's Citations API will automatically cite relevant sources.**

ENHANCED ANALYTICAL FRAMEWORK - Superior Depth with Accessible Communication:

**CRITICAL FORMATTING REQUIREMENTS:**
- Use EXACTLY these section headers: "**EXECUTIVE SUMMARY**", "**INVESTOR INSIGHTS**", "**CATALYSTS & RISKS**"
- Start each bullet with a bullet point symbol: "•"
- Each section must have exactly 4-5 bullets

**CRITICAL WRITING REQUIREMENTS:**
1. **Storytelling Flow**: Each bullet should read like professional investment commentary, not raw data
2. **Source-Grounded Analysis**: Support all claims with information from the provided documents
3. **Accessible Language**: Maintain analytical precision but use clear, readable language that flows naturally
4. **Quantified Insights**: Include specific metrics and probability estimates, but weave them into compelling narratives
5. **Professional Tone**: Write like you're briefing a client, not generating a technical report

**EXECUTIVE SUMMARY** (Strategic & Financial Impact)
Create 4-5 bullets that tell the strategic story of {company} with quantified impacts.

**INVESTOR INSIGHTS** (Valuation & Market Dynamics)
Create 4-5 bullets that weave valuation analysis into compelling market stories.

**CATALYSTS & RISKS** (Probability-Weighted Analysis)
Create 4-5 bullets that present catalysts and risks as investment decision factors.

Generate exactly 4-5 substantive bullets per section that combine analytical excellence with compelling storytelling, grounded in the provided source documents."""

    # Create message content with document blocks + text prompt
    message_content = document_blocks + [{
        "type": "text",
        "text": analysis_prompt
    }]

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514", 
        max_tokens=7500,
        temperature=0.07,
        messages=[{
            "role": "user",
            "content": message_content
        }]
    )

    try:
        raw = response.model_dump_json(indent=2, ensure_ascii=False)  # full, pretty JSON
    except Exception:
        raw = json.dumps(
            response,
            default=lambda o: getattr(o, "model_dump", getattr(o, "dict", lambda: getattr(o, "__dict__", str(o))))(),
            ensure_ascii=False,
            indent=2,
        )

    logger.info("CLAUDE RAW RESPONSE:\n%s", raw)

    
    # Process response preserving Claude's native citation structure
    final_analysis: UISections = {"executive": [], "investor": [], "catalysts": []}
    current_section = None
    
    # Section detection patterns
    section_patterns = {
        "executive": re.compile(r".*executive\s+summary.*", re.IGNORECASE),
        "investor":  re.compile(r".*investor\s+insights.*", re.IGNORECASE),
        "catalysts": re.compile(r".*(catalysts?\s*(&|and)?\s*risks?|risks?\s*(&|and)?\s*catalysts?).*", re.IGNORECASE),
    }
    
    # enumerate to capture text_block_index for the UI
    for block_idx, content_block in enumerate(response.content):
        if content_block.type == "text":
            text = content_block.text
            citations = getattr(content_block, 'citations', [])
            
            # Convert citations to normalized format for this specific text block
            if citations:
                normalized_citations = [_normalize_citation(c, article_index_map) for c in citations]
            else:
                normalized_citations = []
            
            # Parse this text block into bullet points
            lines = text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for section headers
                for section_name, pattern in section_patterns.items():
                    if pattern.match(line):
                        current_section = section_name
                        break
                else:
                    # Process bullet points
                    if line.startswith(('•', '-', '*')) and current_section:
                        bullet = line.lstrip('•-* ').strip()
                        if bullet and len(bullet) > 10:
                            final_analysis[current_section].append({
                                "text": bullet,
                                "text_block_index": block_idx,
                                "citations": normalized_citations
                            })
    
    # Ensure each section has content
    for section_name, bullets in final_analysis.items():
        if not bullets:
            final_analysis[section_name] = [_mk("No significant developments identified in this category.")]

    logger.info(f"Claude analysis with preserved native citations: {len(str(final_analysis))} chars")
    return final_analysis, article_index_map


def generate_claude_analysis_with_citations(company: str, articles: List[Dict]) -> Tuple[UISections, Dict]:
    """Generate analysis using Claude Sonnet 4."""
    anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # --- This is YOUR original document and prompt preparation ---
    # --- I have not touched this. ---
    source_type_counts = {}
    for article_item in articles[:30]:
        source_type = article_item.get('source_type', 'google_search')
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

    document_blocks, article_index_map = [], {}
    for i, article_item in enumerate(articles[:30]):
        content = f"Title: {article_item['title']}\n"
        content += f"Content: {article_item.get('full_content', article_item.get('snippet', ''))}\n"
        content += f"Source: {article_item['source']}\n"
        content += f"Published: {article_item.get('published', '')}\n"
        if article_item.get('source_type') == 'alphavantage_premium':
            content += f"Sentiment: {article_item.get('sentiment_label', 'Neutral')} ({article_item.get('sentiment_score', 0):.3f})\n"
            content += f"Relevance: {article_item.get('relevance_score', 0):.3f}\n"
        article_index_map[i] = {
            'article': article_item, 'url': article_item.get('link', '#'),
            'source': article_item.get('source', 'Unknown'), 'title': article_item.get('title', 'Unknown'),
            'source_type': article_item.get('source_type', 'google_search')
        }
        document_blocks.append({
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": content},
            "citations": {"enabled": True},
            "title": f"{article_item['source']} - {article_item['title'][:50]}..."
        })

    # ============================================================================
    # THIS IS YOUR ORIGINAL, HIGH-QUALITY PROMPT. IT HAS BEEN FULLY RESTORED.
    # ============================================================================
    analysis_prompt = f"""You are a Managing Director of Equity Research at Goldman Sachs writing for institutional investors.

**CRITICAL: Use the provided source documents to support all claims. Claude's Citations API will automatically cite relevant sources.**

ENHANCED ANALYTICAL FRAMEWORK - Superior Depth with Accessible Communication:

**CRITICAL FORMATTING REQUIREMENTS:**
- Use EXACTLY these section headers: "**EXECUTIVE SUMMARY**", "**INVESTOR INSIGHTS**", "**CATALYSTS & RISKS**"
- Start each bullet with a bullet point symbol: "•"
- Each section must have exactly 4-5 bullets

**CRITICAL WRITING REQUIREMENTS:**
1. **Storytelling Flow**: Each bullet should read like professional investment commentary, not raw data
2. **Source-Grounded Analysis**: Support all claims with information from the provided documents
3. **Accessible Language**: Maintain analytical precision but use clear, readable language that flows naturally
4. **Quantified Insights**: Include specific metrics and probability estimates, but weave them into compelling narratives
5. **Professional Tone**: Write like you're briefing a client, not generating a technical report

**EXECUTIVE SUMMARY** (Strategic & Financial Impact - Write as compelling investment thesis)
Create 4-5 bullets that tell the strategic story of {company} with quantified impacts:

- Start each bullet with strategic context, then layer in specific financial metrics
- Include timeline estimates and probability assessments naturally woven into the narrative
- Use sophisticated tags but make the content accessible: [STRATEGY], [FINANCIAL_IMPACT], [EXECUTION_RISK], [VALUE_CREATION], [MANAGEMENT_QUALITY]
- Example style: "[STRATEGY] {{company}}'s expansion into [specific area] represents a significant strategic shift that could drive [specific financial impact with range] over [timeline], with [confidence level] probability of success based on management guidance and market analysis"

**INVESTOR INSIGHTS** (Valuation & Market Dynamics - Write as investment analysis narrative)
Create 4-5 bullets that weave valuation analysis into compelling market stories:

- Integrate valuation metrics (P/E, EV/EBITDA) into broader market positioning narrative
- Connect analyst consensus and price targets to underlying business drivers
- Correlate sentiment analysis with fundamental developments in a readable way
- Include competitive positioning as part of investment thesis, not isolated data points
- Use tags: [VALUATION], [PEER_COMPARISON], [SENTIMENT_ANALYSIS], [TECHNICAL], [INSTITUTIONAL_FLOW]
- Example style: "[VALUATION] Trading at [specific metrics] versus peers, {{company}} appears [undervalued/fairly valued/overvalued] based on [specific analysis methodology]. Recent analyst updates suggest [price target range] reflecting [specific business drivers], with sentiment analysis indicating [market sentiment context]"

**CATALYSTS & RISKS** (Probability-Weighted Analysis with Investment Context)
Create 4-5 bullets that present catalysts and risks as investment decision factors:

- Frame each catalyst/risk in terms of investment impact and timeline, not just technical probability
- Provide specific dates and probability estimates but explain the investment rationale
- Connect technical analysis and options flow to fundamental business developments
- Use tags: [CATALYST], [EVENT_RISK], [REGULATORY], [MACRO_SENSITIVITY], [TECHNICAL_LEVELS]
- Example style: "[CATALYST] The upcoming [specific event/announcement] scheduled for [date] presents a [upside/downside] catalyst with [probability estimate] likelihood of [specific financial impact]. This catalyst is particularly significant because [business context], with options market positioning suggesting [market expectations]"

**ENHANCED REQUIREMENTS FOR SUPERIOR READABILITY:**

1. **Narrative Flow Mastery**: 
   - Begin each bullet with strategic context before diving into metrics
   - Connect quantitative insights to broader business implications
   - Use transition phrases to create smooth flow between technical and strategic points
   - End bullets with forward-looking implications

2. **Quantification with Context**:
   - Always provide ranges and confidence intervals: "15-25% upside with 70% confidence"
   - Include timeline specificity: "expected by Q3 2025"
   - Connect metrics to business drivers: "driven by market share expansion in [specific segment]"

3. **Professional Investment Commentary Style**:
   - Write as if briefing a sophisticated investor
   - Use active voice and confident language
   - Avoid overly technical jargon without context
   - Maintain analytical rigor while ensuring accessibility

**CROSS-SOURCE VALIDATION REQUIREMENTS**:
- When multiple sources provide similar information, synthesize and reference all relevant information
- When sources conflict, acknowledge differences and provide your analytical view
- Highlight unique insights from premium sources (Bloomberg, Reuters, WSJ)
- Leverage AlphaVantage sentiment data as supporting evidence for fundamental themes

**FINAL QUALITY CHECK**:
Each bullet should pass these tests:
✓ Does it tell a clear story that has been advanced the investment thesis?
✓ Would a portfolio manager understand the investment implications?
✓ Is the language accessible while maintaining analytical depth?
✓ Do the quantified estimates have proper context and confidence levels?

Generate exactly 4-5 substantive bullets per section that combine analytical excellence with compelling storytelling, grounded in the provided source documents."""
    
    message_content = document_blocks + [{"type": "text", "text": analysis_prompt}]

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=7500, temperature=0.07,
        messages=[{"role": "user", "content": message_content}]
    )

    try:
        raw = response.model_dump_json(indent=2, ensure_ascii=False)
    except Exception:
        raw = json.dumps(response, default=lambda o: getattr(o, "model_dump", str)(), indent=2)
    logger.info("CLAUDE RAW RESPONSE:\n%s", raw)
    
    # ============================================================================
    # THIS IS THE NEW, ROBUST, CRASH-PROOF PARSER.
    # It replaces the original broken parser logic.
    # ============================================================================
    logger.info("🤖 Starting robust parsing of single-call LLM response...")
    final_analysis: UISections = {"executive": [], "investor": [], "catalysts": []}
    current_section = None
    bullet_buffer = {"text": "", "citations": [], "block_indices": []}

    section_patterns = {
        "executive": re.compile(r".*executive\s+summary.*", re.IGNORECASE),
        "investor":  re.compile(r".*investor\s+insights.*", re.IGNORECASE),
        "catalysts": re.compile(r".*(catalysts?\s*(&|and)?\s*risks?|risks?\s*(&|and)?\s*catalysts?).*", re.IGNORECASE),
    }

    def flush_bullet_buffer():
        if bullet_buffer["text"].strip() and current_section:
            text = bullet_buffer["text"].strip().lstrip('•').strip()
            unique_citations = list({c.get('document_index'): c for c in bullet_buffer["citations"] if c.get('document_index') is not None}.values())
            
            final_analysis[current_section].append({
                "text": text,
                "text_block_index": bullet_buffer["block_indices"][0] if bullet_buffer["block_indices"] else -1,
                "citations": unique_citations
            })
        bullet_buffer["text"], bullet_buffer["citations"], bullet_buffer["block_indices"] = "", [], []

    for block_idx, content_block in enumerate(response.content):
        if content_block.type != "text": continue
        text = content_block.text
        raw_citations = getattr(content_block, 'citations', []) or []
        normalized_citations = [_normalize_citation(c, article_index_map) for c in raw_citations]
        
        for line in text.split('\n'):
            if not line.strip(): continue
            is_header = False
            for section_name, pattern in section_patterns.items():
                if pattern.match(line):
                    flush_bullet_buffer()
                    current_section = section_name
                    is_header = True
                    break
            if is_header: continue
            if line.strip().startswith('•'):
                flush_bullet_buffer()
                bullet_buffer["text"] += line
            else:
                bullet_buffer["text"] += " " + line
            bullet_buffer["citations"].extend(normalized_citations)
            if block_idx not in bullet_buffer["block_indices"]:
                bullet_buffer["block_indices"].append(block_idx)
    flush_bullet_buffer()
    
    # Ensure each section has content
    for section_name in final_analysis:
        if not final_analysis[section_name]:
            final_analysis[section_name] = [_mk(f"No significant developments identified for {company} in this category.")]

    total_citations = sum(len(b['citations']) for s in final_analysis.values() for b in s)
    logger.info(f"✅ Robust parsing complete. Found {total_citations} citations.")
    return final_analysis, article_index_map

def generate_openai_analysis(company: str, articles: List[Dict]) -> Tuple[UISections, Dict]:
    """Generate analysis using OpenAI as fallback."""
    # Prepare article content (simplified for OpenAI)
    article_text_for_prompt = ""
    for i, article in enumerate(articles[:30], 1):
        article_text_for_prompt += f"\n{i}. {article['title']}\n"
        article_text_for_prompt += f"   Source: {article['source']}\n"
        article_text_for_prompt += f"   Content: {article.get('snippet', '')}\n"
    
    prompt = f"""You are a senior equity research analyst analyzing {company}.

ARTICLES TO ANALYZE:
{article_text_for_prompt}

Generate institutional-grade analysis in exactly this format:

**EXECUTIVE SUMMARY**
- [bullet point 1]
- [bullet point 2] 
- [bullet point 3]

**INVESTOR INSIGHTS**
- [bullet point 1]
- [bullet point 2]
- [bullet point 3]

**CATALYSTS & RISKS**  
- [bullet point 1]
- [bullet point 2]
- [bullet point 3]

Focus on actionable insights with specific metrics and timelines."""
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.05,
        max_tokens=2000
    )
    
    analysis_text = response.choices[0].message.content
    sections_legacy = parse_analysis_response(analysis_text)  # returns Dict[str, List[str]]
    
    # Upgrade to UISections (empty citations, no block index)
    upgraded: UISections = {k: [{"text": t, "text_block_index": -1, "citations": []} for t in texts]
                            for k, texts in sections_legacy.items()}
    
    # Create empty article mapping for compatibility
    article_index_map = {}
    
    logger.info(f"OpenAI analysis generated: {len(analysis_text)} chars")
    return upgraded, article_index_map

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

def create_empty_summaries(company: str) -> UISections:
    return {
        "executive": [_mk(f"No recent financial news found for {company}. Try expanding date range or verifying company ticker.")],
        "investor":  [_mk("No recent investor-relevant developments identified.")],
        "catalysts": [_mk("No material catalysts or risks detected in recent coverage.")],
    }

def create_error_summaries(company: str, error_msg: str) -> UISections:
    return {
        "executive": [_mk(f"Analysis temporarily unavailable for {company}: {error_msg[:100]}...")],
        "investor":  [_mk("Please try again in a few moments or contact support.")],
        "catalysts": [_mk("Consider checking company's investor relations page directly.")],
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

async def generate_citations_for_analysis(company: str, analysis: UISections, articles: List[Dict]) -> UISections:
    """
    Final Strategy: Takes an UNCITED analysis and adds citations to it.
    This version includes EXTREMELY VERBOSE LOGGING.
    """
    import json
    logger.info("="*50)
    logger.info("===== 🔎 LOGGING: ENTERING CITATION GENERATION (PHASE 6) =====")

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception:
        logger.error("Could not initialize Anthropic client for citation generation.")
        return analysis

    # Prepare source documents
    document_blocks, article_index_map = [], {}
    for i, article in enumerate(articles[:35]):
        content = f"Title: {article.get('title', '')}\nSnippet: {article.get('snippet', '')}"
        article_index_map[i] = {'url': article.get('link', '#'), 'source': article.get('source', 'Unknown'), 'title': article.get('title', 'Unknown')}
        document_blocks.append({
            "type": "document", "source": {"type": "text", "media_type": "text/plain", "data": content},
            "citations": {"enabled": True}, "title": f"Doc {i}: {article.get('source', 'N/A')}"
        })

    # Prepare the prompt
    analysis_for_prompt = []
    bullet_counter = 0
    for section in ["executive", "investor", "catalysts"]:
        for bullet_data in analysis.get(section, []):
            clean_text = bullet_data['text'].replace('"', "'")
            analysis_for_prompt.append(f"  {{\"bullet_id\": {bullet_counter}, \"text\": \"{clean_text}\"}}")
            bullet_counter += 1
    analysis_json_string = "[\n" + ",\n".join(analysis_for_prompt) + "\n]"
    prompt = f"""Your only job is to add citations. You are a citation bot.

Read each bullet in the `UNCITED_BULLETS` array. For each bullet, find the source document that supports its claim and use the Citations API to cite it.

**FAILURE CONDITION:** If you return any bullet in the `cited_bullets` array without a citation, you have failed the task. Every bullet must be cited.

**UNCITED_BULLEPTS:**
```json
{analysis_json_string}
OUTPUT FORMAT:
Return a single JSON object.
code
JSON
{{
  "cited_bullets": [
    {{ "bullet_id": 0, "cited_text": "The text from bullet 0, with citations attached." }},
    {{ "bullet_id": 1, "cited_text": "The text from bullet 1, with citations attached." }}
  ]
}}```"""
    message_content = document_blocks + [{"type": "text", "text": prompt}]

    # --- LOG THE PROMPT ---
    logger.info("--- 🔎 LOGGING: PROMPT SENT TO CITATION MODEL ---")
    logger.info(prompt)
    logger.info("--- END OF PROMPT ---")

    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: client.messages.create(
                model="claude-sonnet-4-20250514", max_tokens=4096, temperature=0.0,
                messages=[{"role": "user", "content": message_content}]
            )), timeout=180.0
        )
        
        # --- LOG THE RAW RESPONSE ---
        logger.info("--- 🔎 LOGGING: RAW RESPONSE FROM CITATION MODEL ---")
        try:
            logger.info(json.dumps(response.model_dump(), indent=2))
        except Exception as e:
            logger.error(f"Could not dump raw response model: {e}")
            logger.info(str(response))
        logger.info("--- END OF RAW RESPONSE ---")

        # Parse the response
        raw_text_content = ""
        citations_by_block_index = {}
        for i, block in enumerate(response.content):
            if block.type == 'text':
                raw_text_content += block.text
                if hasattr(block, 'citations') and block.citations:
                    citations_by_block_index[i] = block.citations
        
        # --- LOG PARSED CITATIONS ---
        logger.info(f"--- 🔎 LOGGING: PARSED CITATIONS FROM RAW RESPONSE (found in {len(citations_by_block_index)} blocks) ---")
        logger.info(str(citations_by_block_index))
        logger.info("--- END OF PARSED CITATIONS ---")

        json_start = raw_text_content.find('{')
        json_end = raw_text_content.rfind('}') + 1
        result = json.loads(raw_text_content[json_start:json_end])
        cited_bullets_from_model = result.get("cited_bullets", [])

        citations_by_id = {}
        for bullet_info in cited_bullets_from_model:
            bullet_id = bullet_info.get("bullet_id")
            bullet_text = bullet_info.get("cited_text")
            for block_index, raw_citations in citations_by_block_index.items():
                if bullet_text and bullet_text in response.content[block_index].text:
                    citations_by_id[bullet_id] = [_normalize_citation(c, article_index_map) for c in raw_citations]
                    break
        
        # --- LOG THE MERGED CITATION MAP ---
        logger.info("--- 🔎 LOGGING: FINAL CITATION MAP (citations_by_id) ---")
        logger.info(json.dumps(citations_by_id, indent=2))
        logger.info("--- END OF CITATION MAP ---")

        # Merge citations back into the original analysis object
        bullet_counter = 0
        cited_analysis = {"executive": [], "investor": [], "catalysts": []}
        for section, bullets in analysis.items():
            for bullet_data in bullets:
                cited_analysis[section].append({
                    "text": bullet_data["text"],
                    "text_block_index": bullet_data.get("text_block_index", -1),
                    "citations": citations_by_id.get(bullet_counter, [])
                })
                bullet_counter += 1
        
        # --- LOG THE FINAL OBJECT ---
        logger.info("--- 🔎 LOGGING: FINAL CITED ANALYSIS OBJECT TO BE RETURNED ---")
        logger.info(json.dumps(cited_analysis, indent=2))
        logger.info("--- END OF FINAL OBJECT ---")
        
        return cited_analysis

    except Exception as e:
        logger.error(f"❌ Citation generation step failed: {e}", exc_info=True)
        return analysis

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
    
    # Phase 4: Final article selection - IMPROVED VERSION
    logger.info("🎯 Phase 4: Final article selection...")

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

    # ✅ IMPROVED: Only fill with non-relevant articles if they have positive scores AND some company relevance
    if len(final_articles) < config.TARGET_ARTICLE_COUNT:
        company_lower = company.lower()
        
        for article, score in scored_articles:
            if article.get('link', '') not in relevant_urls:
                # ✅ CHECK: Does this article have ANY company relevance?
                title = article.get('title', '').lower()
                snippet = article.get('snippet', '').lower()
                content = title + ' ' + snippet
                
                # Only add if it mentions the company OR has high financial relevance
                has_company_mention = company_lower in content or any(word in content for word in ['apple', 'aapl', 'iphone', 'ios', 'mac'])
                has_strong_financial_context = any(word in content for word in ['stock', 'earnings', 'revenue', 'analyst', 'investment'])
                
                if has_company_mention or (has_strong_financial_context and score > 10):
                    final_articles.append(article)
                    if len(final_articles) >= config.TARGET_ARTICLE_COUNT:
                        break
                else:
                    logger.debug(f"🚫 Skipping irrelevant article: {title[:50]}...")

    # ✅ If we still don't have enough articles, log the gap
    if len(final_articles) < config.TARGET_ARTICLE_COUNT:
        gap = config.TARGET_ARTICLE_COUNT - len(final_articles)
        logger.warning(f"⚠️ Only found {len(final_articles)}/{config.TARGET_ARTICLE_COUNT} relevant articles. {gap} slots unfilled (better than irrelevant filler).")

    final_articles = final_articles[:config.TARGET_ARTICLE_COUNT]

    logger.info(f"🎯 Final selection: {len(final_articles)} articles ({len([a for a in final_articles if a.get('link', '') in relevant_urls])} relevant + {len(final_articles) - len([a for a in final_articles if a.get('link', '') in relevant_urls])} additional relevant)")

    # Phase 5: Analysis generation
    logger.info("📝 Phase 5: Analysis generation...")
    initial_summaries_ui, article_index_map = generate_enhanced_analysis(company, final_articles)

    try:
        import json
        logger.info("="*50)
        logger.info("===== 🔎 LOGGING: INITIAL ANALYSIS (PHASE 5) =====")
        logger.info(f"Type of initial_summaries_ui: {type(initial_summaries_ui)}")
        logger.info("Dumping initial_summaries_ui content:")
        logger.info(json.dumps(initial_summaries_ui, indent=2))
        logger.info("="*50)
    except Exception as e:
        logger.error(f"Could not log initial_summaries_ui: {e}")
# ============================================================================
    
    # Phase 6: SIMPLIFIED quality validation - EXACTLY ONE CALL
    final_summaries_ui = initial_summaries_ui
    quality_info = {'enabled': enable_quality_validation, 'passed': None, 'score': None}

    if enable_quality_validation and final_articles:
        logger.info("🔍 Phase 6: SINGLE CALL quality validation...")
        quality_engine = QualityValidationEngine()
        
        try:
            # Pass the rich UI object directly to the validator
            quality_result = await quality_engine.validate_and_enhance_analysis_SINGLE_CALL(
                company, initial_summaries_ui, final_articles
            )
            
            # The 'quality_validation' key now holds all scoring and metadata
            quality_info = quality_result.get('quality_validation', quality_info)
            
            # Check if the enhanced analysis exists and has citations
            enhanced_analysis_ui = quality_result.get('analysis') # This is already a UISections object
            has_enhancements = quality_info.get('used_enhanced_analysis', False)
            
            if has_enhancements and enhanced_analysis_ui:
                final_summaries_ui = enhanced_analysis_ui
                logger.info(f"🎉 Using ENHANCED and CITED analysis for {company}")
            else:
                final_summaries_ui = initial_summaries_ui
                logger.warning(f"⚠️ Reverting to original analysis for {company}. Enhanced version was not used or lacked citations.")

        except Exception as quality_error:
            logger.error(f"❌ Quality validation ERROR for {company}: {quality_error}", exc_info=True)
            final_summaries_ui = initial_summaries_ui
            quality_info = {'enabled': True, 'passed': False, 'error': str(quality_error), 'score': None}
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
        'summaries': final_summaries_ui,
        'article_index_map': article_index_map,
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