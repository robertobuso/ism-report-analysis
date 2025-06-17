"""
Enhanced Financial News Analysis System with Dynamic Google CSE Integration
===========================================================================

This module implements a sophisticated news fetching and selection system that:
1. Assesses article relevance to target companies early in the pipeline
2. Dynamically triggers Google Custom Search based on relevant content, not just quantity
3. Maintains excellent performance for well-known companies
4. Improves coverage for lesser-known companies through intelligent gap-filling

Key Components:
- RelevanceAssessor: Evaluates if articles are truly about the target company
- DynamicSourceOrchestrator: Makes intelligent decisions about when to use additional sources
- Enhanced article scoring and selection logic
"""

import logging
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

@dataclass
class AnalysisConfig:
    """Configuration parameters for the enhanced news analysis system."""
    
    # Relevance thresholds
    MIN_RELEVANT_PREMIUM_ARTICLES_BEFORE_CSE: int = 8
    MIN_COMPANY_RELEVANCE_SCORE: float = 0.6
    MIN_FINANCIAL_CONTEXT_SCORE: float = 0.3
    
    # Google CSE trigger conditions
    MAX_ARTICLES_BEFORE_CSE_CHECK: int = 25
    MIN_RELEVANT_PERCENTAGE: float = 0.4  # 40% of articles should be relevant
    
    # Source prioritization weights
    ALPHAVANTAGE_WEIGHT: float = 2.0
    NYT_WEIGHT: float = 1.8
    PREMIUM_RSS_WEIGHT: float = 1.5
    GOOGLE_CSE_WEIGHT: float = 1.0
    
    # Quality thresholds
    TARGET_ARTICLE_COUNT: int = 30
    MIN_ARTICLE_COUNT: int = 15
    
    # Performance settings
    ENABLE_FULL_TEXT_EXTRACTION: bool = False
    ENABLE_ADVANCED_NLP: bool = False

