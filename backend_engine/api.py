"""
api.py — FastAPI application for DoksliPlis Backend Engine.

Provides a REST endpoint to verify Indonesian political claims against
trusted news publishers.

Usage
-----
    $ cd backend_engine
    $ source .venv/bin/activate
    $ uvicorn api:app --reload --port 8000

Then POST to /verify:
    curl -X POST http://localhost:8000/verify \
      -H "Content-Type: application/json" \
      -d '{"claim": "PDIP akan mendukung Prabowo di 2029"}'
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from src.transformers.search_agent import verify_claim
from src.preprocessing.cleaner import clean_articles

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    """Schema for the /verify endpoint request body."""
    claim: str = Field(
        ...,
        min_length=1,
        description="Indonesian political claim to verify",
        examples=["PDIP akan mendukung Prabowo di 2029"],
    )


class ArticleResponse(BaseModel):
    title: str
    url: str
    text: str


class VerifyResponse(BaseModel):
    claim: str
    sources: list[str]
    articles: list[ArticleResponse]


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DoksliPlis Backend Engine",
    description="Fact-checking API for Indonesian political claims against trusted publishers.",
    version="0.1.0",
)


@app.post(
    "/verify",
    response_model=VerifyResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Verify a claim",
    description="Search trusted Indonesian publishers for articles related to the claim and return cleaned article text.",
)
async def verify_endpoint(payload: VerifyRequest) -> dict[str, Any]:
    """Verify an Indonesian political claim against trusted news sources.

    Steps
    -----
    1. Search DuckDuckGo scoped to trusted publishers.
    2. Scrape article text from the top 3 results.
    3. Run preprocessing/cleaning on extracted text.
    4. Return structured response.
    """
    try:
        result = verify_claim(payload.claim)
    except Exception as exc:
        _LOG.exception("Pipeline failed for claim: %.60s", payload.claim)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc}",
        ) from exc

    # Preprocess: clean article text before returning
    result["articles"] = clean_articles(result.get("articles", []))

    if not result["articles"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No articles found for this claim. Try rephrasing.",
        )

    return result


@app.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "doksliplis-backend"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
