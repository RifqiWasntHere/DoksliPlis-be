# DoksliPlis

**Because believing everything on the internet is a dangerous hobby, maybe ? man im just frustated with the social media right now..**

So.. anyway, here's DoksliPlis. A fact-checking sidekick built for Indonesian political claims (atleast thats the 1.0 idea of it). You feed it a claim, something like _"Ibu Ibu Mengerumuni Jalan Untuk Demo Mendukung MBG"_, and it goes hunting across trusted Indonesian publishers to find out if there's any truth to it.

This repo is the **backend engine** of DoksliPlis. It handles the searching, scraping, and article extraction so the rest of the project can do the smart stuffy stuffy tuff thingamajigs later (LLM verdicts, a nice UI, maybe even a mobile app if we're feeling ambitious).

---

## What It Does Right Now

1. **Searches DuckDuckGo** scoped to trusted Indonesian news sites (turnbackhoax.id, kompas.com, tirto.id, tempo.co) — no API key needed.
2. **Scrapes the top 3 results** and extracts clean article text by stripping nav bars, ads, footers, and other noise.
3. **Returns structured JSON** with the claim, source URLs, and extracted article bodies — ready for evaluation.

The verdict logic (Classifications of TRUE / FALSE) is intentionally left to the calling layer. I intended this backend to just only fetch the ground truth.

---

## Quick Start

```bash
cd backend_engine
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then run a claim:

```bash
python main.py "Whatever vile claims you find on the internet"
```

You'll get a JSON response with the claim, sources, and scraped article texts (thank you DuckDuckGo).

---

## Project Structure

```
DoksliPlis/
├── backend_engine/
│   ├── main.py                    # CLI entry point + pipeline wrapper
│   ├── requirements.txt           # ddgs, requests, beautifulsoup4, python-dotenv
│   └── src/
│       ├── extractors/
│       │   └── video_parser.py    # YouTube video metadata fetcher (future use)
│       └── transformers/
│           └── search_agent.py    # DuckDuckGo search + article scraping
└── README.md                      # You are here
```

---

## Trusted Publishers

| Site              | Why It's Here                    |
|-------------------|----------------------------------|
| `turnbackhoax.id` | Fact-checking, first by default  |
| `kompas.com`      | Mainstream, widely cited          |
| `tirto.id`        | Digital-native, deep reporting   |
| `tempo.co`        | Investigative journalism         |

The search query uses `site:` operators to scope results to these domains only. No random blogs, no social media noise.

---

## Design Choices (The "Why")

- **DuckDuckGo over Google**: Free, no API key, and honestly good enough for this use case. Google's Custom Search API costs money and DuckDuckGo's HTML results are perfectly scrapeable via the `ddgs` library.
- **BeautifulSoup over headless browsers**: We're extracting article text, not rendering interactive pages. No need to spin up a Chrome instance for this.
- **No API keys in the repo**: Everything here works out of the box. The `.env` file is for future YouTube API integration, not for the current text pipeline.
- **Modular extractors**: The `extractors/` directory is set up for future sources (YouTube videos, podcasts, etc.) even though only the search agent is active today.

---

## What's Coming

This is the foundation. The full DoksliPlis project will layer on top of this:

- **LLM-powered verdicts** — feed the scraped articles to a model and get a structured verdict with reasoning.
- **A proper API** — FastAPI wrapper so the backend can serve a frontend.
- **More sources** — YouTube video transcripts, more publishers, maybe even social media monitoring.
- **A frontend** — because running `python main.py` in a terminal isn't for everyone (though it is pretty satisfying).

---

## Tech Stack

- **Python 3.10+**
- `ddgs` — DuckDuckGo search (no API key)
- `requests` + `beautifulsoup4` — HTTP + HTML parsing
- `python-dotenv` — environment management
- `google-api-python-client` — YouTube Data API (for upcoming video support)

---

## Contributing

This is a passion project, not a startup. If you want to add more publishers, improve the scraping selectors, or wire up the YouTube pipeline, go for it. Open a PR, open an issue, or just yell into my already tinnitus ears cuz i gotchu.

---

## License

Do whatever you want with it. Just don't use it to spread misinformation. That would be ironic.
