"""
Search utilities – enhanced for month-aware queries, pagination, embeddings,
and similarity/freshness filtering.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import numpy as np
import requests
from bs4 import BeautifulSoup

from . import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 1. Query generation
# --------------------------------------------------------------------------- #
def generate_month_aware_queries(trend: dict, num_queries: int = 4) -> list[str]:
    """Return a list of search queries that include current month / year."""
    index_name = trend["index_name"]
    direction = "increase" if trend["change"] > 0 else "decrease"

    current_month = datetime.now().strftime("%B")
    current_year = datetime.now().year

    base_queries = [
        f"manufacturing {index_name.lower()} {direction} impact {current_month} {current_year}",
        f"economic impact of {direction} in manufacturing {index_name.lower()} today",
        f"{index_name} {direction} manufacturing sector implications {current_month}",
        f"why {index_name.lower()} {direction}d in manufacturing this month",
        f"recent {direction} in manufacturing {index_name.lower()} analysis",
        f"manufacturing {index_name.lower()} trends this week",
    ]

    extra = {
        "New Orders": [
            f"manufacturing demand {direction} {current_month} impact",
            f"factory orders {direction} economic implications this week",
        ],
        "Production": [
            f"manufacturing output {direction} {current_month} implications",
            f"factory production {direction} impact today",
        ],
        "Employment": [
            f"manufacturing jobs {direction} {current_month} analysis",
            f"factory workforce changes {current_month} {current_year}",
        ],
        "Prices": [
            f"manufacturing inflation {direction} {current_month} impact",
            f"raw material prices {direction} manufacturing {current_month}",
        ],
        "Manufacturing PMI": [
            f"manufacturing PMI {direction} economic outlook {current_month}",
            f"PMI {direction} impact on economy this week",
        ],
    }.get(index_name, [])

    queries = base_queries + extra
    return queries[:num_queries]


# --------------------------------------------------------------------------- #
# 2. Google CSE search with pagination + de-dup
# --------------------------------------------------------------------------- #
def search_web(query: str, num_results: int = 10, fetch_all_pages: bool = False) -> list[dict]:
    """
    Call Google Custom Search API, return a list of result dictionaries.

    If fetch_all_pages is True, we paginate start=1,11,21 until we have >=15
    unique results or exhaust three pages.
    """
    try:
        if not config.GOOGLE_API_KEY:
            logger.error("Google Custom Search API key not configured")
            return []
        if not config.GOOGLE_SEARCH_ENGINE_ID:
            logger.error("Google Search Engine ID not configured")
            return []

        all_results: list[dict] = []
        start_indices = [1] + ([11, 21] if fetch_all_pages else [])

        for start in start_indices:
            params = {
                "key": config.GOOGLE_API_KEY,
                "cx": config.GOOGLE_SEARCH_ENGINE_ID,
                "q": query,
                "num": min(num_results, 10),
                "start": start,
            }
            logger.info(f"Google CSE search: '{query}' start={start}")
            if start > 1:
                time.sleep(1)  # polite delay

            response = requests.get(config.GOOGLE_SEARCH_URL, params=params, timeout=10)
            if response.status_code != 200:
                logger.error(f"CSE status {response.status_code}: {response.text}")
                break

            payload = response.json()
            if "items" not in payload:
                logger.warning("No items in CSE response")
                break

            for item in payload["items"]:
                all_results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source": get_domain(item.get("link", "")),
                        "date": item.get("pagemap", {})
                        .get("metatags", [{}])[0]
                        .get("article:published_time", ""),
                    }
                )

            # stop if we already have 15+
            if len({r["url"] for r in all_results}) >= 15:
                break

        # de-duplicate by URL
        seen = set()
        unique_results = [r for r in all_results if not (r["url"] in seen or seen.add(r["url"]))]

        logger.info(f"Found {len(unique_results)} unique search results")
        return unique_results

    except Exception as exc:
        logger.error(f"search_web error: {exc}")
        return []


# --------------------------------------------------------------------------- #
# 3. Article embeddings & similarity / freshness filter
# --------------------------------------------------------------------------- #
def get_embedding(text: str, model: str = "text-embedding-3-small"):
    """Return OpenAI embedding vector or None on failure."""
    try:
        import openai

        openai.api_key = config.OPENAI_API_KEY
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding
    except Exception as exc:
        logger.error(f"Embedding error: {exc}")
        return None


def calculate_cosine_similarity(v1, v2) -> float:
    if v1 is None or v2 is None:
        return 0.0
    a, b = np.array(v1), np.array(v2)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def filter_articles_by_similarity_and_freshness(
    articles: list[dict], trend_desc: str, max_age_days: int = 45, top_n: int = 5
) -> list[dict]:
    """Return up to top_n articles within max_age_days and highest cosine similarity."""
    from dateutil import parser as date_parser

    trend_emb = get_embedding(trend_desc)
    if trend_emb is None:
        logger.warning("Could not embed trend description – skipping similarity filter")
        return articles[:top_n]

    cutoff = datetime.now() - timedelta(days=max_age_days)
    scored: list[dict] = []

    for art in articles:
        # filter by freshness
        if art.get("date"):
            try:
                if date_parser.parse(art["date"]) < cutoff:
                    continue
            except Exception:
                pass  # unknown format – keep

        text = f"{art.get('title','')} {art.get('snippet','')} {art.get('content','')[:200]}"
        sim = calculate_cosine_similarity(trend_emb, get_embedding(text))
        art["similarity_score"] = sim
        scored.append(art)

    return sorted(scored, key=lambda x: x["similarity_score"], reverse=True)[:top_n]


# --------------------------------------------------------------------------- #
# 4. Misc helpers
# --------------------------------------------------------------------------- #
def get_domain(url: str) -> str:
    try:
        domain = urlparse(url).netloc
        return domain[4:] if domain.startswith("www.") else domain
    except Exception:
        return url
