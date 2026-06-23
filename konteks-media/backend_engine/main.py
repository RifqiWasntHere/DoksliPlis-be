"""
main.py — KonteksMedia Backend Engine entry point.

Provides a CLI and a thin wrapper around the search agent so the
pipeline can be invoked directly or imported by a future FastAPI /
Streamlit layer.

Examples
--------
CLI:
    $ python main.py "saya tidak pernah korupsi"

Programmatic:
    >>> from main import run_pipeline
    >>> result = run_pipeline("saya tidak pernah korupsi")
"""

from __future__ import annotations

import json
import logging
import sys

from dotenv import load_dotenv

from src.transformers.search_agent import verify_claim

load_dotenv()

_LOG = logging.getLogger(__name__)


def run_pipeline(claim: str, api_key: str | None = None) -> dict:
    """Execute the full media-verification pipeline and return the result dict.

    Parameters
    ----------
    claim : str
        Indonesian political quote or claim to verify.
    api_key : str, optional
        Overrides the ``YOUTUBE_API_KEY`` environment variable.

    Returns
    -------
    dict — see ``verify_claim`` return spec in ``search_agent.py``.
    """
    _LOG.info("Pipeline started for claim: %.80s", claim)
    result = verify_claim(claim, api_key=api_key)
    _LOG.info("Pipeline finished.  Confidence=%s", result.get("match_confidence", "N/A"))
    return result


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if len(sys.argv) < 2:
        print('Usage: python main.py "<Indonesian quote to verify>"')
        sys.exit(1)

    claim_text = " ".join(sys.argv[1:])
    result = run_pipeline(claim_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
