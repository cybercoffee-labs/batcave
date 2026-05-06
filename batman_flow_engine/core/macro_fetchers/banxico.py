"""Fetch Mexico macro events from Banxico (Banco de México) RSS feed.

Source: https://www.banxico.org.mx/comunicados/rss/comunicados.xml

Banxico publishes communiqués (rate decisions, inflation reports, FX
interventions) as an RSS feed. We parse it directly with stdlib XML —
no extra dependency. Free, no auth, no rate limits worth noting.

Each parsed item becomes a MacroEvent dict:
    {
        "source": "banxico",
        "event_type": "rate_decision" | "inflation_report" | "fx_intervention" | "currency_move" | "central_bank",
        "headline": str,
        "timestamp": ISO-8601,
        "severity": "low" | "medium" | "high" | "critical",
        "currencies_affected": ["MXN", ...],
        "description": str (truncated to 500),
        "source_url": str,
    }
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

logger = logging.getLogger("batman.macro_fetchers.banxico")

BANXICO_RSS_URL = "https://www.banxico.org.mx/comunicados/rss/comunicados.xml"
HTTP_TIMEOUT = 5  # seconds — Banxico is fast under normal conditions; cap blast radius on outages
USER_AGENT = "batman-lab/1.0 (+https://github.com/cybercoffee-labs/batcave)"


def _classify_event(headline: str) -> tuple[str, str]:
    """Inspect headline keywords to classify event type and severity.

    Returns (event_type, severity).

    Spanish + English keywords because Banxico publishes in Spanish.
    """
    h = headline.lower()
    if "tasa" in h or "tipo de interés" in h or "rate" in h:
        # Rate decisions are high-severity if they include "decisión"; otherwise
        # they're informational about the policy context.
        if "decisión" in h or "decision" in h:
            return "rate_decision", "high"
        return "rate_decision", "medium"
    if "inflación" in h or "inflation" in h:
        return "inflation_report", "high"
    if "intervención" in h or "intervention" in h:
        return "fx_intervention", "critical"
    if "peso" in h or "mxn" in h or "tipo de cambio" in h:
        return "currency_move", "medium"
    return "central_bank", "low"


def _parse_published(raw: str | None) -> datetime:
    """Parse RFC 822 (RSS) date or fall back to now()."""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _fetch_rss_xml(url: str = BANXICO_RSS_URL) -> str | None:
    """Fetch the RSS feed body. Returns None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 — known fixed URL
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        logger.warning("Banxico RSS fetch failed (network): %s", exc)
        return None
    except Exception as exc:
        logger.warning("Banxico RSS fetch failed (%s): %s", type(exc).__name__, exc)
        return None


def fetch_banxico_events(hours_back: int = 4) -> list[dict[str, Any]]:
    """Fetch Banxico events from the last *hours_back* hours.

    Returns [] on any error. Never raises.
    """
    body = _fetch_rss_xml()
    if body is None:
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("Banxico RSS parse failed: %s", exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    events: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        published = _parse_published(item.findtext("pubDate"))
        if published < cutoff:
            continue

        event_type, severity = _classify_event(title)
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()

        events.append(
            {
                "source": "banxico",
                "event_type": event_type,
                "headline": title,
                "timestamp": published.isoformat(),
                "severity": severity,
                "currencies_affected": ["MXN"],
                "description": description[:500],
                "source_url": link,
            }
        )

    logger.info("Banxico: fetched %d events (lookback=%dh)", len(events), hours_back)
    return events
