"""
main.py — DoksliPlis Backend Engine entry point.

Provides a CLI and a thin wrapper around the search agent so the
pipeline can be invoked directly or imported by a future FastAPI /
Streamlit layer.

Example of usage :
CLI:
    $ python main.py "PDIP akan mendukung Prabowo di 2029"
"""

from __future__ import annotations

import json
import logging
import sys

from src.transformers.search_agent import verify_claim

_LOG = logging.getLogger(__name__)


def run_pipeline(claim: str) -> dict:
    """Execute the full text-verification pipeline and return the result dict.

    Parameters
    ----------
    claim : str
        Indonesian political claim to verify.

    Returns
    -------
    dict — see ``verify_claim`` return spec in ``search_agent.py``.
    """
    _LOG.info("Pipeline started for claim: %.80s", claim)
    result = verify_claim(claim)
    article_count = len(result.get("articles", []))
    _LOG.info("Pipeline finished.  Articles fetched=%d", article_count)
    return result


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if len(sys.argv) < 2:
        print('Usage: python main.py "<Indonesian claim to verify>"')
        sys.exit(1)

    claim_text = " ".join(sys.argv[1:])
    result = run_pipeline(claim_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
