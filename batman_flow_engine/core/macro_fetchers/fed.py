"""Fetch Federal Reserve events from FRB news/events feeds.

Source candidates:
  - FOMC press conferences:   https://www.federalreserve.gov/feeds/press_all.xml
  - General press releases:   https://www.federalreserve.gov/feeds/press_release.xml
  - FRED data updates:        https://fred.stlouisfed.org/feed/

The FRB RSS feeds are reliable. This implementation uses the
press_all.xml feed and applies keyword classification similar to
banxico.py. Severity weighting biases towards FOMC + interest rates.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

logger = logging.getLogger("batman.macro_fetchers.fed")

FED_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
HTTP_TIMEOUT = 5
USER_AGENT = "batman-lab/1.0 (+https://github.com/cybercoffee-labs/batcave)"


def _classify(headline: str) -> tuple[str, str]:
    h = headline.lower()
    if "fomc" in h:
        return "rate_decision", "high"
    if "rate" in h or "interest" in h or "policy" in h:
        return "rate_decision", "high"
    if "inflation" in h or "cpi" in h or "ppi" in h:
        return "inflation_report", "high"
    if "employment" in h or "payroll" in h or "unemployment" in h:
        return "labor_report", "medium"
    if "balance sheet" in h or "qe" in h or "quantitative" in h:
        return "balance_sheet", "high"
    return "central_bank", "low"


def _parse_published(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _fetch_rss_xml(url: str = FED_RSS_URL) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        logger.warning("Fed RSS fetch failed (network): %s", exc)
        return None
    except Exception as exc:
        logger.warning("Fed RSS fetch failed (%s): %s", type(exc).__name__, exc)
        return None


def fetch_fed_events(hours_back: int = 4) -> list[dict[str, Any]]:
    """Fetch Federal Reserve events from the last *hours_back* hours."""
    body = _fetch_rss_xml()
    if body is None:
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("Fed RSS parse failed: %s", exc)
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

        event_type, severity = _classify(title)
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()

        events.append(
            {
                "source": "fed",
                "event_type": event_type,
                "headline": title,
                "timestamp": published.isoformat(),
                "severity": severity,
                "currencies_affected": ["USD"],
                "description": description[:500],
                "source_url": link,
            }
        )

    logger.info("Fed: fetched %d events (lookback=%dh)", len(events), hours_back)
    return events
