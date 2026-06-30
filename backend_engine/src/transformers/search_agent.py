"""
search_agent.py — Ground-Truth News Search & Article Extraction.

This is the text-based MVP of DoksliPlis. Given a textual claim (e.g. an
Indonesian political claim), the agent:

1. Queries **DuckDuckGo** (via the ``ddgs`` library) with the
   claim, scoped to trusted Indonesian publishers via ``site:`` operators
   and locked to the Indonesia region (``region="id-id"``).
2. Takes the top 3 URL results (extracted from the ``href`` field).
3. Scrapes the main article text from each URL using ``httpx`` + ``beautifulsoup4``.
4. Returns a structured JSON payload containing the claim, the 3 URLs, and
   the extracted article text — ready for LLM evaluation.

Usage
-----
>>> from src.transformers.search_agent import verify_claim
>>> result = verify_claim("PDIP akan mendukung Prabowo di 2029")
>>> for article in result["articles"]:
...     print(article["url"], article["text"][:200])
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag
from ddgs import DDGS  # type: ignore

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Trusted Indonesian publishers — used as ``site:`` filter in the query.
_TRUSTED_SITES = [
    "turnbackhoax.id",
    "kompas.com",
    "tirto.id",
    "tempo.co",
]

# Number of search results to fetch and scrape.
_MAX_RESULTS = 1

# DuckDuckGo region code for Indonesia.
_SEARCH_REGION = "id-id"

# HTTP request timeout in seconds.
_REQUEST_TIMEOUT = 15

# Retry configuration.
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds between retries

# Browser-like headers to avoid bot detection on news sites / datacenter IPs.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# CSS selectors tried in order to extract article body text.
# Each site structures content differently; we try common patterns first.
_CONTENT_SELECTORS = [
    "article p",            # Semantic <article> — works for most modern sites
    "[class*='article'] p", # Class names containing "article"
    "[class*='content'] p", # Class names containing "content"
    "main p",               # <main> element paragraphs
    ".post-content p",      # WordPress-style
    ".story p",             # Tempo-style
    "p",                    # Fallback: all paragraphs
]

# ---------------------------------------------------------------------------
# HTTP client (reusable, with HTTP/2 support to bypass bot detection)
# ---------------------------------------------------------------------------
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Return a shared httpx.Client with HTTP/2 and browser-like settings."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            http2=True,
            timeout=_REQUEST_TIMEOUT,
            headers=_HEADERS,
            follow_redirects=True,
        )
    return _client


# ---------------------------------------------------------------------------
# Step 1 — DuckDuckGo search
# ---------------------------------------------------------------------------
def _build_site_filter() -> str:
    """Return an OR-joined ``site:`` filter string for the trusted sources."""
    return " OR ".join(f"site:{s}" for s in _TRUSTED_SITES)


def _search_claim(claim: str) -> list[dict[str, str]]:
    """Search the claim against trusted Indonesian publishers via DuckDuckGo.

    Uses the ``DDGS().text()`` client from the ``ddgs`` library.
    No API key is needed — the library scrapes DuckDuckGo's HTML results
    directly, so it works out of the box.

    The ``region="id-id"`` parameter biases results toward Indonesian-language
    content and Indonesian web sources.  ``max_results`` is capped at 3 to
    keep scraping fast.

    Parameters
    ----------
    claim : str
        The Indonesian claim to search for.

    Returns
    -------
    list of dicts, each with ``title`` and ``url``.  Length <=
    ``_MAX_RESULTS``.
    """
    query = f"{claim} {_build_site_filter()}"

    with DDGS() as ddgs:
        results = ddgs.text(
            query,
            region=_SEARCH_REGION,
            max_results=_MAX_RESULTS,
        )

    hits: list[dict[str, str]] = []
    for r in results:
        url = r.get("href", "")
        if not url:
            continue
        hits.append(
            {
                "title": r.get("title", ""),
                "url": url,
            }
        )
        if len(hits) >= _MAX_RESULTS:
            break

    _LOG.info(
        "DuckDuckGo returned %d results for claim: %.60s",
        len(hits),
        claim,
    )
    return hits


# ---------------------------------------------------------------------------
# Step 2 — Article text extraction
# ---------------------------------------------------------------------------
def _fetch_page(url: str) -> str | None:
    """Fetch a page with retry logic, using httpx with HTTP/2.

    Returns the HTML text on success, or None on failure after all retries.
    """
    client = _get_client()

    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.get(url)
            resp.raise_for_status()

            # Check for suspiciously small / blocked responses
            if len(resp.text) < 1000:
                _LOG.warning(
                    "Response from %s is too small (%d chars) on attempt %d — likely blocked or CAPTCHA",
                    url,
                    len(resp.text),
                    attempt + 1,
                )
                if attempt < _MAX_RETRIES - 1:
                    _RETRY_DELAY * (attempt + 1)
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                return None

            return resp.text

        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            _LOG.warning(
                "Attempt %d/%d failed for %s: %s",
                attempt + 1,
                _MAX_RETRIES,
                url,
                exc,
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))

    return None


def _extract_article_text(url: str) -> str:
    """Scrape the main article text from a news URL.

    Scraping logic
    --------------
    1. **Fetch** the page with ``httpx`` (HTTP/2, browser-like headers)
       so news sites on datacenter IPs don't block the request.
    2. **Retry** up to 3 times with backoff on failure or small responses.
    3. **Parse** the HTML with ``BeautifulSoup`` (``html.parser`` backend).
    4. **Strip** non-content elements commonly containing noise.
    5. **Select** paragraphs using a prioritized list of CSS selectors.
    6. **Clean** the extracted text: drop short fragments (< 30 chars),
       deduplicate while preserving order, and join with double newlines.

    Parameters
    ----------
    url : str
        The article URL to scrape.

    Returns
    -------
    str — the extracted article body text, or an empty string if
    extraction fails.
    """
    html = _fetch_page(url)
    if html is None:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # --- Remove noise elements -------------------------------------------
    noise_keywords = [
        "nav", "menu", "sidebar", "footer", "header",
        "ad", "banner", "social", "share", "related",
        "recommend", "comment", "cookie", "popup",
        "modal", "newsletter", "subscribe",
    ]
    for tag in soup.find_all(
        lambda t: isinstance(t, Tag)
        and (
            t.name in ("script", "style", "nav", "header", "footer", "aside")
            or any(
                kw in (t.get("class") or [])
                or kw in (t.get("id") or "")
                for kw in noise_keywords
            )
        )
    ):
        tag.decompose()

    # --- Extract content paragraphs --------------------------------------
    paragraphs: list[str] = []
    for selector in _CONTENT_SELECTORS:
        elements = soup.select(selector)
        if not elements:
            continue
        for el in elements:
            text = el.get_text(strip=True)
            # Skip very short fragments (likely captions, timestamps, etc.)
            if len(text) > 30:
                paragraphs.append(text)
        if paragraphs:
            break  # stop at the first selector that yields results

    # --- Deduplicate while preserving order -------------------------------
    seen: set[str] = set()
    unique_paragraphs: list[str] = []
    for p in paragraphs:
        if p not in seen:
            seen.add(p)
            unique_paragraphs.append(p)

    article_text = "\n\n".join(unique_paragraphs)
    _LOG.info("Extracted %d chars from %s", len(article_text), url)
    return article_text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def verify_claim(claim: str) -> dict[str, Any]:
    """End-to-end text-based claim verification pipeline.

    Parameters
    ----------
    claim : str
        The Indonesian political claim to verify.

    Returns
    -------
    dict with the following structure::

        {
            "claim": str,               # original claim
            "sources": [                # trusted publisher filter used
                "turnbackhoax.id",
                "kompas.com",
                "tirto.id",
                "tempo.co",
            ],
            "articles": [
                {
                    "title": str,       # search result title
                    "url": str,         # article URL
                    "text": str,        # scraped article body
                },
                ...
            ],
        }
    """
    # 1. Search
    search_results = _search_claim(claim)
    if not search_results:
        return {
            "claim": claim,
            "sources": _TRUSTED_SITES,
            "articles": [],
            "error": "No results from trusted publishers.",
        }

    # 2. Scrape each URL
    articles: list[dict[str, str]] = []
    for result in search_results:
        text = _extract_article_text(result["url"])
        articles.append(
            {
                "title": result["title"],
                "url": result["url"],
                "text": text,
            }
        )

    return {
        "claim": claim,
        "sources": _TRUSTED_SITES,
        "articles": articles,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print(
            "Usage: python -m src.transformers.search_agent "
            '"<Indonesian claim to verify>"'
        )
        sys.exit(1)

    claim_text = " ".join(sys.argv[1:])
    result = verify_claim(claim_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
