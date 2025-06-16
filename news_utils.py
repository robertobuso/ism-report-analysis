import requests
import os
import re
from datetime import datetime, timedelta
from openai import OpenAI
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Enhanced source diversity and quality
PREMIUM_SOURCES = {
    'bloomberg.com': 10, 'reuters.com': 9, 'wsj.com': 9, 'ft.com': 8,
    'cnbc.com': 7, 'marketwatch.com': 7, 'barrons.com': 8, 'financialtimes.com': 8,
    'seekingalpha.com': 6, 'zacks.com': 5, 'thestreet.com': 5, 'investorplace.com': 4,
    'fool.com': 4, 'investing.com': 4, 'benzinga.com': 5, 'morningstar.com': 6
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

# Sophisticated insight tags for better categorization
INSIGHT_TAGS = {
    'earnings': '[EARNINGS]', 'guidance': '[GUIDANCE]', 'analyst': '[ANALYST]',
    'merger': '[M&A]', 'acquisition': '[M&A]', 'partnership': '[PARTNERSHIP]',
    'ai': '[AI STRATEGY]', 'artificial intelligence': '[AI STRATEGY]',
    'dividend': '[SHAREHOLDER RETURN]', 'buyback': '[SHAREHOLDER RETURN]',
    'lawsuit': '[LEGAL RISK]', 'regulation': '[REGULATORY]',
    'ceo': '[MANAGEMENT]', 'leadership': '[MANAGEMENT]',
    'product': '[PRODUCT]', 'launch': '[PRODUCT]',
    'insider': '[INSIDER SIGNAL]', 'upgrade': '[ANALYST]', 'downgrade': '[ANALYST]'
}

def fetch_google_news(company: str, days_back: int = 7) -> List[Dict]:
    """
    Multi-strategy news fetch with premium source targeting and comprehensive coverage.
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_filter = start_date.strftime("%Y-%m-%d")
        
        # Enhanced search strategies prioritizing premium sources
        search_queries = []
        
        # Strategy 1: Premium source targeting
        premium_sites = ['bloomberg.com', 'reuters.com', 'wsj.com', 'cnbc.com', 'marketwatch.com']
        for site in premium_sites[:3]:  # Top 3 to avoid overwhelming API
            search_queries.append(f'site:{site} "{company}" after:{date_filter}')
        
        # Strategy 2: Financial-specific searches
        if len(company) <= 5 and company.isupper():
            # Ticker-based searches
            search_queries.extend([
                f'"{company}" stock earnings analyst price target after:{date_filter}',
                f'{company} revenue guidance outlook after:{date_filter}',
                f'{company} (upgrade OR downgrade OR rating) after:{date_filter}'
            ])
        else:
            # Company name searches
            search_queries.extend([
                f'"{company}" earnings revenue analyst after:{date_filter}',
                f'"{company}" stock price guidance after:{date_filter}',
                f'"{company}" (merger OR acquisition OR partnership) after:{date_filter}'
            ])
        
        # Strategy 3: Business development and catalyst searches
        search_queries.extend([
            f'"{company}" (CEO OR CFO OR management) after:{date_filter}',
            f'"{company}" (product OR launch OR innovation) after:{date_filter}',
            f'"{company}" financial news after:{date_filter}'
        ])
        
        all_articles = []
        seen_urls = set()
        
        for query in search_queries:
            try:
                url = "https://www.googleapis.com/customsearch/v1"
                params = {
                    "key": os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY"),
                    "cx": os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
                    "q": query,
                    "sort": "date",
                    "num": 10,
                    "dateRestrict": f"d{days_back}"
                }
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                for item in response.json().get("items", []):
                    article_url = item.get("link", "")
                    
                    if article_url in seen_urls:
                        continue
                    seen_urls.add(article_url)
                    
                    article = {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "link": article_url,
                        "source": extract_domain(article_url),
                        "published": item.get("snippet", "")
                    }
                    
                    if is_relevant_article(article, company):
                        all_articles.append(article)
                
                # Rate limiting
                import time
                time.sleep(0.15)
                
            except Exception as query_e:
                logger.warning(f"Query failed: {query[:50]}... - {str(query_e)}")
                continue
        
        # Log source quality distribution
        source_distribution = {}
        for article in all_articles:
            source = article['source']
            source_distribution[source] = source_distribution.get(source, 0) + 1
        
        premium_count = sum(count for source, count in source_distribution.items() if source in PREMIUM_SOURCES)
        logger.info(f"Fetched {len(all_articles)} articles for {company}: {premium_count} from premium sources")
        logger.debug(f"Source distribution: {dict(list(source_distribution.items())[:5])}")
        
        return all_articles
        
    except Exception as e:
        logger.error(f"Error fetching news for {company}: {str(e)}")
        return []

def is_relevant_article(article: Dict, company: str) -> bool:
    """
    Filter out obviously irrelevant articles during fetch.
    """
    title = article.get('title', '').lower()
    snippet = article.get('snippet', '').lower()
    source = article.get('source', '').lower()
    company_lower = company.lower()
    
    # Skip job postings, careers pages
    if any(term in title + snippet for term in ['jobs at', 'careers at', 'apply today', 'job openings', 'hiring']):
        return False
    
    # Skip obviously unrelated businesses (like Apple Valley Ford)
    if company_lower == 'apple':
        irrelevant_terms = ['ford', 'dealership', 'auto sales', 'car dealer', 'valley', 'city of apple']
        if any(term in title + snippet for term in irrelevant_terms):
            return False
    
    # Skip pure directory/listing pages
    if any(term in title for term in ['directory', 'yellow pages', 'business listing']):
        return False
        
    # Skip podcast/video unless from premium sources
    if source not in PREMIUM_SOURCES and any(term in title + snippet for term in ['podcast', 'video', 'watch now', 'listen']):
        return False
    
    # Must have reasonable company mention
    company_mentions = title.count(company_lower) + snippet.count(company_lower)
    if company_mentions == 0:
        return False
        
    return True

def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return "unknown"

def score_articles(articles: List[Dict], company: str) -> List[Tuple[Dict, float]]:
    """
    Score articles based on source quality, financial relevance, and content quality.
    Returns list of (article, score) tuples sorted by score descending.
    """
    scored_articles = []
    
    for article in articles:
        score = 0.0
        
        title = article.get('title', '').lower()
        snippet = article.get('snippet', '').lower()
        source = article.get('source', '').lower()
        
        # Source quality score (0-10)
        source_score = PREMIUM_SOURCES.get(source, 2)
        score += source_score
        
        # Financial relevance score (0-8)
        title_snippet = title + ' ' + snippet
        financial_matches = sum(1 for keyword in FINANCIAL_KEYWORDS if keyword in title_snippet)
        relevance_score = min(financial_matches * 0.7, 8)
        score += relevance_score
        
        # Company name prominence (0-5)
        company_lower = company.lower()
        
        # Higher score for company name in title
        if company_lower in title:
            score += 3
        
        # Score for mentions in snippet
        company_mentions = snippet.count(company_lower)
        company_score = min(company_mentions * 1, 2)
        score += company_score
        
        # Content quality score (0-3)
        snippet_length = len(snippet)
        if snippet_length > 200:
            score += 3
        elif snippet_length > 100:
            score += 2
        elif snippet_length > 50:
            score += 1
        
        # News freshness indicators (0-2)
        fresh_indicators = ['today', 'yesterday', 'this week', 'breaking', 'just announced']
        if any(indicator in title_snippet for indicator in fresh_indicators):
            score += 2
        
        # Business/financial context boost (0-3)
        business_terms = ['stock', 'shares', 'market', 'investors', 'wall street', 'nasdaq', 'trading']
        business_matches = sum(1 for term in business_terms if term in title_snippet)
        score += min(business_matches * 0.5, 3)
        
        # PENALTIES for low-value content
        
        # Heavy penalty for job postings and careers
        if any(term in title_snippet for term in ['jobs at', 'careers', 'hiring', 'apply today', 'job openings']):
            score -= 15
            
        # Penalty for pure directory/listing content
        if any(term in title for term in ['directory', 'listing', 'find businesses']):
            score -= 10
            
        # Penalty for obviously unrelated businesses (like Apple Valley Ford for Apple)
        if company_lower == 'apple':
            unrelated_terms = ['ford', 'dealership', 'auto', 'car dealer', 'apple valley', 'apple creek']
            if any(term in title_snippet for term in unrelated_terms):
                score -= 20
        
        # Penalty for low-engagement content
        if any(word in title_snippet for word in ['podcast', 'video', 'watch', 'listen']) and source not in PREMIUM_SOURCES:
            score -= 3
            
        # Penalty for press releases (often less analytical)
        if any(word in title_snippet for word in ['press release', 'pr newswire', 'announces']):
            score -= 2
            
        # Ensure minimum score of 0
        score = max(score, 0)
        
        scored_articles.append((article, score))
    
    # Sort by score descending and log top scores for debugging
    scored_articles.sort(key=lambda x: x[1], reverse=True)
    
    if scored_articles:
        logger.info(f"Article scoring complete. Top 3 scores: {[round(score, 1) for _, score in scored_articles[:3]]}")
        logger.debug(f"Top article: '{scored_articles[0][0].get('title', '')[:50]}...' Score: {scored_articles[0][1]}")
    
    return scored_articles

def generate_financial_summary(company: str, articles: List[Dict], max_articles: int = 15) -> Dict[str, List[str]]:
    """
    Generate institutional-grade financial analysis with quantified impacts and trading context.
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
        
        # Source quality assessment
        premium_count = sum(1 for article in top_articles if article['source'] in PREMIUM_SOURCES)
        total_articles = len(top_articles)
        
        # Prepare enhanced article content for analysis
        article_text = ""
        for i, article in enumerate(top_articles, 1):
            source_quality = "PREMIUM" if article['source'] in PREMIUM_SOURCES else "STANDARD"
            article_text += f"\n{i}. [{source_quality}] {article['title']}\n"
            article_text += f"   Source: {article['source']}\n"
            article_text += f"   Content: {article['snippet']}\n"
            article_text += f"   Link: {article['link']}\n"
        
        # Institutional-grade analysis prompt with quantification focus
        prompt = f"""You are a senior equity research analyst at Goldman Sachs providing institutional-grade analysis for {company}.

ARTICLES TO ANALYZE ({total_articles} articles, {premium_count} premium sources):
{article_text}

ANALYSIS FRAMEWORK:
Generate insights that help portfolio managers make informed decisions. Each bullet must include:
1. Specific financial/strategic context
2. Quantified impact where possible (revenue $, margin %, timeline, price targets)
3. Market relevance and trading implications

REQUIRED SECTIONS (2-3 bullets each):

**EXECUTIVE SUMMARY**
Focus: Material business developments affecting fundamental outlook
Requirements: 
- Include specific financial metrics when mentioned (revenue impact, cost savings, market size)
- Add expected timeline for impact realization
- Use varied tags: [STRATEGY], [PRODUCT], [MANAGEMENT], [PARTNERSHIP], [EXPANSION]
- Format: **[TAG]** Development description with quantified impact *(Source: domain.com)*

**INVESTOR INSIGHTS** 
Focus: Valuation drivers, analyst views, and market positioning
Requirements:
- Include specific price targets, rating changes, and rationale
- Add trading context (support/resistance levels, volume patterns)
- Reference peer comparisons and sector implications
- Quantify estimate revisions (EPS changes, revenue adjustments)
- Use tags: [ANALYST], [VALUATION], [ESTIMATES], [MULTIPLE], [PEER COMPARISON]

**CATALYSTS & RISKS**
Focus: Near-term stock-moving events and risk factors
Requirements:
- Include specific dates for upcoming events (earnings, product launches, regulatory decisions)
- Quantify potential impact magnitude (% revenue exposure, market size, probability)
- Add urgency indicators (days until event, percentage of business at risk)
- Reference historical precedents when relevant
- Use tags: [CATALYST], [RISK], [REGULATORY], [COMPETITIVE], [TECHNICAL]

CRITICAL REQUIREMENTS:
- Every bullet MUST include quantified impact when data is available
- Add trading context: "Next resistance at $X", "Support level holds at $Y"
- Include analyst reasoning: "JPM raised PT to $X citing [specific reason]"
- Reference timeframes: "Expected Q2 impact", "FY25 guidance revision"
- Add market context: "Outperforming sector by X%", "Trading at Xp P/E premium"
- If no premium sources available, acknowledge limitation but extract maximum value
- Be specific: Replace "enhance competitive position" with "expected to gain 2-3% market share in premium segment"

AVOID:
- Generic statements without financial context
- Repetitive tags ([UPDATE] used multiple times)
- Analysis without quantification when numbers are available
- Speculation beyond what's reported in sources"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": f"You are a senior equity research analyst at Goldman Sachs. Provide institutional-grade analysis with specific financial metrics, trading context, and quantified impacts. Focus on actionable insights for portfolio managers trading {company}."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1,  # Very low temperature for consistent, factual analysis
            max_tokens=1800
        )
        
        analysis_text = response.choices[0].message.content
        logger.info(f"Generated institutional analysis for {company}: {len(analysis_text)} characters from {len(top_articles)} articles ({premium_count} premium)")
        
        return parse_financial_summaries(analysis_text)
        
    except Exception as e:
        logger.error(f"Error generating institutional summary for {company}: {str(e)}")
        return {
            "executive": [f"Error generating analysis: {str(e)}"],
            "investor": ["Analysis unavailable due to processing error."],
            "catalysts": ["Unable to identify catalysts at this time."]
        }

def parse_financial_summaries(text: str) -> Dict[str, List[str]]:
    """
    Parse the LLM response into structured summaries with better error handling.
    """
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
            if bullet and len(bullet) > 10:  # Filter out very short bullets
                sections[current_section].append(bullet)
    
    # Fallback parsing if section detection fails
    if all(len(section) == 0 for section in sections.values()):
        logger.warning("Section detection failed, using fallback parsing")
        bullets = [line.lstrip('-•* ').strip() for line in lines 
                  if line.strip().startswith(('-', '•', '*')) and len(line.strip()) > 10]
        
        # Distribute bullets evenly across sections
        for i, bullet in enumerate(bullets[:9]):  # Max 9 bullets total
            section_names = list(sections.keys())
            sections[section_names[i % 3]].append(bullet)
    
    # Ensure each section has at least one item
    for section_name, bullets in sections.items():
        if not bullets:
            sections[section_name] = ["No significant developments identified in this category."]
    
    return sections

def convert_markdown_to_html(text: str) -> str:
    """
    Convert markdown formatting to HTML for proper display.
    """
    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Convert *italic* to <em>
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    
    # Convert [text](url) to HTML links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    
    # Convert *(Source: domain)* to styled source attribution
    text = re.sub(r'\*\(Source:\s*([^)]+)\)\*', r'<span class="text-muted small">(Source: \1)</span>', text)
    
    return text