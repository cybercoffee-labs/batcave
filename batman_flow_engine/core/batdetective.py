"""
BATDETECTIVE — Macro Intelligence Orchestrator

Burry/Dalio-style "detective mode" intelligence for the human operator.
NOT a bot. NOT autonomous. Just a clean pipeline:

    Macro fetchers → impact rules → confidence threshold → alerts log

Cycle flow:
  1. Fan out across configured macro sources (Banxico, Fed, GDELT, BCRA).
  2. Each source returns a list of MacroEvent dicts (or [] on error).
  3. For each event, run apply_impact_rules → impact dict.
  4. If confidence ≥ threshold AND scanners are affected → format + persist.
  5. Return the list of alerts so the engine can include them in latest.json
     and Streamlit can render them on the next refresh.

This module is engine-cycle-friendly: it's safe to call from
engine.run_engine() once per cycle. Cost is dominated by HTTP calls
(~3-5s with 4 sources; less with caching at the fetcher level if added
later).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Iterable

from core.macro_alerts import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    format_alert,
    save_alert,
)
from core.macro_fetchers import (
    fetch_banxico_events,
    fetch_bcra_events,
    fetch_fed_events,
    fetch_gdelt_events,
)
from core.macro_rules import apply_impact_rules

logger = logging.getLogger("batman.batdetective")

# Tests, cron-quick runs, and air-gapped environments can bypass the
# network-dependent fetchers entirely with this env var. Anything truthy
# (non-empty, not "0"/"false") disables the cycle. Returns [] cleanly.
DISABLE_ENV = "BATMAN_DISABLE_BATDETECTIVE"


def _is_disabled() -> bool:
    val = os.environ.get(DISABLE_ENV, "").strip().lower()
    return val not in ("", "0", "false", "no")


# Each source is a (name, fetcher_callable) pair so we can iterate, log
# uniformly, and skip a single bad source without aborting the cycle.
DEFAULT_SOURCES: tuple[tuple[str, Callable[..., list[dict[str, Any]]]], ...] = (
    ("banxico", fetch_banxico_events),
    ("bcra", fetch_bcra_events),
    ("fed", fetch_fed_events),
    ("gdelt", fetch_gdelt_events),
)


def _fetch_all(
    sources: Iterable[tuple[str, Callable[..., list[dict[str, Any]]]]],
    hours_back: int,
) -> list[dict[str, Any]]:
    """Sequentially fetch from each source. Errors in one don't kill the rest."""
    events: list[dict[str, Any]] = []
    for name, fetcher in sources:
        try:
            batch = fetcher(hours_back=hours_back)
        except Exception as exc:
            logger.warning("BATDETECTIVE source %s raised (skipping): %s", name, exc)
            continue
        if not isinstance(batch, list):
            logger.warning("BATDETECTIVE source %s returned non-list (%s); skipping", name, type(batch).__name__)
            continue
        events.extend(batch)
    return events


def run_batdetective_cycle(
    hours_back: int = 4,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    sources: Iterable[tuple[str, Callable[..., list[dict[str, Any]]]]] | None = None,
) -> list[dict[str, Any]]:
    """Run one BATDETECTIVE cycle and return the list of generated alerts.

    Args:
        hours_back: lookback window passed to each fetcher.
        confidence_threshold: alerts below this confidence are dropped.
        sources: override the default sources (for testing).

    Returns:
        List of alert dicts (also persisted to storage/logs/macro_alerts.jsonl).
        Empty list on any fatal error or when no rules fire.
    """
    if sources is None and _is_disabled():
        logger.info("BATDETECTIVE cycle SKIPPED (%s set)", DISABLE_ENV)
        return []

    sources = tuple(sources) if sources is not None else DEFAULT_SOURCES
    logger.info(
        "BATDETECTIVE cycle start (sources=%d, lookback=%dh, threshold=%.2f)",
        len(sources),
        hours_back,
        confidence_threshold,
    )

    try:
        events = _fetch_all(sources, hours_back)
    except Exception as exc:
        logger.error("BATDETECTIVE fetch fan-out failed: %s", exc, exc_info=True)
        return []

    logger.info("BATDETECTIVE: fetched %d total macro events", len(events))

    alerts: list[dict[str, Any]] = []
    for event in events:
        try:
            impact = apply_impact_rules(event)
        except Exception as exc:
            logger.warning("Impact rules raised on event headline=%r: %s", event.get("headline", "?"), exc)
            continue

        if not impact.get("impact_on_scanners"):
            # No rule fired → don't even consider this an alert candidate.
            continue
        if impact.get("confidence", 0.0) < confidence_threshold:
            logger.debug(
                "BATDETECTIVE: suppressed event (confidence=%.2f < threshold=%.2f) headline=%r",
                impact.get("confidence", 0.0),
                confidence_threshold,
                event.get("headline", "?"),
            )
            continue

        alert = format_alert(event, impact)
        if save_alert(alert):
            alerts.append(alert)
            logger.info(
                "BATDETECTIVE alert: [%s/%s] %s (confidence=%.0f%%, scanners=%s)",
                event.get("source"),
                event.get("severity"),
                event.get("headline"),
                impact["confidence"] * 100,
                ",".join(alert["scanners_affected"]),
            )

    logger.info("BATDETECTIVE cycle complete: %d alerts generated", len(alerts))
    return alerts


def main() -> int:
    """CLI: python -m core.batdetective. Prints alerts as JSON-lines to stdout."""
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    alerts = run_batdetective_cycle()
    for alert in alerts:
        print(json.dumps(alert, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
