---
name: media-verifier
description: >
  DoksliPlis text-based news verification pipeline.  Given an Indonesian
  political claim, searches trusted Indonesian publishers via DuckDuckGo,
  scrapes the top 3 article texts, and evaluates the claim against the
  extracted ground-truth content to determine if it is true, false, or
  taken out of context.
version: 0.3.0
required_environment_variables: []
---

# Media Verifier — DoksliPlis Text-Based Pipeline

## Overview

This skill triggers the **DoksliPlis** backend engine to verify whether
an Indonesian political claim is supported, refuted, or taken out of context
by trusted news publishers.  The pipeline:

1. Queries **DuckDuckGo** (via the ``duckduckgo_search`` library) with the
   claim, scoped to trusted Indonesian publishers via `site:` operators
   and locked to the Indonesia region (`region="id-id"`).
2. Takes the top 3 URL results (extracted from the `href` field).
3. Scrapes the main article text from each URL using `requests` + `beautifulsoup4`.
4. Returns a structured JSON payload with the claim, URLs, and extracted text.
5. **The LLM (you) evaluates the claim** against the scraped articles and
   renders a verdict: **TRUE**, **FALSE**, or **OUT OF CONTEXT**.

**No API keys required** — DuckDuckGo search is free and works out of the box.

## Required Setup

```bash
cd backend_engine
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

That's it — no `.env` file or API keys needed.

## Execution Workflow

When the user asks to verify a claim:

1. **Run the pipeline to fetch ground-truth articles:**

   ```bash
   cd backend_engine
   source .venv/bin/activate
   python main.py "<the Indonesian claim to verify>"
   ```

   This returns a JSON payload with `claim`, `sources`, and `articles`
   (each with `title`, `url`, `text`).

2. **Evaluate the claim yourself against the scraped text.**
   Read the extracted article texts and determine:

   - **TRUE** — The articles directly support the claim.
   - **FALSE** — The articles directly contradict the claim.
   - **OUT OF CONTEXT** — The articles mention related facts but the
     claim misrepresents or cherry-picks them.
   - **INSUFFICIENT EVIDENCE** — The articles don't contain enough
     information to verify or refute the claim.

3. **Present the verdict to the user in this format:**

   ```
   🔍 Claim: "{claim}"

   📰 Ground-Truth Sources:
   1. {title} — {url}
   2. {title} — {url}
   3. {title} — {url}

   ⚖️ Verdict: {TRUE | FALSE | OUT OF CONTEXT | INSUFFICIENT EVIDENCE}

   📝 Reasoning:
   {Your analysis citing specific evidence from the articles}
   ```

## Trusted Publishers

| Domain            | Type            |
|-------------------|-----------------|
| `turnbackhoax.id` | Fact-checking   |
| `kompas.com`      | Mainstream news |
| `tirto.id`        | Digital news    |
| `tempo.co`        | Investigative   |

## Parameters

| Parameter   | Default | Description                              |
|-------------|---------|------------------------------------------|
| Max results | 3       | Articles fetched & scraped               |
| Region      | `id-id` | DuckDuckGo region (Indonesia)           |
| Timeout     | 10 s    | HTTP request timeout per article         |
| Sites       | 4       | Trusted publishers (see table above)     |

## Error Handling

- If no search results are returned, inform the user and suggest
  rephrasing the claim or checking spelling.
- If an article URL fails to fetch or returns empty text, note which
  source was skipped and continue with the remaining articles.

## Future Enhancements (v0.4+)

- Add more trusted publishers (e.g., `detik.com`, `cnnindonesia.com`).
- Implement article text caching to avoid re-scraping.
- Add a FastAPI endpoint for programmatic access.
- Integrate an automated LLM verdict via structured prompting.
