import requests
import json
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time
import random
from . import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def search_web(query, num_results=3):
    """
    Search the web using Google Custom Search API.
    
    Args:
        query: Search query string
        num_results: Number of results to return (max 10)
        
    Returns:
        List of dictionaries containing search results
    """
    try:
        # Make sure we don't exceed the maximum results per request
        num_results = min(num_results, 10)
        
        # Check if API key and search engine ID are configured
        if not config.GOOGLE_API_KEY:
            logger.error("Google Custom Search API key not configured in environment")
            return []
            
        if not config.GOOGLE_SEARCH_ENGINE_ID:
            logger.error("Google Search Engine ID not configured in environment")
            return []
        
        # Prepare request parameters
        params = {
            'key': config.GOOGLE_API_KEY,
            'cx': config.GOOGLE_SEARCH_ENGINE_ID,
            'q': query,
            'num': num_results
        }
        
        logger.info(f"Searching for: {query}")
        logger.info(f"Using API key: {config.GOOGLE_API_KEY[:4]}...{config.GOOGLE_API_KEY[-4:]}")
        logger.info(f"Using Search Engine ID: {config.GOOGLE_SEARCH_ENGINE_ID}")
        
        response = requests.get(config.GOOGLE_SEARCH_URL, params=params)
        
        # Check if the request was successful
        if response.status_code != 200:
            logger.error(f"Search API returned status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return []
        
        # Parse the response
        search_results = response.json()
        
        # Check if the response has items
        if 'items' not in search_results:
            error_msg = search_results.get('error', {}).get('message', 'No search results')
            logger.error(f"No search results found: {error_msg}")
            return []
        
        # Extract relevant information
        results = []
        for item in search_results['items']:
            result = {
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'source': get_domain(item.get('link', '')),
                'date': item.get('pagemap', {}).get('metatags', [{}])[0].get('article:published_time', '')
            }
            results.append(result)
        
        logger.info(f"Found {len(results)} search results")
        return results
    except Exception as e:
        logger.error(f"Error searching web: {str(e)}")
        return []

def _get_mock_search_results(query):
    """Generate mock search results for demonstration purposes."""
    logger.warning(f"Using mock search results for query: {query}")
    
    # Get keywords from the query to make mock results more relevant
    keywords = query.lower().split()
    relevant_topics = []
    
    if any(kw in keywords for kw in ['prices', 'price', 'costs', 'inflation']):
        relevant_topics.append('prices')
    if any(kw in keywords for kw in ['order', 'orders', 'demand']):
        relevant_topics.append('orders')
    if any(kw in keywords for kw in ['production', 'output', 'manufacturing']):
        relevant_topics.append('production')
    if any(kw in keywords for kw in ['employment', 'jobs', 'hiring']):
        relevant_topics.append('employment')
    
    # Default to prices if no relevant topics found
    if not relevant_topics:
        relevant_topics = ['prices']
    
    # Mock results for each topic
    mock_results = {
        'prices': [
            {
                'title': 'Manufacturing Prices Show Sharp Increase in Recent Report',
                'url': 'https://example.com/manufacturing-prices-report',
                'snippet': 'Recent data shows manufacturing prices have increased substantially, driven by supply chain issues and rising demand.',
                'source': 'EconomicTimes',
                'date': '2025-05-01'
            },
            {
                'title': 'Raw Material Costs Driving Inflation Concerns in Manufacturing',
                'url': 'https://example.com/raw-material-costs',
                'snippet': 'Manufacturers report significant increases in input costs, particularly in metals, semiconductors, and energy prices.',
                'source': 'IndustryWeek',
                'date': '2025-04-28'
            },
            {
                'title': 'Impact of Rising Manufacturing Costs on Consumer Prices',
                'url': 'https://example.com/consumer-impact',
                'snippet': 'Analysis of how increased manufacturing costs are beginning to affect consumer prices across multiple product categories.',
                'source': 'ConsumerReports',
                'date': '2025-04-30'
            }
        ],
        'orders': [
            {
                'title': 'Manufacturing New Orders Indicate Strong Demand Despite Economic Concerns',
                'url': 'https://example.com/manufacturing-orders-demand',
                'snippet': 'The latest ISM report shows surprising strength in new orders, suggesting resilient demand despite broader economic headwinds.',
                'source': 'BusinessInsider',
                'date': '2025-05-01'
            },
            {
                'title': 'Supply Chain Issues Continue to Impact Order Fulfillment',
                'url': 'https://example.com/supply-chain-orders',
                'snippet': 'Manufacturers struggle to fulfill growing order books amid persistent supply chain disruptions and material shortages.',
                'source': 'SupplyChainDigital',
                'date': '2025-04-25'
            },
            {
                'title': 'Regional Manufacturing Surveys Show Mixed Order Trends',
                'url': 'https://example.com/regional-manufacturing',
                'snippet': 'While some regions report strong new order growth, others face declining demand, creating a complex national picture.',
                'source': 'RegionalEconomics',
                'date': '2025-04-22'
            }
        ],
        'production': [
            {
                'title': 'Manufacturing Production Rebounds After Months of Contraction',
                'url': 'https://example.com/production-rebound',
                'snippet': 'Production levels show significant improvement as manufacturers adapt to supply constraints and labor challenges.',
                'source': 'IndustryToday',
                'date': '2025-05-01'
            },
            {
                'title': 'Energy Costs Threaten Production Growth in Manufacturing Sector',
                'url': 'https://example.com/energy-production-impact',
                'snippet': 'Rising energy prices pose challenges to sustained production growth, particularly for energy-intensive manufacturing processes.',
                'source': 'EnergyInsights',
                'date': '2025-04-27'
            },
            {
                'title': 'Automation Investments Helping Balance Production Constraints',
                'url': 'https://example.com/automation-manufacturing',
                'snippet': 'Manufacturers increasing investments in automation to maintain production levels amid ongoing labor shortages.',
                'source': 'AutomationWorld',
                'date': '2025-04-20'
            }
        ],
        'employment': [
            {
                'title': 'Manufacturing Employment Shows Modest Growth Despite Automation',
                'url': 'https://example.com/manufacturing-employment',
                'snippet': 'The latest figures show continued but modest job growth in manufacturing, balancing automation with expanding production needs.',
                'source': 'WorkforceInsights',
                'date': '2025-05-01'
            },
            {
                'title': 'Skills Gap Remains a Challenge for Manufacturing Employers',
                'url': 'https://example.com/manufacturing-skills-gap',
                'snippet': 'Manufacturers report difficulty finding qualified workers despite offering higher wages and improved benefits.',
                'source': 'IndustryWeek',
                'date': '2025-04-26'
            },
            {
                'title': 'Regional Manufacturing Employment Trends Vary Widely',
                'url': 'https://example.com/regional-employment',
                'snippet': 'While some regions see manufacturing job growth, others continue to face declines, reflecting industry-specific and geographic factors.',
                'source': 'LaborEconomics',
                'date': '2025-04-15'
            }
        ]
    }
    
    # Return results for the first relevant topic
    return mock_results[relevant_topics[0]]

def fetch_article_content(url, max_length=None):
    """
    Fetch and extract the main content from an article URL.
    
    Args:
        url: URL to fetch
        max_length: Maximum content length to return
        
    Returns:
        Extracted article content as string
    """
    if max_length is None:
        max_length = config.MAX_ARTICLE_LENGTH
        
    try:
        # Check if this is a mock URL
        if url.startswith('https://example.com/'):
            return _get_mock_article_content(url)
            
        # Add a random delay to avoid rate limiting (between 1-3 seconds)
        time.sleep(random.uniform(1, 3))
        
        # Add headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Send the request
        logger.info(f"Fetching content from: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        
        # Check if the request was successful
        if response.status_code != 200:
            logger.error(f"Failed to fetch {url}, status code: {response.status_code}")
            return f"Failed to fetch content (Status code: {response.status_code})"
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Extract text from common article containers
        content = ""
        
        # Try to find article content in common containers
        article_containers = soup.select('article, .article, .post, .content, main, [itemprop="articleBody"]')
        
        if article_containers:
            # Use the first container that matches
            for paragraph in article_containers[0].find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                content += paragraph.get_text() + "\n\n"
        else:
            # Fallback to all paragraphs if no article container is found
            for paragraph in soup.find_all('p'):
                content += paragraph.get_text() + "\n"
        
        # Clean up the content
        content = ' '.join(content.split())
        
        # Truncate if necessary
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        return content
    except Exception as e:
        logger.error(f"Error fetching article content: {str(e)}")
        # Return mock content for demonstration purposes
        return _get_mock_article_content(url)

def _get_mock_article_content(url):
    """Generate mock article content for demonstration purposes."""
    logger.warning(f"Using mock article content for URL: {url}")
    
    # Mock content by URL
    if "manufacturing-prices-report" in url:
        return "The latest manufacturing data shows a significant increase in prices, with the ISM Prices Index rising 7.5 points to 62.4 in February 2025. This marks the largest monthly increase in over two years and suggests growing inflationary pressures in the manufacturing sector. Analysts point to several factors driving this trend, including persistent supply chain disruptions, increased global demand, and rising energy costs. The automotive and electronics sectors are particularly affected, with some manufacturers reporting difficulty maintaining margins."
    elif "raw-material-costs" in url:
        return "Manufacturing input costs have risen dramatically, according to industry sources. Steel prices are up over 15% year-over-year, while semiconductor costs remain elevated due to ongoing shortages. Energy costs are also contributing to the overall increase in manufacturing expenses. Many larger companies are implementing strategic pricing adjustments to pass these costs on to consumers, while smaller manufacturers are reporting margin compression. The trend is expected to continue for at least the next quarter, with potential relief coming in Q4 as supply chains stabilize."
    elif "consumer-impact" in url:
        return "Consumer prices are beginning to reflect the impact of higher manufacturing costs. Retailers report difficulty absorbing the full increase, with companies like Walmart and Target facing difficult decisions about how much to pass on to consumers. Technology companies like Apple and Microsoft have been more successful in maintaining margins due to strong brand loyalty and pricing power. Industry analysts suggest this could lead to a shift in consumer spending patterns, favoring essential goods and services with inelastic demand over discretionary purchases."
    elif "manufacturing-orders-demand" in url:
        return "The latest ISM Manufacturing Report shows new orders rose to 58.2, indicating continued expansion and strong demand. Despite economic concerns around inflation and interest rates, customers continue to place orders at a robust pace. Industry analysts suggest this resilience may be driven by inventory rebuilding after prolonged supply chain disruptions and strong export demand. The consumer goods and technology sectors are leading the growth in new orders, while construction-related manufacturing shows mixed results amid housing market uncertainties."
    elif "supply-chain-orders" in url:
        return "Manufacturers are reporting growing backlogs as new orders outpace production capacity due to persistent supply chain constraints. While order books are filling up, companies face challenges in sourcing key components and raw materials. The semiconductor shortage continues to impact electronics and automotive production, while logistics disruptions affect delivery timelines. Some manufacturers have implemented allocation systems to prioritize key customers, while others are extending lead times to manage expectations."
    elif "regional-manufacturing" in url:
        return "Regional manufacturing surveys reveal a diverging trends across the United States. The Northeast and Midwest regions report robust new order growth, particularly in industrial equipment and transportation sectors. However, the Southeast and parts of the West Coast show declining order rates in consumer goods and construction-related manufacturing. These regional variations may reflect different exposure to international trade patterns and sector concentrations. Economists suggest these divergent trends could lead to uneven economic growth across regions in the coming months."
    elif "production-rebound" in url:
        return "Manufacturing production has increased 5.4 points to 57.8, marking the strongest expansion in 18 months. After struggling with supply constraints and labor shortages, manufacturers have made significant adaptations to boost output. Investments in automation, workforce training, and supply chain diversification are beginning to pay off. Sectors showing the strongest production growth include computer and electronic products, machinery, and fabricated metal products. The improved production levels come as a relief to customers who have faced extended lead times over the past year."
    elif "energy-production-impact" in url:
        return "Rising energy costs are creating headwinds for manufacturing production growth, particularly in energy-intensive sectors like chemicals, paper, and primary metals. Natural gas and electricity price increases are squeezing margins and forcing some manufacturers to reassess production schedules. Companies are responding with energy efficiency initiatives and accelerating renewable energy investments to mitigate long-term cost exposure. Some analysts predict potential production cutbacks in the most affected sectors if energy prices continue to climb through the summer months."
    elif "automation-manufacturing" in url:
        return "Manufacturers are accelerating automation investments to maintain production levels despite ongoing labor challenges. The latest capital expenditure data shows a 22% year-over-year increase in automation equipment purchases. While these investments help address immediate production constraints, they're also changing the skill requirements for manufacturing workers. Companies report shifting their hiring focus toward technical roles that can program, maintain, and optimize automated systems. Industry groups are partnering with technical schools to develop training programs aligned with these evolving workforce needs."
    elif "manufacturing-employment" in url:
        return "The ISM Employment Index rose 2.8 points to 52.1, indicating modest expansion in manufacturing hiring. Despite concerns about automation replacing jobs, the sector continues to add workers, though at a slower pace than other economic indicators would suggest. The job growth is concentrated in skilled positions and technical roles, reflecting the sector's increasing technological sophistication. Companies report offering higher wages, enhanced benefits, and training opportunities to attract and retain workers in a competitive labor market."
    elif "manufacturing-skills-gap" in url:
        return "The manufacturing skills gap persists as a significant challenge despite rising wages and improved benefits. According to the latest industry survey, 79% of manufacturers report difficulty finding qualified candidates for open positions. The most severe shortages are in CNC operation, industrial maintenance, automation specialists, and manufacturing engineers. Some companies are developing in-house training programs and apprenticeships to build their workforce pipeline, while others are partnering with community colleges and technical schools to develop curriculum aligned with industry needs."
    elif "regional-employment" in url:
        return "Manufacturing employment shows significant regional variation across the United States. The Midwest and Southeast regions report the strongest job growth, driven by transportation equipment, food processing, and medical device manufacturing. In contrast, the Northeast continues to see manufacturing employment declines, particularly in traditional industries like textiles and paper. The Western states show mixed results, with technology manufacturing adding jobs while other sectors remain flat. These regional differences reflect both industry concentration patterns and varying state-level policies affecting manufacturing competitiveness."
    else:
        return "Content not available for this URL in demo mode."
    
def get_domain(url):
    """Extract the domain from a URL."""
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
            
        return domain
    except:
        return url