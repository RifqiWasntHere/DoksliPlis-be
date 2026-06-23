"""
search_agent.py — YouTube Transcript Search & Contextual Quote Verification.

This is the core MVP of KonteksMedia. Given a textual claim (e.g. an
Indonesian political quote), the agent:

1. Searches YouTube for long-form videos whose titles/descriptions
   semantically overlap with the claim.
2. Fetches the Indonesian (``id``) transcript of the top-ranked video.
3. Fuzzy-matches the claim against every transcript segment to find the
   best alignment and its timestamp.
4. Extracts a *context window*: the 2-minute text buffer BEFORE the
   quote, the quote itself, and the 2-minute buffer AFTER it.

The result is a structured dictionary that downstream consumers (LLM
verifiers, Streamlit UIs, etc.) can render as a timeline.

Usage
-----
>>> from src.transformers.search_agent import verify_claim
>>> result = verify_claim("saya tidak pernah korupsi", api_key="YOUR_KEY")
>>> print(result["context_window"]["before"])
>>> print(result["context_window"]["quote"])
>>> print(result["context_window"]["after"])
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from googleapiclient.discovery import build  # type: ignore
from rapidfuzz import fuzz, process  # type: ignore
from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

load_dotenv()

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# YouTube search: bias toward long-form content (videos > 20 min).
_SEARCH_ORDER = "relevance"
_SEARCH_TYPE = "video"
_SEARCH_VIDEO_DURATION = "long"  # > 20 minutes
_SEARCH_MAX_RESULTS = 5

# Fuzzy-match threshold (0-100).  Tuned for Indonesian which has
# richer morphology than English; we accept slightly lower scores.
_FUZZY_MATCH_THRESHOLD = 55

# Context window radius in seconds.
_CONTEXT_RADIUS_SEC = 120  # 2 minutes


# ---------------------------------------------------------------------------
# Step 1 — YouTube search
# ---------------------------------------------------------------------------
def _search_videos(api_key: str, claim: str) -> list[dict[str, str]]:
    """Return up to ``_SEARCH_MAX_RESULTS`` video dicts from YouTube.

    Each dict carries ``video_id``, ``title``, ``channel``, and
    ``description`` (truncated to 300 chars to keep payloads small).
    """
    youtube = build("youtube", "v3", developerKey=api_key)
    request = youtube.search().list(
        q=claim,
        part="snippet",
        type=_SEARCH_TYPE,
        videoDuration=_SEARCH_VIDEO_DURATION,
        order=_SEARCH_ORDER,
        maxResults=_SEARCH_MAX_RESULTS,
        relevanceLanguage="id",  # bias results toward Indonesian
    )
    response = request.execute()

    hits: list[dict[str, str]] = []
    for item in response.get("items", []):
        vid = item["id"]["video_id"]
        snip = item["snippet"]
        hits.append(
            {
                "video_id": vid,
                "title": snip.get("title", ""),
                "channel": snip.get("channelTitle", ""),
                "description": snip.get("description", "")[:300],
            }
        )
    _LOG.info("Found %d candidate videos for claim: %.60s…", len(hits), claim)
    return hits


# ---------------------------------------------------------------------------
# Step 2 — Transcript fetching
# ---------------------------------------------------------------------------
def _fetch_transcript(video_id: str) -> list[dict[str, Any]]:
    """Fetch the Indonesian auto-generated or manual transcript.

    Returns a list of segments, each with ``text`` (str), ``start`` (float,
    seconds), and ``duration`` (float, seconds).

    Raises ``youtube_transcript_api.TranscriptDisabled`` or
    ``NoTranscriptFound`` if no Indonesian track exists — callers should
    catch and fall back to the next candidate video.
    """
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    # Prefer a manual Indonesian track, then auto-generated Indonesian.
    try:
        transcript = transcript_list.find_transcript(["id"])
    except Exception:
        # Fall back to any available transcript.
        transcript = transcript_list.find_transcript(
            transcript_list._manually_created_transcripts  # type: ignore
            or transcript_list._generated_transcripts  # type: ignore
        )

    segments = transcript.fetch()
    _LOG.info(
        "Fetched %d transcript segments for video %s (lang=%s)",
        len(segments),
        video_id,
        transcript.language_code,
    )
    return segments


# ---------------------------------------------------------------------------
# Step 3 — Fuzzy-match the claim inside the transcript
# ---------------------------------------------------------------------------
def _find_quote_timestamp(
    segments: list[dict[str, Any]],
    claim: str,
) -> tuple[int, float, str]:
    """Return ``(best_index, best_start_sec, best_text)``.

    Uses ``rapidfuzz.fuzz.partial_ratio`` to compare the claim against
    each segment's text.  ``partial_ratio`` is chosen because the claim
    may be a *substring* of a longer transcript segment (or vice-versa).

    Parameters
    ----------
    segments : list of transcript segments (from ``_fetch_transcript``).
    claim : the user-supplied quote to locate.

    Returns
    -------
    Tuple of (index into *segments*, start time in seconds, matched text).
    """
    texts = [seg["text"] for seg in segments]

    # rapidfuzz.process.extractOne is O(n) and returns (match, score, idx).
    best_text, best_score, best_idx = process.extractOne(
        claim,
        texts,
        scorer=fuzz.partial_ratio,
        score_cutoff=_FUZZY_MATCH_THRESHOLD,
    )

    if best_idx is None:
        # No segment crossed the threshold; pick the best available anyway
        # so the caller can decide what to do.
        best_text, best_score, best_idx = process.extractOne(
            claim, texts, scorer=fuzz.partial_ratio
        )
        _LOG.warning(
            "No segment crossed threshold %d; best score was %d",
            _FUZZY_MATCH_THRESHOLD,
            best_score,
        )

    best_start = segments[best_idx]["start"]
    _LOG.info(
        "Best match at index %d (%.1fs), score=%d: %.80s…",
        best_idx,
        best_start,
        best_score,
        best_text,
    )
    return best_idx, best_start, best_text


# ---------------------------------------------------------------------------
# Step 4 — Build the context window
# ---------------------------------------------------------------------------
def _build_context_window(
    segments: list[dict[str, Any]],
    match_index: int,
) -> dict[str, str]:
    """Extract 2-minute text buffers before and after the matched segment.

    The "before" buffer concatenates all segments whose *start* time is
    within ``_CONTEXT_RADIUS_SEC`` seconds before the match segment's start.
    The "after" buffer does the same forward in time.

    Returns
    -------
    dict with keys ``before``, ``quote``, ``after`` — each a plain string.
    """
    match_start = segments[match_index]["start"]
    match_end = match_start + segments[match_index].get("duration", 0)

    before_start = match_start - _CONTEXT_RADIUS_SEC
    after_end = match_end + _CONTEXT_RADIUS_SEC

    before_parts: list[str] = []
    after_parts: list[str] = []

    for i, seg in enumerate(segments):
        seg_start = seg["start"]
        seg_end = seg_start + seg.get("duration", 0)

        if i == match_index:
            continue  # the quote itself is handled separately

        if before_start <= seg_start < match_start:
            before_parts.append(seg["text"])
        elif match_end < seg_end <= after_end:
            after_parts.append(seg["text"])

    return {
        "before": " ".join(before_parts),
        "quote": segments[match_index]["text"],
        "after": " ".join(after_parts),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def verify_claim(
    claim: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """End-to-end claim verification pipeline.

    Parameters
    ----------
    claim : str
        The Indonesian political quote or claim to verify.
    api_key : str, optional
        YouTube Data API v3 key.  Falls back to ``YOUTUBE_API_KEY``
        environment variable.

    Returns
    -------
    dict with the following structure::

        {
            "claim": str,               # original claim
            "match_confidence": int,    # 0-100 fuzzy score
            "video": {
                "id": str,
                "title": str,
                "channel": str,
                "url": str,             # full watch URL
            },
            "timestamp": {
                "start_sec": float,     # quote start
                "start_human": str,     # HH:MM:SS
            },
            "context_window": {
                "before": str,          # ~2 min before
                "quote": str,           # matched segment
                "after": str,           # ~2 min after
            },
        }
    """
    key = api_key or os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise EnvironmentError(
            "YouTube API key required.  Set YOUTUBE_API_KEY in your "
            ".env file or pass api_key= directly."
        )

    # 1. Search
    candidates = _search_videos(key, claim)
    if not candidates:
        return {"claim": claim, "error": "No candidate videos found."}

    # 2. Try candidates until we get a transcript
    segments: list[dict[str, Any]] = []
    chosen_video: dict[str, str] = {}
    for candidate in candidates:
        try:
            segments = _fetch_transcript(candidate["video_id"])
            chosen_video = candidate
            break
        except Exception as exc:
            _LOG.warning(
                "Skipping %s: %s", candidate["video_id"], exc
            )
            continue

    if not segments:
        return {
            "claim": claim,
            "error": "No Indonesian transcript found in any candidate.",
        }

    # 3. Fuzzy-match
    best_idx, best_start, best_text = _find_quote_timestamp(segments, claim)

    # Re-score for the confidence field
    confidence = fuzz.partial_ratio(claim, best_text)

    # 4. Context window
    ctx = _build_context_window(segments, best_idx)

    # 5. Format timestamp
    hours, remainder = divmod(int(best_start), 3600)
    minutes, seconds = divmod(remainder, 60)
    ts_human = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return {
        "claim": claim,
        "match_confidence": confidence,
        "video": {
            "id": chosen_video["video_id"],
            "title": chosen_video["title"],
            "channel": chosen_video["channel"],
            "url": f"https://www.youtube.com/watch?v={chosen_video['video_id']}&t={int(best_start)}s",
        },
        "timestamp": {
            "start_sec": best_start,
            "start_human": ts_human,
        },
        "context_window": ctx,
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
            '"<Indonesian quote to verify>"'
        )
        sys.exit(1)

    claim_text = " ".join(sys.argv[1:])
    result = verify_claim(claim_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
