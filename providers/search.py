"""Web search and URL pulling capabilities using DuckDuckGo."""

import httpx
import logging
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

logger = logging.getLogger(__name__)

async def get_search_results(query: str, max_results: int = 3) -> list[dict]:
    """Execute a web search using DuckDuckGo.
    
    Returns a list of dicts with 'title', 'href', and 'body' keys.
    """
    logger.info(f"[search] Searching: '{query}'")
    try:
        results = DDGS().text(query, max_results=max_results)
        return list(results)
    except DuckDuckGoSearchException as e:
        logger.error(f"[search] DuckDuckGo failure: {e}")
        return []
    except Exception as e:
        logger.error(f"[search] Unexpected search error: {e}")
        return []


async def fetch_and_extract_text(url: str, max_chars: int = 8000) -> str:
    """Fetch a web page and carefully strip boilerplate using BeautifulSoup."""
    logger.info(f"[search] Fetching url={url}")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            
            # Use BeautifulSoup to parse HTML and remove script/style
            soup = BeautifulSoup(resp.text, "html.parser")
            for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
                script_or_style.extract()
                
            text = soup.get_text(separator="\n", strip=True)
            return text[:max_chars]
    except Exception as e:
        logger.warning(f"[search] Failed to fetch/parse {url}: {e}")
        return ""
