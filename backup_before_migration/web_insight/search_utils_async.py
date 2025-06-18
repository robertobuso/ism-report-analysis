import httpx
import asyncio
import logging
import time
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from urllib.parse import urlparse
from . import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_article_async(url, timeout=10):
    """
    Asynchronously fetch article content with timeout and retry logic.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        HTML content as string or None if failed
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        logger.info(f"Fetching content from: {url}")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=timeout, follow_redirects=True)
            
            # Check if the request was successful
            if response.status_code != 200:
                logger.error(f"Failed to fetch {url}, status code: {response.status_code}")
                return None
                
            return response.text
    except Exception as e:
        logger.error(f"Error fetching {url}: {str(e)}")
        return None

async def fetch_articles_concurrently(urls, max_concurrency=5):
    """
    Fetch multiple articles concurrently with a concurrency limit.
    
    Args:
        urls: List of URLs to fetch
        max_concurrency: Maximum number of concurrent requests
        
    Returns:
        Dictionary mapping URLs to their HTML content
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def fetch_with_semaphore(url):
        async with semaphore:
            return url, await fetch_article_async(url)
    
    tasks = [fetch_with_semaphore(url) for url in urls]
    results = await asyncio.gather(*tasks)
    
    # Filter out failed fetches
    return {url: content for url, content in results if content is not None}

def extract_article_content(html, url, max_length=None):
    """
    Extract the main content from an article using readability-lxml with BeautifulSoup fallback.
    
    Args:
        html: HTML content
        url: URL of the article (for logging)
        max_length: Maximum content length to return
        
    Returns:
        Dictionary with title and content
    """
    if max_length is None:
        max_length = config.MAX_ARTICLE_LENGTH
        
    try:
        # Try with readability-lxml first
        from readability import Document
        doc = Document(html)
        title = doc.title()
        content = doc.summary()
        
        # Clean up the extracted HTML
        soup = BeautifulSoup(content, 'html.parser')
        content_text = soup.get_text(" ", strip=True)
        
        # Truncate if necessary
        if len(content_text) > max_length:
            content_text = content_text[:max_length] + "..."
            
        return {
            "title": title,
            "content": content_text
        }
    except Exception as e:
        logger.warning(f"Readability extraction failed for {url}: {str(e)}")
        
        # Fallback to BeautifulSoup
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
                
            # Try to get the title
            title = soup.title.string if soup.title else "No title found"
            
            # Try to find article content in common containers
            article_containers = soup.select('article, .article, .post, .content, main, [itemprop="articleBody"]')
            
            content = ""
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
                
            return {
                "title": title,
                "content": content
            }
        except Exception as e:
            logger.error(f"BeautifulSoup extraction failed for {url}: {str(e)}")
            return {
                "title": "Failed to extract title",
                "content": f"Failed to extract content: {str(e)}"
            }

def extract_date_from_metadata(html):
    """Extract publication date from HTML metadata."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try common metadata tags for publication date
        meta_tags = [
            # Open Graph protocol
            soup.find('meta', property='article:published_time'),
            # Schema.org
            soup.find('meta', itemprop='datePublished'),
            # Dublin Core
            soup.find('meta', name='dc.date'),
            # Other common formats
            soup.find('meta', name='date'),
            soup.find('meta', name='pubdate'),
            soup.find('meta', name='publish_date'),
            soup.find('meta', name='article:published_time')
        ]
        
        for tag in meta_tags:
            if tag and tag.get('content'):
                return tag.get('content')
                
        return None
    except Exception as e:
        logger.error(f"Error extracting date from metadata: {str(e)}")
        return None