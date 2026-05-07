"""Fetch Argentina macro events from BCRA (Banco Central de la República Argentina).

Source candidate: https://www.bcra.gob.ar/Noticias/comunicados.asp (HTML, no RSS).

STATUS: stub. The BCRA site does not expose an RSS feed at a stable URL,
so a proper fetcher would need an HTML scrape with bs4 or lxml. We
deliberately defer that until BATDETECTIVE has been validated end-to-end
on the simpler Banxico path. Returning [] keeps the orchestrator working;
when this is implemented, the rest of BATDETECTIVE picks it up automatically.

Tracked under audit Section L.2 — BATDETECTIVE expansion.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("batman.macro_fetchers.bcra")


def fetch_bcra_events(hours_back: int = 4) -> list[dict[str, Any]]:
    """Stub: returns []. See module docstring."""
    logger.debug("BCRA fetcher is a stub — returning [] (lookback=%dh)", hours_back)
    return []
