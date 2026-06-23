"""
video_parser.py — YouTube video metadata & candidate extraction.

Given a YouTube video ID, this module fetches the video's metadata
(title, description, channel, duration) via the YouTube Data API and
provides a structured candidate dict for downstream transcript analysis.
"""

from typing import Any

from googleapiclient.discovery import build  # type: ignore


def fetch_video_details(api_key: str, video_id: str) -> dict[str, Any]:
    """Return metadata for a single YouTube video.

    Parameters
    ----------
    api_key : str
        YouTube Data API v3 key.
    video_id : str
        The 11-character YouTube video ID.

    Returns
    -------
    dict with keys: video_id, title, description, channel_title,
    published_at, duration (ISO 8601), view_count.
    """
    youtube = build("youtube", "v3", developerKey=api_key)
    resp = (
        youtube.videos()
        .list(part="snippet,statistics,contentDetails", id=video_id)
        .execute()
    )

    if not resp["items"]:
        raise ValueError(f"No video found for id={video_id}")

    item = resp["items"][0]
    snippet = item["snippet"]
    stats = item.get("statistics", {})
    details = item.get("contentDetails", {})

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "duration": details.get("duration", ""),
        "view_count": int(stats.get("viewCount", 0)),
    }
