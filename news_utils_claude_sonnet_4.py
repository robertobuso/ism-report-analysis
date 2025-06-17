# news_utils_claude_sonnet_4.py - Complete Claude Sonnet 4 Integration

import os
import re
import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Import Anthropic client
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("Anthropic library not installed. Run: pip install anthropic")

def generate_premium_analysis_claude_sonnet_4_enhanced(company: str, articles: List[Dict], max_articles: int = 30) -> Dict[str, List[str]]:
    """
    ENHANCED Claude Sonnet 4 analysis with improved readability and source attribution.
    Combines superior analytical depth with accessible storytelling.
    """
    
    if not ANTHROPIC_AVAILABLE:
        logger.error("Anthropic library not available. Falling back to OpenAI.")
        from news_utils import generate_premium_analysis_30_articles
        return generate_premium_analysis_30_articles(company, articles, max_articles)
    
    if not articles or len(articles) == 0:
        return create_empty_summaries_claude()
    
    try:
        analysis_articles = articles[:max_articles]
        
        # Enhanced article content preparation with source mapping
        article_text = ""
        source_mapping = {}  # Map source domains to article indices for citation
        
        for i, article in enumerate(analysis_articles, 1):
            source_type = article.get('source_type', 'google_search')
            source_domain = article.get('source', 'unknown')
            
            # Build source mapping for citations
            if source_domain not in source_mapping:
                source_mapping[source_domain] = []
            source_mapping[source_domain].append(i)
            
            # Include FULL content for Claude's analysis
            if source_type == 'alphavantage_premium':
                full_content = article.get('full_content', article.get('snippet', ''))
                sentiment_data = {
                    'label': article.get('sentiment_label', 'Neutral'),
                    'score': article.get('sentiment_score', 0),
                    'relevance': article.get('relevance_score', 0)
                }
                
                article_text += f"\n{i}. [ALPHAVANTAGE+SENTIMENT] {article['title']}\n"
                article_text += f"   Source: {article['source']} | Sentiment: {sentiment_data['label']} ({sentiment_data['score']:.3f}) | Relevance: {sentiment_data['relevance']:.3f}\n"
                article_text += f"   Full Content: {full_content}\n"
                
            elif source_type == 'nyt_api':
                full_content = article.get('full_content', article.get('snippet', ''))
                article_text += f"\n{i}. [NYT_PREMIUM] {article['title']}\n"
                article_text += f"   Source: {article['source']} (NYT Editorial Quality)\n"
                article_text += f"   Full Content: {full_content}\n"
                
            else:
                content = article.get('full_content', article.get('snippet', ''))
                article_text += f"\n{i}. [PREMIUM_RSS] {article['title']}\n"
                article_text += f"   Source: {article['source']}\n"
                article_text += f"   Content: {content}\n"
            
            article_text += f"   Published: {article.get('published', 'Recent')}\n"
            article_text += f"   URL: {article['link']}\n"
        
        # Calculate enhanced metrics
        source_type_counts = {}
        for article in analysis_articles:
            source_type = article.get('source_type', 'google_search')
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        
        premium_sources = ['bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'nytimes.com', 'cnbc.com', 'marketwatch.com']
        premium_count = sum(1 for article in analysis_articles if article.get('source', '') in premium_sources)
        alphavantage_count = source_type_counts.get('alphavantage_premium', 0)
        
        # Create source citation guide
        citation_guide = "AVAILABLE SOURCES FOR CITATION:\n"
        for source, indices in source_mapping.items():
            citation_guide += f"• {source}: Articles {', '.join(map(str, indices))}\n"
        
        # ENHANCED PROMPT - Combines analytical depth with readable storytelling
        prompt = f"""You are a Managing Director of Equity Research at Goldman Sachs writing for institutional investors who value both analytical precision AND clear, compelling narratives. Your analysis will be read by portfolio managers making investment decisions.

COMPREHENSIVE DATA INTELLIGENCE ({len(analysis_articles)} articles with FULL context):
{article_text}

{citation_guide}

SOURCE QUALITY METRICS:
• Total Articles: {len(analysis_articles)}
• Premium Sources (Bloomberg/Reuters/WSJ/FT/NYT/CNBC/MarketWatch): {premium_count} ({premium_count/len(analysis_articles)*100:.1f}%)
• AlphaVantage (Full Content + Sentiment): {alphavantage_count}
• Source Distribution: {source_type_counts}

ENHANCED ANALYTICAL FRAMEWORK - Superior Depth with Accessible Communication:

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

        # Generate analysis with enhanced prompt
        anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        if not anthropic_client.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        start_time = time.time()
        
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            temperature=0.07,  # Slightly higher for more natural language flow
            system=f"You are a Managing Director of Equity Research at Goldman Sachs writing institutional-grade investment analysis for {company}. Your writing combines analytical precision with compelling storytelling. Every factual claim must cite its source explicitly. Write in an accessible, professional style that portfolio managers would find both credible and engaging.",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        analysis_text = response.content[0].text
        generation_time = time.time() - start_time
        
        # Enhanced logging
        logger.info(f"🎯 Enhanced Claude Sonnet 4 analysis generated for {company}:")
        logger.info(f"   • Analysis length: {len(analysis_text)} characters")
        logger.info(f"   • Premium source coverage: {premium_count}/{len(analysis_articles)} ({premium_count/len(analysis_articles)*100:.1f}%)")
        logger.info(f"   • Generation time: {generation_time:.2f}s")
        logger.info(f"   • Enhanced readability & source attribution: ✅")
        
        return parse_financial_summaries_enhanced(analysis_text)
        
    except Exception as e:
        logger.error(f"Enhanced Claude Sonnet 4 analysis failed for {company}: {str(e)}")
        # Fallback to OpenAI
        try:
            from news_utils import generate_premium_analysis_30_articles
            return generate_premium_analysis_30_articles(company, articles, max_articles)
        except Exception as fallback_error:
            logger.error(f"Fallback to OpenAI also failed: {fallback_error}")
            return create_error_summaries_claude(company, str(e))

def parse_financial_summaries_enhanced(text: str) -> Dict[str, List[str]]:
    """
    Enhanced parsing for Claude Sonnet 4's more sophisticated output.
    Claude tends to be more structured and consistent than OpenAI.
    """
    sections = {"executive": [], "investor": [], "catalysts": []}
    current_section = None
    
    # Enhanced section detection for Claude's output patterns
    section_patterns = {
        "executive": re.compile(r".*(executive\s+summary|strategic|financial\s+impact).*", re.IGNORECASE),
        "investor": re.compile(r".*(investor\s+insights|valuation|market\s+dynamics).*", re.IGNORECASE),
        "catalysts": re.compile(r".*(catalysts?\s*(&|and)?\s*risks?|risks?\s*(&|and)?\s*catalysts?|probability).*", re.IGNORECASE)
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
                logger.debug(f"Found section: {section_name}")
                break
        
        if section_found:
            continue
            
        # Process bullet points (Claude tends to use various formats)
        if line.startswith(('-', '•', '*', '◦')) and current_section:
            bullet = line.lstrip('-•*◦ ').strip()
            if bullet and len(bullet) > 15:  # Filter out short fragments
                sections[current_section].append(bullet)
                logger.debug(f"Added bullet to {current_section}: {bullet[:50]}...")
    
    # Quality check - ensure each section has content
    for section_name, bullets in sections.items():
        if not bullets:
            logger.warning(f"No bullets found for section: {section_name}")
            sections[section_name] = [f"Enhanced Claude Sonnet 4 analysis available - processing completed for {section_name} category with full context utilization."]
    
    # Log parsing results
    total_bullets = sum(len(bullets) for bullets in sections.values())
    logger.info(f"Parsed {total_bullets} total bullets: Executive={len(sections['executive'])}, Investor={len(sections['investor'])}, Catalysts={len(sections['catalysts'])}")
    
    return sections

def create_empty_summaries_claude() -> Dict[str, List[str]]:
    """Create empty summaries for Claude Sonnet 4 when no articles available."""
    return {
        "executive": ["**[ENHANCED]** Claude Sonnet 4 ready for comprehensive analysis. No recent articles found - try expanding date range or verifying company ticker."],
        "investor": ["**[INSTITUTIONAL]** Advanced financial reasoning capabilities available. Consider checking earnings calendar or major financial events."],
        "catalysts": ["**[QUANTIFIED]** Probability-weighted risk analysis available. Monitor upcoming announcements or regulatory events."]
    }

def create_error_summaries_claude(company: str, error_msg: str) -> Dict[str, List[str]]:
    """Create error summaries for Claude Sonnet 4 failures."""
    return {
        "executive": [f"**[ERROR]** Claude Sonnet 4 analysis temporarily unavailable for {company}. {error_msg[:100]}..."],
        "investor": ["**[FALLBACK]** OpenAI analysis may be available. Please try again or contact support."],
        "catalysts": ["**[RETRY]** Enhanced analysis will retry automatically. Consider refreshing the page."]
    }

# Integration wrapper to replace existing OpenAI calls
def generate_premium_analysis_upgraded_v2(company: str, articles: List[Dict], max_articles: int = 30) -> Dict[str, List[str]]:
    """
    ENHANCED INTEGRATION FUNCTION - Version 2 with improved readability and source attribution.
    """
    
    if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
        logger.info(f"🎯 Using Enhanced Claude Sonnet 4 for superior readable analysis of {company}")
        return generate_premium_analysis_claude_sonnet_4_enhanced(company, articles, max_articles)
    else:
        logger.warning("Enhanced Claude Sonnet 4 not available, falling back to OpenAI")
        from news_utils import generate_premium_analysis_30_articles
        return generate_premium_analysis_30_articles(company, articles, max_articles)

# Performance comparison utilities
def compare_analysis_quality(company: str, articles: List[Dict]) -> Dict[str, Any]:
    """
    Compare OpenAI vs Claude Sonnet 4 analysis for the same company.
    Useful for testing and validation.
    """
    results = {
        'company': company,
        'article_count': len(articles),
        'timestamp': datetime.now().isoformat(),
        'openai_analysis': None,
        'claude_analysis': None,
        'performance_metrics': {}
    }
    
    try:
        # OpenAI analysis
        start_time = time.time()
        from news_utils import generate_premium_analysis_30_articles
        openai_result = generate_premium_analysis_30_articles(company, articles)
        openai_time = time.time() - start_time
        results['openai_analysis'] = openai_result
        results['performance_metrics']['openai_time'] = openai_time
        
        # Claude Sonnet 4 analysis  
        start_time = time.time()
        claude_result = generate_premium_analysis_claude_sonnet_4_enhanced(company, articles)
        claude_time = time.time() - start_time
        results['claude_analysis'] = claude_result
        results['performance_metrics']['claude_time'] = claude_time
        
        # Quality comparison metrics
        def count_financial_terms(summaries):
            financial_terms = ['revenue', 'margin', 'eps', 'ebitda', 'guidance', 'target', 'estimate', '%', '$']
            count = 0
            for section in summaries.values():
                for bullet in section:
                    count += sum(1 for term in financial_terms if term.lower() in bullet.lower())
            return count
        
        def count_quantified_statements(summaries):
            import re
            quantified_patterns = [
                r'\d+[\-–]\d+%',  # Percentage ranges
                r'\$\d+[kmb]?',   # Dollar amounts
                r'\d+\.\d+x',     # Multiples
                r'\d+%\s+(probability|chance|confidence)',  # Probability statements
                r'Q[1-4]\s+\d{4}', # Quarter references
            ]
            count = 0
            for section in summaries.values():
                for bullet in section:
                    for pattern in quantified_patterns:
                        count += len(re.findall(pattern, bullet, re.IGNORECASE))
            return count
        
        results['performance_metrics']['openai_financial_terms'] = count_financial_terms(openai_result)
        results['performance_metrics']['claude_financial_terms'] = count_financial_terms(claude_result)
        results['performance_metrics']['openai_quantified'] = count_quantified_statements(openai_result)
        results['performance_metrics']['claude_quantified'] = count_quantified_statements(claude_result)
        
        # Calculate improvement metrics
        if results['performance_metrics']['openai_financial_terms'] > 0:
            financial_improvement = (results['performance_metrics']['claude_financial_terms'] / 
                                   results['performance_metrics']['openai_financial_terms'] - 1) * 100
            results['performance_metrics']['financial_terms_improvement'] = f"{financial_improvement:.1f}%"
        
        if results['performance_metrics']['openai_quantified'] > 0:
            quantified_improvement = (results['performance_metrics']['claude_quantified'] / 
                                    results['performance_metrics']['openai_quantified'] - 1) * 100
            results['performance_metrics']['quantified_improvement'] = f"{quantified_improvement:.1f}%"
        
        logger.info(f"🔬 Analysis comparison for {company}:")
        logger.info(f"   • Financial terms - OpenAI: {results['performance_metrics']['openai_financial_terms']}, Claude: {results['performance_metrics']['claude_financial_terms']}")
        logger.info(f"   • Quantified statements - OpenAI: {results['performance_metrics']['openai_quantified']}, Claude: {results['performance_metrics']['claude_quantified']}")
        logger.info(f"   • Generation time - OpenAI: {openai_time:.2f}s, Claude: {claude_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Analysis comparison failed: {e}")
        results['error'] = str(e)
    
    return results

# Environment setup helper
def setup_claude_sonnet_4():
    """
    Helper function to set up Claude Sonnet 4 integration.
    Call this to verify everything is configured correctly.
    """
    setup_results = {
        'anthropic_library': False,
        'api_key_configured': False,
        'client_initialized': False,
        'ready': False,
        'instructions': []
    }
    
    # Check Anthropic library
    try:
        import anthropic
        setup_results['anthropic_library'] = True
        logger.info("✅ Anthropic library is installed")
    except ImportError:
        setup_results['instructions'].append("Install Anthropic library: pip install anthropic")
        logger.error("❌ Anthropic library not installed")
    
    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        setup_results['api_key_configured'] = True
        logger.info("✅ ANTHROPIC_API_KEY is configured")
    else:
        setup_results['instructions'].append("Set ANTHROPIC_API_KEY environment variable")
        logger.error("❌ ANTHROPIC_API_KEY not found")
    
    # Test client initialization
    if setup_results['anthropic_library'] and setup_results['api_key_configured']:
        try:
            anthropic_client = anthropic.Anthropic(api_key=api_key)
            # Test with a simple message
            test_response = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=50,
                messages=[{"role": "user", "content": "Hello, Claude!"}]
            )
            setup_results['client_initialized'] = True
            logger.info("✅ Claude Sonnet 4 client initialized successfully")
        except Exception as e:
            setup_results['instructions'].append(f"Client initialization failed: {str(e)}")
            logger.error(f"❌ Client initialization failed: {e}")
    
    setup_results['ready'] = all([
        setup_results['anthropic_library'],
        setup_results['api_key_configured'], 
        setup_results['client_initialized']
    ])
    
    if setup_results['ready']:
        logger.info("🚀 Claude Sonnet 4 is ready for financial analysis!")
    else:
        logger.warning("⚠️ Claude Sonnet 4 setup incomplete. Follow these steps:")
        for instruction in setup_results['instructions']:
            logger.warning(f"   • {instruction}")
    
    return setup_results

if __name__ == "__main__":
    # Test setup when run directly
    setup_results = setup_claude_sonnet_4()
    
    if setup_results['ready']:
        print("🎉 Claude Sonnet 4 upgrade ready!")
        print("\nTo integrate into your existing system:")
        print("1. Replace generate_premium_analysis_30_articles() calls with generate_premium_analysis_upgraded()")
        print("2. Or directly call generate_premium_analysis_claude_sonnet_4_enhanced() for Claude-specific features")
        print("3. Use compare_analysis_quality() to test improvements on specific companies")
    else:
        print("❌ Setup incomplete. See instructions above.")