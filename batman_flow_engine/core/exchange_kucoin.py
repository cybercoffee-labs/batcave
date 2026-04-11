"""
KuCoin Spot Price Connector

PURPOSE: Fetch spot prices from KuCoin exchange.

API: https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={PAIR}

PAIRS: BTC-USDT, ETH-USDT, SOL-USDT

NO API KEY NEEDED - public endpoints only.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Optional, Any

KUCOIN_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1"
TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-flow-engine/1.0"

# Supported pairs
PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]


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


def fetch_kucoin_price(pair: str) -> Optional[Dict[str, Any]]:
    """
    Fetch price data for a trading pair from KuCoin.

    Args:
        pair: Trading pair (e.g., "BTC-USDT")

    Returns:
        Dict with price data or None on error:
        {
            "price": float,
            "bid": float,
            "ask": float,
            "sequence": str,
            "ts": str (ISO format)
        }
    """
    data = _fetch_json(KUCOIN_URL, {"symbol": pair})

    if not data:
        return None

    # KuCoin response format:
    # {"code": "200000", "data": {"sequence": "...", "price": "...", "size": "...", "bestBid": "...", "bestAsk": "..."}}
    if data.get("code") != "200000":
        return None

    ticker = data.get("data", {})
    if not ticker:
        return None

    try:
        bid = float(ticker.get("bestBid", 0) or 0)
        ask = float(ticker.get("bestAsk", 0) or 0)
        last_price = float(ticker.get("price", 0) or 0)

        # If price is 0 but bid/ask available, use mid price
        if last_price == 0 and bid > 0 and ask > 0:
            last_price = (bid + ask) / 2

        return {
            "price": last_price,
            "bid": bid,
            "ask": ask,
            "sequence": ticker.get("sequence", ""),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    except (ValueError, TypeError):
        return None


def fetch_kucoin_ticker(pair: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full ticker data from KuCoin (alias for fetch_kucoin_price).

    Args:
        pair: Trading pair (e.g., "BTC-USDT")

    Returns:
        Dict with ticker data or None
    """
    return fetch_kucoin_price(pair)


def fetch_all_kucoin_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetch prices for all supported pairs.

    Returns:
        Dict mapping pair to price data
    """
    results = {}
    for pair in PAIRS:
        data = fetch_kucoin_price(pair)
        if data:
            results[pair] = data
    return results


if __name__ == "__main__":
    print("=" * 50)
    print("KuCoin Price Connector Test")
    print("=" * 50)

    for pair in PAIRS:
        result = fetch_kucoin_price(pair)
        if result:
            print(f"{pair}: ${result['price']:,.2f} (bid: {result['bid']:,.2f}, ask: {result['ask']:,.2f})")
        else:
            print(f"{pair}: FAILED")
