"""
Bitso Exchange Connector (Mexican Exchange)

DATA SOURCES:
    - Ticker: https://api.bitso.com/v3/ticker/?book={PAIR}
    - Order Book: https://api.bitso.com/v3/order_book/?book={PAIR}&aggregate=true

PAIRS: btc_mxn, eth_mxn, usdt_mxn

No API key required for public endpoints.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, Dict, Any

TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-flow-engine/1.0"

BASE_URL = "https://api.bitso.com/v3"
TICKER_URL = f"{BASE_URL}/ticker/"
ORDER_BOOK_URL = f"{BASE_URL}/order_book/"

# Supported pairs
SUPPORTED_PAIRS = ["btc_mxn", "eth_mxn", "usdt_mxn"]


def _fetch_json(url: str, params: Optional[Dict[str, str]] = None) -> Optional[Dict]:
    """
    Fetch JSON data from URL with retry logic.

    Args:
        url: Base URL to fetch
        params: Optional query parameters

    Returns:
        Parsed JSON dict or None on failure
    """
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError:
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)
        except (json.JSONDecodeError, Exception):
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)
    return None


def fetch_bitso_price(pair: str) -> Dict[str, Any]:
    """
    Fetch current ticker price from Bitso.

    Args:
        pair: Trading pair (e.g., "btc_mxn", "eth_mxn", "usdt_mxn")

    Returns:
        Dict with keys: price, bid, ask, volume_24h, ts, status

    Example:
        >>> data = fetch_bitso_price("btc_mxn")
        >>> print(data["price"])  # 1450000.00
    """
    pair_lower = pair.lower()

    if pair_lower not in SUPPORTED_PAIRS:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Unsupported pair: {pair}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    data = _fetch_json(TICKER_URL, {"book": pair_lower})

    if not data:
        return {
            "pair": pair,
            "status": "error",
            "error": "Failed to fetch data from Bitso API",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    if not data.get("success"):
        return {
            "pair": pair,
            "status": "error",
            "error": data.get("error", {}).get("message", "Unknown error"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    payload = data.get("payload", {})

    try:
        return {
            "pair": pair_lower,
            "price": float(payload.get("last", 0)),
            "bid": float(payload.get("bid", 0)),
            "ask": float(payload.get("ask", 0)),
            "volume_24h": float(payload.get("volume", 0)),
            "high_24h": float(payload.get("high", 0)),
            "low_24h": float(payload.get("low", 0)),
            "vwap": float(payload.get("vwap", 0)),
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "bitso",
            "status": "ok",
        }
    except (ValueError, TypeError) as e:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Failed to parse response: {e}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def fetch_bitso_order_book(pair: str, limit: int = 20) -> Dict[str, Any]:
    """
    Fetch order book from Bitso.

    Args:
        pair: Trading pair (e.g., "btc_mxn", "eth_mxn", "usdt_mxn")
        limit: Number of orders per side (max 50)

    Returns:
        Dict with keys: bids, asks, ts, status
        Each bid/ask is: {"price": float, "amount": float}

    Example:
        >>> data = fetch_bitso_order_book("usdt_mxn", limit=10)
        >>> print(data["bids"][0])  # {"price": 17.50, "amount": 1000.0}
    """
    pair_lower = pair.lower()

    if pair_lower not in SUPPORTED_PAIRS:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Unsupported pair: {pair}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    # Bitso API doesn't have a limit param, but we can aggregate
    data = _fetch_json(ORDER_BOOK_URL, {"book": pair_lower, "aggregate": "true"})

    if not data:
        return {
            "pair": pair,
            "status": "error",
            "error": "Failed to fetch order book from Bitso API",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    if not data.get("success"):
        return {
            "pair": pair,
            "status": "error",
            "error": data.get("error", {}).get("message", "Unknown error"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    payload = data.get("payload", {})

    try:
        raw_bids = payload.get("bids", [])[:limit]
        raw_asks = payload.get("asks", [])[:limit]

        bids = [{"price": float(b.get("price", 0)), "amount": float(b.get("amount", 0))} for b in raw_bids]
        asks = [{"price": float(a.get("price", 0)), "amount": float(a.get("amount", 0))} for a in raw_asks]

        # Calculate spread
        best_bid = bids[0]["price"] if bids else 0
        best_ask = asks[0]["price"] if asks else 0
        spread_pct = ((best_ask - best_bid) / best_bid * 100) if best_bid > 0 else 0

        return {
            "pair": pair_lower,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": round(spread_pct, 4),
            "bid_depth": sum(b["amount"] for b in bids),
            "ask_depth": sum(a["amount"] for a in asks),
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "bitso",
            "status": "ok",
        }
    except (ValueError, TypeError, IndexError) as e:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Failed to parse order book: {e}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def fetch_all_bitso_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetch prices for all supported Bitso pairs.

    Returns:
        Dict mapping pair names to price data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = fetch_bitso_price(pair)
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Bitso Exchange Connector Test")
    print("=" * 70)

    for pair in SUPPORTED_PAIRS:
        data = fetch_bitso_price(pair)
        if data.get("status") == "ok":
            print(f"{pair}: ${data['price']:,.2f} MXN | Bid: ${data['bid']:,.2f} | Ask: ${data['ask']:,.2f}")
        else:
            print(f"{pair}: Error - {data.get('error')}")

    print("\nOrder Book (usdt_mxn, top 5):")
    ob = fetch_bitso_order_book("usdt_mxn", limit=5)
    if ob.get("status") == "ok":
        print(f"  Best Bid: ${ob['best_bid']:.4f} | Best Ask: ${ob['best_ask']:.4f} | Spread: {ob['spread_pct']:.4f}%")
