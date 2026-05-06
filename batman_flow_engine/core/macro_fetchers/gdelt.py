"""Fetch geopolitical events from GDELT 2.0 DOC API.

Source: https://api.gdeltproject.org/api/v2/doc/doc

GDELT classifies global news in real time. We use the DOC API in 'artlist'
mode to retrieve recent articles matching geopolitical keywords for our
target currencies (MXN, ARS) and crypto.

Endpoint pattern:
    https://api.gdeltproject.org/api/v2/doc/doc?query=<q>&mode=artlist&format=json&maxrecords=50&sort=DateDesc

Free, no auth. Rate limited; we respect it by limiting to maxrecords=50.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger("batman.macro_fetchers.gdelt")

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
HTTP_TIMEOUT = 5
USER_AGENT = "batman-lab/1.0 (+https://github.com/cybercoffee-labs/batcave)"

# Keywords that map an article to currency exposure.
DEFAULT_KEYWORDS = (
    "Mexico",
    "Argentina",
    "Federal Reserve",
    "FOMC",
    "Bitcoin",
    "stablecoin",
    "USDT",
)


def _query_for_keyword(keyword: str) -> str:
    """Build a GDELT DOC query for one keyword."""
    return urllib.parse.urlencode(
        {
            "query": keyword,
            "mode": "artlist",
            "format": "json",
            "maxrecords": "20",
            "sort": "DateDesc",
        }
    )


def _classify(headline: str, keyword: str) -> tuple[str, str, list[str]]:
    """Return (event_type, severity, currencies_affected)."""
    h = (headline or "").lower()
    k = keyword.lower()

    currencies: list[str] = []
    if "mexico" in k or "mexican" in h or "mxn" in h or "peso" in h:
        currencies.append("MXN")
    if "argentin" in k or "argentin" in h or "ars" in h:
        currencies.append("ARS")
    if "federal reserve" in k or "fomc" in k or "fed " in h or "powell" in h:
        currencies.append("USD")
    if "bitcoin" in k or "btc" in h:
        # Pseudo-currency for downstream rule mapping. Crypto-specific events
        # impact scanner A (cross-exchange) and E (funding) more than fiat.
        currencies.append("BTC")
    if "stablecoin" in k or "usdt" in h or "usdc" in h:
        currencies.append("STABLE")

    severity = "low"
    event_type = "geopolitical"
    if "war" in h or "sanction" in h or "crisis" in h or "default" in h or "depeg" in h:
        severity = "critical"
    elif "election" in h or "protest" in h or "strike" in h or "intervention" in h:
        severity = "high"
    elif "rate" in h or "policy" in h or "inflation" in h:
        severity = "medium"
        event_type = "central_bank"

    if "depeg" in h or "stablecoin" in h.replace("stablecoins", "stablecoin"):
        event_type = "stablecoin_event"

    return event_type, severity, currencies


def _fetch_keyword(keyword: str) -> list[dict[str, Any]]:
    url = f"{GDELT_DOC_API}?{_query_for_keyword(keyword)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        logger.warning("GDELT fetch failed for keyword=%r (network): %s", keyword, exc)
        return []
    except json.JSONDecodeError as exc:
        logger.warning("GDELT response is not JSON for keyword=%r: %s", keyword, exc)
        return []
    except Exception as exc:
        logger.warning("GDELT fetch failed for keyword=%r (%s): %s", keyword, type(exc).__name__, exc)
        return []

    return payload.get("articles", []) if isinstance(payload, dict) else []


def fetch_gdelt_events(
    keywords: Iterable[str] = DEFAULT_KEYWORDS,
    hours_back: int = 4,
) -> list[dict[str, Any]]:
    """Fetch GDELT events for *keywords* in the last *hours_back* hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    events: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for keyword in keywords:
        for article in _fetch_keyword(keyword):
            if not isinstance(article, dict):
                continue
            url = article.get("url")
            if not url or url in seen_urls:
                continue
            title = article.get("title", "")
            seen_at = article.get("seendate")
            try:
                # GDELT format: YYYYMMDDTHHMMSSZ
                ts = (
                    datetime.strptime(seen_at, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                    if seen_at
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                ts = datetime.now(timezone.utc)
            if ts < cutoff:
                continue

            event_type, severity, currencies = _classify(title, keyword)
            if not currencies:
                continue  # Article doesn't map to anything we care about.

            seen_urls.add(url)
            events.append(
                {
                    "source": "gdelt",
                    "event_type": event_type,
                    "headline": title,
                    "timestamp": ts.isoformat(),
                    "severity": severity,
                    "currencies_affected": currencies,
                    "description": article.get("snippet", "")[:500] if isinstance(article.get("snippet"), str) else "",
                    "source_url": url,
                }
            )

    logger.info("GDELT: fetched %d events (lookback=%dh, keywords=%d)", len(events), hours_back, len(list(keywords)))
    return events
