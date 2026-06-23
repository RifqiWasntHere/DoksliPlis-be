"""
search_agent.py — Ground-Truth News Search & Article Extraction.

This is the text-based MVP of DoksliPlis. Given a textual claim (e.g. an
Indonesian political claim), the agent:

1. Queries **DuckDuckGo** (via the ``ddgs`` library) with the
   claim, scoped to trusted Indonesian publishers via ``site:`` operators
   and locked to the Indonesia region (``region="id-id"``).
2. Takes the top 3 URL results (extracted from the ``href`` field).
3. Scrapes the main article text from each URL using ``requests`` + ``beautifulsoup4``.
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
from typing import Any

import requests
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
_MAX_RESULTS = 3

# DuckDuckGo region code for Indonesia.
_SEARCH_REGION = "id-id"

# HTTP request timeout in seconds.
_REQUEST_TIMEOUT = 10

# User-Agent header to avoid being blocked by news sites.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en-US;q=0.9,en;q=0.8",
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
def _extract_article_text(url: str) -> str:
    """Scrape the main article text from a news URL.

    Scraping logic
    --------------
    1. **Fetch** the page with ``requests.get`` using a realistic User-Agent
       so news sites don't return 403 / bot walls.
    2. **Parse** the HTML with ``BeautifulSoup`` (``html.parser`` backend —
       no extra native deps needed).
    3. **Strip** non-content elements that commonly contain noise:
       ``<script>``, ``<style>``, ``<nav>``, ``<header>``, ``<footer>``,
       ``<aside>``, and any element whose class/id contains ``nav``,
       ``menu``, ``sidebar``, ``footer``, ``header``, ``ad``, ``banner``,
       ``social``, ``share``, ``related``, ``recommend``, ``comment``,
       ``cookie``, ``popup``, ``modal``, ``newsletter``, ``subscribe``.
    4. **Select** paragraphs using a prioritized list of CSS selectors
       (``_CONTENT_SELECTORS``).  We try the most specific pattern first
       (``article p``) and fall back to broader ones (``main p``, then
       ``p``).  The first selector that yields text wins.
    5. **Clean** the extracted text: drop short fragments (< 30 chars),
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
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        _LOG.warning("Failed to fetch %s: %s", url, exc)
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

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
