"""Web search and URL pulling capabilities.

Search results feed a URL fetcher that runs inside the worker, so the fetcher
is hardened: it refuses private/loopback targets (SSRF) and caps the response
size before parsing.
"""

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

try:  # package renamed from duckduckgo_search to ddgs
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException as SearchException
except ImportError:  # pragma: no cover - older installs
    from duckduckgo_search import DDGS  # type: ignore[no-redef]
    from duckduckgo_search.exceptions import (  # type: ignore[no-redef]
        DuckDuckGoSearchException as SearchException,
    )

MAX_BYTES = 2_000_000
BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}
BLOCKED_PORTS = {22, 23, 25, 3306, 5432, 6379}


def is_safe_url(url: str) -> bool:
    """Reject non-http(s) schemes and hosts that resolve to private space."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if parsed.hostname.lower() in BLOCKED_HOSTNAMES:
        return False
    if parsed.port and parsed.port in BLOCKED_PORTS:
        return False

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except (socket.gaierror, UnicodeError):
        return False

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False

    return True


def _search_sync(query: str, max_results: int) -> list[dict]:
    """Blocking DuckDuckGo call — always run this in a thread."""
    return list(DDGS().text(query, max_results=max_results) or [])


async def get_search_results(query: str, max_results: int = 3) -> list[dict]:
    """Execute a web search.

    DDGS is a synchronous library; calling it inline would block the event
    loop for every request, so it runs in a worker thread.
    """
    logger.info("[search] query=%r", query)
    try:
        results = await asyncio.to_thread(_search_sync, query, max_results)
    except SearchException as exc:
        logger.error("[search] provider failure: %s", exc)
        return []
    except Exception as exc:
        logger.error("[search] unexpected failure: %s", exc)
        return []

    cleaned: list[dict] = []
    for result in results:
        url = result.get("href") or result.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            cleaned.append(
                {
                    "title": (result.get("title") or "Untitled").strip(),
                    "href": url,
                    "body": (result.get("body") or "").strip(),
                }
            )
    return cleaned


async def fetch_and_extract_text(url: str, max_chars: int = 8000) -> str:
    """Fetch a page and strip boilerplate, refusing unsafe targets."""
    if not is_safe_url(url):
        logger.warning("[search] refusing to fetch unsafe url=%s", url)
        return ""

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": "HumanoidBot/0.2 (+research assistant)"},
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    logger.info(
                        "[search] skipping non-text content-type=%s", content_type
                    )
                    return ""

                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= MAX_BYTES:
                        logger.info("[search] truncating body at %d bytes", size)
                        break
                body = b"".join(chunks).decode(response.encoding or "utf-8", "ignore")
    except Exception as exc:
        logger.warning("[search] failed to fetch %s: %s", url, exc)
        return ""

    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.extract()

    text = soup.get_text(separator="\n", strip=True)
    # Collapse runs of blank lines left behind by removed blocks.
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:max_chars]