class RelevanceAssessor:
    """
    Advanced relevance assessment for determining if articles are truly about the target company.
    Uses multiple heuristics and can be extended with NLP for more sophisticated analysis.
    """
    
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self._setup_keyword_patterns()
    
    def _setup_keyword_patterns(self):
        """Initialize keyword patterns for relevance assessment."""
        # Financial context keywords (high importance)
        self.financial_keywords = {
            'earnings': 1.0, 'revenue': 1.0, 'profit': 0.9, 'eps': 1.0,
            'guidance': 0.9, 'forecast': 0.8, 'outlook': 0.8,
            'analyst': 0.9, 'rating': 0.8, 'target': 0.8, 'upgrade': 0.9, 'downgrade': 0.9,
            'stock': 0.7, 'shares': 0.7, 'price': 0.6, 'market': 0.5,
            'acquisition': 1.0, 'merger': 1.0, 'deal': 0.8, 'investment': 0.8,
            'ceo': 0.8, 'cfo': 0.8, 'management': 0.7, 'board': 0.7,
            'product': 0.6, 'launch': 0.7, 'partnership': 0.7
        }
        
        # Negative indicators (reduce relevance)
        self.negative_indicators = {
            'job', 'career', 'hiring', 'apply', 'employment', 'work at',
            'directory', 'listing', 'yellow pages', 'contact us',
            'about us', 'location', 'hours', 'phone', 'address'
        }
        
        # Financial news patterns
        self.financial_patterns = [
            r'\$[\d,]+(?:\.\d+)?[kmb]?',  # Dollar amounts
            r'\d+(?:\.\d+)?%',  # Percentages
            r'q[1-4]\s+\d{4}',  # Quarters
            r'fy\s*\d{4}',  # Fiscal years
            r'\d+\.\d+\s*eps',  # EPS mentions
        ]
    
    def assess_article_relevance(self, article: Dict, company: str, 
                                ticker: Optional[str] = None, 
                                company_name: Optional[str] = None) -> Dict[str, float]:
        """
        Comprehensive relevance assessment for a single article.
        
        Returns:
            Dict with relevance scores:
            - company_relevance: How much the article is about the target company (0-1)
            - financial_context: How much financial/business context exists (0-1)
            - overall_relevance: Combined relevance score (0-1)
            - is_company_specific: Boolean indicating if article is truly about the company
        """
        
        title = article.get('title', '').lower()
        content = article.get('snippet', '') or article.get('full_content', '')
        content = content.lower()
        combined_text = f"{title} {content}"
        
        # Get all company identifiers
        company_identifiers = self._get_company_identifiers(company, ticker, company_name)
        
        # 1. Company Mention Analysis
        company_relevance = self._assess_company_mentions(combined_text, company_identifiers)
        
        # 2. Financial Context Analysis
        financial_context = self._assess_financial_context(combined_text)
        
        # 3. Content Quality Assessment
        content_quality = self._assess_content_quality(article, combined_text)
        
        # 4. Source Quality Bonus
        source_quality = self._assess_source_quality(article)
        
        # 5. Negative Indicators Check
        negative_penalty = self._check_negative_indicators(combined_text)
        
        # Calculate overall relevance with weighted combination
        overall_relevance = (
            company_relevance * 0.4 +
            financial_context * 0.3 +
            content_quality * 0.2 +
            source_quality * 0.1
        ) - negative_penalty
        
        # Ensure bounds
        overall_relevance = max(0.0, min(1.0, overall_relevance))
        
        # Determine if article is company-specific
        is_company_specific = (
            company_relevance >= self.config.MIN_COMPANY_RELEVANCE_SCORE and
            financial_context >= self.config.MIN_FINANCIAL_CONTEXT_SCORE and
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
            # Add variations without corporate suffixes
            clean_name = company_name.lower()
            for suffix in [' inc', ' corp', ' corporation', ' company', ' ltd', ' limited']:
                clean_name = clean_name.replace(suffix, '')
            if clean_name not in identifiers:
                identifiers.append(clean_name)
        
        return list(set(identifiers))  # Remove duplicates
    
    def _assess_company_mentions(self, text: str, identifiers: List[str]) -> float:
        """Assess how prominently the company is mentioned."""
        if not text:
            return 0.0
        
        mention_score = 0.0
        total_mentions = 0
        
        for identifier in identifiers:
            if not identifier:
                continue
                
            # Count exact matches (higher weight)
            exact_matches = text.count(identifier)
            total_mentions += exact_matches
            
            # Title mentions get extra weight
            title_mentions = text[:100].count(identifier)  # Approximate title
            mention_score += title_mentions * 0.3
            
            # Word boundary matches (prevent partial word matches)
            import re
            word_boundary_pattern = r'\b' + re.escape(identifier) + r'\b'
            word_matches = len(re.findall(word_boundary_pattern, text, re.IGNORECASE))
            mention_score += word_matches * 0.2
        
        # Normalize by text length and apply diminishing returns
        text_words = len(text.split())
        if text_words > 0:
            mention_density = total_mentions / text_words
            mention_score += mention_density * 10  # Scale up density
        
        # Apply diminishing returns for very high mention counts
        mention_score = min(mention_score, 1.0)
        
        return mention_score
    
    def _assess_financial_context(self, text: str) -> float:
        """Assess financial and business context in the text."""
        if not text:
            return 0.0
        
        context_score = 0.0
        
        # 1. Financial keyword scoring
        for keyword, weight in self.financial_keywords.items():
            if keyword in text:
                context_score += weight * 0.1
        
        # 2. Financial pattern matching
        import re
        for pattern in self.financial_patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            context_score += matches * 0.15
        
        # 3. Business context phrases
        business_phrases = [
            'quarterly results', 'annual report', 'sec filing', 'press release',
            'financial results', 'business update', 'market share', 'competitive',
            'revenue growth', 'margin expansion', 'cost reduction', 'strategic',
            'board of directors', 'shareholder', 'investor', 'wall street'
        ]
        
        for phrase in business_phrases:
            if phrase in text:
                context_score += 0.1
        
        # Normalize and apply bounds
        context_score = min(context_score, 1.0)
        
        return context_score
    
    def _assess_content_quality(self, article: Dict, text: str) -> float:
        """Assess the quality and depth of content."""
        quality_score = 0.0
        
        # Length-based quality (longer articles often have more substance)
        text_length = len(text)
        if text_length > 500:
            quality_score += 0.3
        elif text_length > 200:
            quality_score += 0.2
        elif text_length > 100:
            quality_score += 0.1
        
        # Source type bonuses
        source_type = article.get('source_type', '')
        if source_type == 'alphavantage_premium':
            quality_score += 0.4  # Full content + sentiment
        elif source_type == 'nyt_api':
            quality_score += 0.3  # Full abstracts
        elif source_type == 'rss_feed':
            quality_score += 0.2  # Enhanced RSS content
        
        # Full content availability
        if article.get('full_content') and len(article['full_content']) > 300:
            quality_score += 0.2
        
        # Sentiment data availability (AlphaVantage)
        if article.get('sentiment_label') and article.get('sentiment_score') is not None:
            quality_score += 0.1
        
        return min(quality_score, 1.0)
    
    def _assess_source_quality(self, article: Dict) -> float:
        """Assess the quality of the source."""
        source = article.get('source', '').lower()
        
        # Premium source weights
        premium_sources = {
            'bloomberg.com': 1.0,
            'reuters.com': 1.0,
            'wsj.com': 0.95,
            'ft.com': 0.9,
            'nytimes.com': 0.9,
            'barrons.com': 0.85,
            'cnbc.com': 0.8,
            'marketwatch.com': 0.75,
            'fortune.com': 0.7,
            'businessinsider.com': 0.6
        }
        
        return premium_sources.get(source, 0.3)  # Default for other sources
    
    def _check_negative_indicators(self, text: str) -> float:
        """Check for indicators that reduce relevance."""
        penalty = 0.0
        
        for indicator in self.negative_indicators:
            if indicator in text:
                penalty += 0.1
        
        return min(penalty, 0.5)  # Cap penalty at 0.5

class DynamicSourceOrchestrator:
    """
    Intelligent orchestration of news sources with dynamic decision-making.
    Decides when to use Google CSE based on relevance assessment, not just quantity.
    """
    
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.relevance_assessor = RelevanceAssessor(config)
    
    def fetch_enhanced_news_with_dynamic_cse(self, company: str, days_back: int = 7) -> Dict[str, Any]:
        """
        Enhanced news fetching with dynamic Google CSE integration.
        
        This is the main orchestration function that implements the enhanced logic:
        1. Fetch from premium sources (AlphaVantage, NYT, RSS)
        2. Assess relevance of fetched articles
        3. Dynamically decide whether to use Google CSE
        4. Intelligently combine and prioritize results
        """
        
        start_time = time.time()
        logger.info(f"🚀 Starting enhanced dynamic analysis for {company}")
        
        # Get company identifiers for better relevance assessment
        ticker, company_name = self._resolve_company_identifiers(company)
        
        all_articles = []
        source_performance = {}
        relevance_metrics = {}
        
        # Phase 1: Fetch from Premium Sources
        logger.info("📊 Phase 1: Fetching from premium sources...")
        
        # 1.1 AlphaVantage (highest priority - full content + sentiment)
        alphavantage_articles = self._fetch_alphavantage_with_relevance(
            company, ticker, company_name, days_back
        )
        all_articles.extend(alphavantage_articles)
        source_performance['alphavantage'] = len(alphavantage_articles)
        
        # 1.2 NYT API (full abstracts)
        nyt_articles = self._fetch_nyt_with_relevance(
            company, ticker, company_name, days_back, 
            existing_urls={a.get('link', '') for a in all_articles}
        )
        all_articles.extend(nyt_articles)
        source_performance['nyt'] = len(nyt_articles)
        
        # 1.3 Premium RSS Feeds
        rss_articles = self._fetch_rss_with_relevance(
            company, ticker, company_name, days_back,
            existing_urls={a.get('link', '') for a in all_articles}
        )
        all_articles.extend(rss_articles)
        source_performance['rss'] = len(rss_articles)
        
        # Phase 2: Relevance Assessment and Dynamic Decision Making
        logger.info("🧠 Phase 2: Assessing relevance and making dynamic decisions...")
        
        # Assess relevance of all premium articles
        relevant_articles, relevance_stats = self._assess_article_batch_relevance(
            all_articles, company, ticker, company_name
        )
        
        relevance_metrics.update(relevance_stats)
        
        # Decision logic for Google CSE
        should_use_google_cse = self._should_trigger_google_cse(
            all_articles, relevant_articles, relevance_stats
        )
        
        # Phase 3: Conditional Google CSE Fetch
        google_articles = []
        if should_use_google_cse:
            logger.info("🔍 Phase 3: Triggering Google CSE for gap-filling...")
            google_articles = self._fetch_google_cse_targeted(
                company, ticker, company_name, days_back,
                existing_urls={a.get('link', '') for a in all_articles},
                gap_analysis=relevance_stats
            )
            all_articles.extend(google_articles)
            source_performance['google_cse'] = len(google_articles)
        else:
            logger.info("✅ Phase 3: Skipping Google CSE - sufficient relevant premium content")
            source_performance['google_cse'] = 0
        
        # Phase 4: Final Article Selection and Ranking
        logger.info("🎯 Phase 4: Final selection and ranking...")
        
        # Final relevance assessment including Google articles
        if google_articles:
            final_relevant_articles, final_relevance_stats = self._assess_article_batch_relevance(
                all_articles, company, ticker, company_name
            )
            relevance_metrics.update(final_relevance_stats)
        else:
            final_relevant_articles = relevant_articles
        
        # Intelligent article selection with enhanced scoring
        selected_articles = self._select_final_articles(
            all_articles, final_relevant_articles, company, ticker, company_name
        )
        
        # Phase 5: Generate Analysis
        logger.info("📝 Phase 5: Generating enhanced analysis...")
        
        summaries = {}
        if selected_articles:
            summaries = self._generate_enhanced_analysis(
                company, selected_articles, relevance_metrics
            )
        
        # Calculate final metrics
        response_time = time.time() - start_time
        final_metrics = self._calculate_enhanced_metrics(
            selected_articles, source_performance, relevance_metrics, response_time
        )
        
        # Enhanced logging
        self._log_enhanced_results(company, final_metrics, source_performance, relevance_metrics)
        
        return {
            'company': company,
            'resolved_ticker': ticker,
            'resolved_company_name': company_name,
            'articles': selected_articles,
            'summaries': summaries,
            'metrics': final_metrics,
            'source_performance': source_performance,
            'relevance_metrics': relevance_metrics,
            'google_cse_triggered': should_use_google_cse,
            'success': len(selected_articles) > 0
        }
    
    def _resolve_company_identifiers(self, company: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolve company input to ticker and company name."""
        try:
            # Use existing company ticker service
            from company_ticker_service import fast_company_ticker_service
            return fast_company_ticker_service.get_both_ticker_and_company(company)
        except ImportError:
            logger.warning("Company ticker service not available, using basic resolution")
            # Basic fallback logic
            if len(company) <= 5 and company.isupper():
                return company, None
            else:
                return None, company
    
    def _fetch_alphavantage_with_relevance(self, company: str, ticker: Optional[str], 
                                         company_name: Optional[str], days_back: int) -> List[Dict]:
        """Fetch AlphaVantage articles with immediate relevance filtering."""
        try:
            # Use existing AlphaVantage function
            from news_utils import fetch_alphavantage_news_enhanced
            articles = fetch_alphavantage_news_enhanced(company, days_back)
            
            # Apply immediate relevance filtering
            relevant_articles = []
            for article in articles:
                relevance = self.relevance_assessor.assess_article_relevance(
                    article, company, ticker, company_name
                )
                # Only keep articles with decent relevance
                if relevance['overall_relevance'] >= 0.3 or relevance['is_company_specific']:
                    article['relevance_assessment'] = relevance
                    relevant_articles.append(article)
            
            logger.info(f"AlphaVantage: {len(articles)} raw → {len(relevant_articles)} relevant")
            return relevant_articles
            
        except Exception as e:
            logger.error(f"AlphaVantage with relevance failed: {e}")
            return []
    
    def _fetch_nyt_with_relevance(self, company: str, ticker: Optional[str], 
                                company_name: Optional[str], days_back: int,
                                existing_urls: set) -> List[Dict]:
        """Fetch NYT articles with relevance filtering."""
        try:
            # Use existing NYT function
            from news_utils import fetch_nyt_news_working
            articles = fetch_nyt_news_working(company, days_back, max_articles=100)
            
            # Deduplicate and filter
            relevant_articles = []
            for article in articles:
                if article.get('link', '') in existing_urls:
                    continue
                
                relevance = self.relevance_assessor.assess_article_relevance(
                    article, company, ticker, company_name
                )
                
                # NYT has higher quality threshold
                if relevance['overall_relevance'] >= 0.4 or relevance['is_company_specific']:
                    article['relevance_assessment'] = relevance
                    relevant_articles.append(article)
            
            logger.info(f"NYT: {len(articles)} raw → {len(relevant_articles)} relevant")
            return relevant_articles
            
        except Exception as e:
            logger.error(f"NYT with relevance failed: {e}")
            return []
    
    def _fetch_rss_with_relevance(self, company: str, ticker: Optional[str], 
                                company_name: Optional[str], days_back: int,
                                existing_urls: set) -> List[Dict]:
        """Fetch RSS articles with relevance filtering."""
        try:
            # Use existing RSS function
            from news_utils import fetch_rss_feeds_working_2025_parallel
            articles = fetch_rss_feeds_working_2025_parallel(company, days_back)
            
            # Deduplicate and filter
            relevant_articles = []
            for article in articles:
                if article.get('link', '') in existing_urls:
                    continue
                
                relevance = self.relevance_assessor.assess_article_relevance(
                    article, company, ticker, company_name
                )
                
                # RSS articles need reasonable relevance
                if relevance['overall_relevance'] >= 0.35 or relevance['is_company_specific']:
                    article['relevance_assessment'] = relevance
                    relevant_articles.append(article)
            
            logger.info(f"RSS: {len(articles)} raw → {len(relevant_articles)} relevant")
            return relevant_articles
            
        except Exception as e:
            logger.error(f"RSS with relevance failed: {e}")
            return []
    
    def _assess_article_batch_relevance(self, articles: List[Dict], company: str, 
                                      ticker: Optional[str], company_name: Optional[str]) -> Tuple[List[Dict], Dict]:
        """Assess relevance for a batch of articles and return statistics."""
        
        relevant_articles = []
        total_articles = len(articles)
        
        relevance_scores = []
        company_specific_count = 0
        source_relevance = {}
        
        for article in articles:
            # Skip if already assessed
            if 'relevance_assessment' in article:
                relevance = article['relevance_assessment']
            else:
                relevance = self.relevance_assessor.assess_article_relevance(
                    article, company, ticker, company_name
                )
                article['relevance_assessment'] = relevance
            
            relevance_scores.append(relevance['overall_relevance'])
            
            if relevance['is_company_specific']:
                company_specific_count += 1
                relevant_articles.append(article)
            
            # Track by source
            source = article.get('source', 'unknown')
            if source not in source_relevance:
                source_relevance[source] = {'total': 0, 'relevant': 0}
            source_relevance[source]['total'] += 1
            if relevance['is_company_specific']:
                source_relevance[source]['relevant'] += 1
        
        # Calculate statistics
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0
        relevance_percentage = (company_specific_count / total_articles) if total_articles > 0 else 0
        
        stats = {
            'total_articles': total_articles,
            'relevant_articles': company_specific_count,
            'relevance_percentage': relevance_percentage,
            'average_relevance_score': avg_relevance,
            'source_relevance_breakdown': source_relevance
        }
        
        return relevant_articles, stats
    
    def _should_trigger_google_cse(self, all_articles: List[Dict], 
                                 relevant_articles: List[Dict], 
                                 relevance_stats: Dict) -> bool:
        """
        Dynamic decision making for Google CSE trigger.
        This is the core logic that replaces quantity-based with relevance-based decisions.
        """
        
        total_articles = len(all_articles)
        relevant_count = len(relevant_articles)
        relevance_percentage = relevance_stats.get('relevance_percentage', 0)
        
        logger.info(f"CSE Decision Analysis:")
        logger.info(f"  • Total articles: {total_articles}")
        logger.info(f"  • Relevant articles: {relevant_count}")
        logger.info(f"  • Relevance percentage: {relevance_percentage:.1%}")
        
        # Decision criteria (multiple conditions must be met)
        
        # 1. Check if we have sufficient relevant articles from premium sources
        has_sufficient_relevant = relevant_count >= self.config.MIN_RELEVANT_PREMIUM_ARTICLES_BEFORE_CSE
        
        # 2. Check if relevance percentage is acceptable
        has_good_relevance_rate = relevance_percentage >= self.config.MIN_RELEVANT_PERCENTAGE
        
        # 3. Check source diversity (ensure we're not over-reliant on one source)
        source_diversity = len(set(a.get('source', '') for a in relevant_articles))
        has_source_diversity = source_diversity >= 3
        
        # 4. Special case: very few total articles (might be niche company)
        is_low_volume_company = total_articles < 15
        
        # Decision logic
        if has_sufficient_relevant and has_good_relevance_rate and has_source_diversity:
            decision = False
            reason = f"Sufficient relevant premium content ({relevant_count} relevant, {relevance_percentage:.1%} rate, {source_diversity} sources)"
        elif is_low_volume_company:
            decision = True
            reason = f"Low volume company detected ({total_articles} total articles) - using CSE for comprehensive coverage"
        elif relevant_count < self.config.MIN_RELEVANT_PREMIUM_ARTICLES_BEFORE_CSE:
            decision = True
            reason = f"Insufficient relevant articles ({relevant_count} < {self.config.MIN_RELEVANT_PREMIUM_ARTICLES_BEFORE_CSE})"
        elif relevance_percentage < self.config.MIN_RELEVANT_PERCENTAGE:
            decision = True
            reason = f"Low relevance rate ({relevance_percentage:.1%} < {self.config.MIN_RELEVANT_PERCENTAGE:.1%})"
        else:
            decision = False
            reason = "Edge case - defaulting to no CSE"
        
        logger.info(f"🎯 CSE Decision: {'TRIGGER' if decision else 'SKIP'} - {reason}")
        
        return decision
    
    def _fetch_google_cse_targeted(self, company: str, ticker: Optional[str], 
                                 company_name: Optional[str], days_back: int,
                                 existing_urls: set, gap_analysis: Dict) -> List[Dict]:
        """Fetch Google CSE articles with targeted queries based on gap analysis."""
        try:
            # Use existing Google search function
            from news_utils import fetch_google_news
            articles = fetch_google_news(company, days_back)
            
            # Enhanced relevance filtering for Google articles
            relevant_articles = []
            for article in articles:
                if article.get('link', '') in existing_urls:
                    continue
                
                relevance = self.relevance_assessor.assess_article_relevance(
                    article, company, ticker, company_name
                )
                
                # Higher threshold for Google articles to maintain quality
                if relevance['overall_relevance'] >= 0.5 or relevance['is_company_specific']:
                    article['relevance_assessment'] = relevance
                    relevant_articles.append(article)
            
            # Limit Google articles to avoid overwhelming premium content
            max_google_articles = min(10, self.config.TARGET_ARTICLE_COUNT - gap_analysis.get('relevant_articles', 0))
            relevant_articles = relevant_articles[:max_google_articles]
            
            logger.info(f"Google CSE: {len(articles)} raw → {len(relevant_articles)} relevant (limited to {max_google_articles})")
            return relevant_articles
            
        except Exception as e:
            logger.error(f"Google CSE targeted fetch failed: {e}")
            return []
    
    def _select_final_articles(self, all_articles: List[Dict], relevant_articles: List[Dict],
                             company: str, ticker: Optional[str], company_name: Optional[str]) -> List[Dict]:
        """Intelligent final article selection with enhanced prioritization."""
        
        # Start with relevant articles as the base
        priority_articles = relevant_articles.copy()
        
        # Add enhanced scoring to all articles
        for article in all_articles:
            enhanced_score = self._calculate_enhanced_article_score(article, company, ticker, company_name)
            article['enhanced_score'] = enhanced_score
        
        # Sort by enhanced score
        all_articles.sort(key=lambda x: x.get('enhanced_score', 0), reverse=True)
        
        # Ensure we have at least target article count if possible
        if len(priority_articles) < self.config.TARGET_ARTICLE_COUNT:
            # Add best non-relevant articles to reach target
            needed = self.config.TARGET_ARTICLE_COUNT - len(priority_articles)
            additional_articles = [
                a for a in all_articles 
                if a not in priority_articles and a.get('enhanced_score', 0) > 0.3
            ][:needed]
            priority_articles.extend(additional_articles)
        
        # Final sort and limit
        priority_articles.sort(key=lambda x: x.get('enhanced_score', 0), reverse=True)
        final_articles = priority_articles[:self.config.TARGET_ARTICLE_COUNT]
        
        logger.info(f"Final selection: {len(final_articles)} articles selected from {len(all_articles)} total")
        
        return final_articles
    
    def _calculate_enhanced_article_score(self, article: Dict, company: str, 
                                        ticker: Optional[str], company_name: Optional[str]) -> float:
        """Calculate enhanced scoring that considers relevance, source quality, and content."""
        
        score = 0.0
        
        # Base relevance score
        relevance = article.get('relevance_assessment', {})
        if relevance:
            score += relevance.get('overall_relevance', 0) * 0.4
            if relevance.get('is_company_specific', False):
                score += 0.2  # Bonus for company-specific articles
        
        # Source type bonuses
        source_type = article.get('source_type', '')
        source_weights = {
            'alphavantage_premium': self.config.ALPHAVANTAGE_WEIGHT,
            'nyt_api': self.config.NYT_WEIGHT,
            'rss_feed': self.config.PREMIUM_RSS_WEIGHT,
            'google_search': self.config.GOOGLE_CSE_WEIGHT
        }
        source_weight = source_weights.get(source_type, 1.0)
        score = score * source_weight
        
        # Premium source bonus
        source = article.get('source', '').lower()
        premium_sources = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'nytimes.com']
        if source in premium_sources:
            score += 0.2
        
        # Content quality bonus
        if article.get('full_content') and len(article['full_content']) > 300:
            score += 0.1
        
        # Sentiment data bonus (AlphaVantage)
        if article.get('sentiment_label') and article.get('sentiment_score') is not None:
            score += 0.1
        
        return min(score, 2.0)  # Cap at 2.0
    
    def _generate_enhanced_analysis(self, company: str, articles: List[Dict], 
                                  relevance_metrics: Dict) -> Dict[str, List[str]]:
        """Generate analysis with enhanced context from relevance assessment."""
        try:
            # Use existing analysis function but with enhanced context
            from news_utils import generate_premium_analysis_30_articles
            return generate_premium_analysis_30_articles(company, articles)
        except ImportError:
            # Fallback analysis
            return {
                "executive": [f"Analysis of {len(articles)} articles for {company} with enhanced relevance filtering"],
                "investor": [f"Relevance rate: {relevance_metrics.get('relevance_percentage', 0):.1%} - indicating {'high' if relevance_metrics.get('relevance_percentage', 0) > 0.6 else 'moderate'} company-specific coverage"],
                "catalysts": [f"Dynamic source selection used - {'Google CSE triggered' if relevance_metrics.get('google_cse_triggered', False) else 'Premium sources sufficient'}"]
            }
    
    def _calculate_enhanced_metrics(self, articles: List[Dict], source_performance: Dict,
                                  relevance_metrics: Dict, response_time: float) -> Dict:
        """Calculate comprehensive metrics including relevance information."""
        
        total_articles = len(articles)
        
        # Source breakdown
        alphavantage_count = sum(1 for a in articles if a.get('source_type') == 'alphavantage_premium')
        nyt_count = sum(1 for a in articles if a.get('source_type') == 'nyt_api')
        rss_count = sum(1 for a in articles if a.get('source_type') == 'rss_feed')
        google_count = sum(1 for a in articles if a.get('source_type') == 'google_search')
        
        # Premium sources
        premium_sources = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'nytimes.com']
        premium_count = sum(1 for a in articles if a.get('source', '') in premium_sources)
        
        # Relevance metrics
        relevant_count = sum(1 for a in articles if a.get('relevance_assessment', {}).get('is_company_specific', False))
        avg_relevance = sum(a.get('relevance_assessment', {}).get('overall_relevance', 0) for a in articles) / total_articles if total_articles > 0 else 0
        
        # Quality determination with relevance consideration
        if avg_relevance >= 0.7 and alphavantage_count >= 8:
            analysis_quality = "Premium+"
        elif avg_relevance >= 0.6 and relevant_count >= 10:
            analysis_quality = "Institutional"
        elif avg_relevance >= 0.5 and relevant_count >= 6:
            analysis_quality = "Professional"
        elif relevant_count >= 3:
            analysis_quality = "Standard"
        else:
            analysis_quality = "Limited"
        
        return {
            'total_articles': total_articles,
            'alphavantage_articles': alphavantage_count,
            'nyt_articles': nyt_count,
            'rss_articles': rss_count,
            'google_articles': google_count,
            'premium_sources_count': premium_count,
            'relevant_articles': relevant_count,
            'relevance_percentage': (relevant_count / total_articles * 100) if total_articles > 0 else 0,
            'average_relevance_score': round(avg_relevance, 3),
            'alphavantage_coverage': (alphavantage_count / total_articles * 100) if total_articles > 0 else 0,
            'premium_coverage': (premium_count / total_articles * 100) if total_articles > 0 else 0,
            'analysis_quality': analysis_quality,
            'response_time': response_time,
            'enhanced_scoring_used': True,
            'dynamic_cse_logic_used': True
        }
    
    def _log_enhanced_results(self, company: str, metrics: Dict, 
                            source_performance: Dict, relevance_metrics: Dict):
        """Enhanced logging with detailed relevance information."""
        
        logger.info(f"🎯 ENHANCED ANALYSIS COMPLETE for {company}:")
        logger.info(f"   • Total articles: {metrics['total_articles']}")
        logger.info(f"   • Relevant articles: {metrics['relevant_articles']} ({metrics['relevance_percentage']:.1f}%)")
        logger.info(f"   • Average relevance: {metrics['average_relevance_score']:.3f}")
        logger.info(f"   • Source breakdown: AV={metrics['alphavantage_articles']}, NYT={metrics['nyt_articles']}, RSS={metrics['rss_articles']}, Google={metrics['google_articles']}")
        logger.info(f"   • Premium coverage: {metrics['premium_coverage']:.1f}%")
        logger.info(f"   • Analysis quality: {metrics['analysis_quality']}")
        logger.info(f"   • Response time: {metrics['response_time']:.2f}s")

# Example usage and testing
if __name__ == "__main__":
    # Test with a well-known company
    print("Testing with well-known company (Apple)...")
    apple_results = fetch_enhanced_news_with_dynamic_relevance_assessment("AAPL", 7)
    print(f"Apple: {apple_results['metrics']['total_articles']} articles, {apple_results['metrics']['relevance_percentage']:.1f}% relevant")
    print(f"Google CSE triggered: {apple_results['google_cse_triggered']}")
    
    # Test with a lesser-known company
    print("\nTesting with lesser-known company (ONTO)...")
    onto_results = fetch_enhanced_news_with_dynamic_relevance_assessment("ONTO", 7)
    print(f"ONTO: {onto_results['metrics']['total_articles']} articles, {onto_results['metrics']['relevance_percentage']:.1f}% relevant")
    print(f"Google CSE triggered: {onto_results['google_cse_triggered']}")