"""Macro event fetchers for BATDETECTIVE.

Each fetcher returns a list of MacroEvent dicts with the same shape
(see core/batdetective.py for the contract). All fetchers must:

  - Return [] on any error (do NOT raise — outage on one source must
    not stop the whole BATDETECTIVE cycle).
  - Be self-contained: no shared HTTP session, no shared cache.
  - Respect a default 4-hour lookback window unless caller overrides.

The minimum viable implementation supports Banxico via RSS. BCRA, Fed,
and GDELT have stub implementations returning [] — see TODO markers in
each file.
"""

from .banxico import fetch_banxico_events
from .bcra import fetch_bcra_events
from .fed import fetch_fed_events
from .gdelt import fetch_gdelt_events

__all__ = [
    "fetch_banxico_events",
    "fetch_bcra_events",
    "fetch_fed_events",
    "fetch_gdelt_events",
]
