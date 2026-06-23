---
name: media-verifier
description: >
  KonteksMedia media-verification pipeline.  Given an Indonesian political
  quote or claim, searches YouTube for long-form videos, fetches the
  Indonesian transcript, fuzzy-matches the quote to find its timestamp,
  and returns a structured 2-minute context window (before / quote / after).
version: 0.1.0
required_environment_variables:
  - YOUTUBE_API_KEY
---

# Media Verifier — KonteksMedia Pipeline

## Overview

This skill triggers the **KonteksMedia** backend engine to verify whether
an Indonesian political quote is presented in or out of context.  The
pipeline:

1. Searches YouTube (Data API v3) for long-form videos matching the claim.
2. Fetches the Indonesian transcript via `youtube-transcript-api`.
3. Fuzzy-matches the claim against transcript segments using `rapidfuzz`.
4. Extracts a 2-minute text buffer before and after the matched quote.
5. Returns a structured timeline with timestamps and confidence score.

## Required Setup

```bash
cd konteks-media/backend_engine
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set the YouTube API key:

```bash
echo 'YOUTUBE_API_KEY=your_key_here' > .env
```

## Execution Workflow

When the user asks to verify a claim or quote:

1. **Confirm the API key is available.**  
   Check `YOUTUBE_API_KEY` in the environment.  If missing, prompt the
   user to provide it and write it to `.env` (do not echo it back).

2. **Run the pipeline:**

   ```bash
   cd konteks-media/backend_engine
   source .venv/bin/activate
   python main.py "<the Indonesian quote or claim>"
   ```

   Or, for programmatic use within a Python session:

   ```python
   from src.transformers.search_agent import verify_claim
   result = verify_claim("<the Indonesian quote or claim>")
   ```

3. **Format the output as a structural timeline.**  
   Present the result to the user in this format:

   ```
   📺 Video: {title} — {channel}
   🔗 URL: {url}
   ⏱️  Timestamp: {start_human} ({start_sec}s)
   🎯 Match Confidence: {match_confidence}/100

   ── Context Window ──
   ⬅️  BEFORE (2 min):
   {before}

   💬 QUOTE:
   {quote}

   ➡️  AFTER (2 min):
   {after}
   ```

4. **Handle errors gracefully.**  
   - If no videos are found, inform the user and suggest rephrasing.
   - If no Indonesian transcript is available, report which videos were tried.
   - If the fuzzy-match confidence is below 55, warn the user that the
     match may be unreliable.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Search order | `relevance` | YouTube search ranking |
| Video duration | `long` | Only videos > 20 min |
| Max results | 5 | Candidate videos tried |
| Language bias | `id` | Indonesian relevance |
| Fuzzy threshold | 55 | `rapidfuzz.partial_ratio` cutoff |
| Context radius | 120 s | 2-minute buffer each side |

## Future Enhancements (v0.2+)

- Integrate `src/extractors/video_parser.py` for richer metadata display.
- Add multi-language transcript fallback (e.g., `en` → translate).
- Add a FastAPI endpoint for programmatic access.
- Integrate an LLM verdict layer on top of the context window.
