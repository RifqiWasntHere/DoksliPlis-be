"""
cleaner.py — Text preprocessing utilities for scraped articles.

Takes raw article text (as extracted by the search agent) and applies
normalization steps to make it cleaner for downstream consumption
(LLM evaluation, API responses, display).

Usage
-----
>>> from src.preprocessing.cleaner import clean_article
>>> clean = clean_article(raw_text)
"""

from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Common noise patterns injected by scrapers / ad widgets / share buttons.
_NOISE_PATTERNS = [
    re.compile(r"Baca juga:.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Baca artikel lainnya.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Lihat juga:.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Share this article.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Bagikan artikel ini.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Advertisement\s*", re.IGNORECASE),
    re.compile(r"Iklan\s*", re.IGNORECASE),
    re.compile(r"Scroll to continue.*", re.IGNORECASE),
    re.compile(r"Subscribe to our newsletter.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Sign up for.*newsletter.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"Editor:.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Penulis:.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Reporter:.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Foto:.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Sumber:.*$", re.IGNORECASE | re.MULTILINE),
]


def _strip_noise(text: str) -> str:
    """Remove common boilerplate / noise patterns from scraped text."""
    result = text
    for pat in _NOISE_PATTERNS:
        result = pat.sub("", result)
    return result


def _normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph breaks."""
    # Replace 3+ newlines with exactly 2 (paragraph separator)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace multiple spaces/tabs with single space
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


def _normalize_unicode(text: str) -> str:
    """Normalize unicode characters to NFC form and strip control chars."""
    text = unicodedata.normalize("NFC", text)
    # Remove zero-width characters and other invisible unicode noise
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)
    return text


def _normalize_quotes(text: str) -> str:
    """Normalize fancy quotes and dashes to ASCII equivalents."""
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_article(text: str) -> str:
    """Apply all preprocessing steps to raw article text.

    Pipeline
    --------
    1. Unicode normalization (NFC, strip invisible chars)
    2. Quote/dash normalization
    3. Noise pattern removal (share buttons, ad labels, etc.)
    4. Whitespace cleanup

    Parameters
    ----------
    text : str
        Raw article text as scraped by the search agent.

    Returns
    -------
    str — cleaned text, or empty string if input was empty.
    """
    if not text or not text.strip():
        return ""

    result = text
    result = _normalize_unicode(result)
    result = _normalize_quotes(result)
    result = _strip_noise(result)
    result = _normalize_whitespace(result)
    return result


def clean_articles(articles: list[dict[str, str]]) -> list[dict[str, str]]:
    """Clean the ``text`` field of each article in a list.

    Parameters
    ----------
    articles : list of dict
        Each dict must have a ``"text"`` key (as returned by ``verify_claim``).

    Returns
    -------
    list of dict — same structure, with ``"text"`` cleaned in place.
    """
    for article in articles:
        article["text"] = clean_article(article.get("text", ""))
    return articles
