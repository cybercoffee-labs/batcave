"""
MEXC Spot Price Connector

PURPOSE: Fetch spot prices from MEXC exchange.

API: https://api.mexc.com/api/v3/ticker/price?symbol={PAIR}

PAIRS: BTCUSDT, ETHUSDT, SOLUSDT

NO API KEY NEEDED - public endpoints only.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Optional, Any

MEXC_PRICE_URL = "https://api.mexc.com/api/v3/ticker/price"
MEXC_TICKER_URL = "https://api.mexc.com/api/v3/ticker/bookTicker"
TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-flow-engine/1.0"

# Supported pairs
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def _fetch_json(url: str, params: Optional[Dict[str, str]] = None) -> Optional[Dict]:
    """Fetch JSON data from URL with retry logic."""
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)
    return None


def fetch_mexc_price(pair: str) -> Optional[Dict[str, Any]]:
    """
    Fetch price data for a trading pair from MEXC.

    Args:
        pair: Trading pair (e.g., "BTCUSDT")

    Returns:
        Dict with price data or None on error:
        {
            "price": float,
            "bid": float,
            "ask": float,
            "ts": str (ISO format)
        }
    """
    # Fetch last price
    price_data = _fetch_json(MEXC_PRICE_URL, {"symbol": pair})

    if not price_data or "price" not in price_data:
        return None

    # Fetch bid/ask from book ticker
    book_data = _fetch_json(MEXC_TICKER_URL, {"symbol": pair})

    try:
        last_price = float(price_data.get("price", 0))

        # Extract bid/ask
        bid = 0.0
        ask = 0.0

        if book_data:
            bid = float(book_data.get("bidPrice", 0) or 0)
            ask = float(book_data.get("askPrice", 0) or 0)

        # If no bid/ask, use price as both
        if bid == 0:
            bid = last_price
        if ask == 0:
            ask = last_price

        return {
            "price": last_price,
            "bid": bid,
            "ask": ask,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    except (ValueError, TypeError):
        return None


def fetch_mexc_ticker(pair: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full ticker data from MEXC (alias for fetch_mexc_price).

    Args:
        pair: Trading pair (e.g., "BTCUSDT")

    Returns:
        Dict with ticker data or None
    """
    return fetch_mexc_price(pair)


def fetch_all_mexc_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetch prices for all supported pairs.

    Returns:
        Dict mapping pair to price data
    """
    results = {}
    for pair in PAIRS:
        data = fetch_mexc_price(pair)
        if data:
            results[pair] = data
    return results


if __name__ == "__main__":
    print("=" * 50)
    print("MEXC Price Connector Test")
    print("=" * 50)

    for pair in PAIRS:
        result = fetch_mexc_price(pair)
        if result:
            print(f"{pair}: ${result['price']:,.2f} (bid: {result['bid']:,.2f}, ask: {result['ask']:,.2f})")
        else:
            print(f"{pair}: FAILED")
