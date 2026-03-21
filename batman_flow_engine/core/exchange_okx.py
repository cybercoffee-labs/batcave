"""
OKX Exchange Connector

DATA SOURCES:
    - Spot Ticker: https://www.okx.com/api/v5/market/ticker?instId={PAIR}
    - Funding Rate: https://www.okx.com/api/v5/public/funding-rate?instId={PAIR}

PAIRS: BTC-USDT, ETH-USDT, SOL-USDT

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

BASE_URL = "https://www.okx.com/api/v5"
TICKER_URL = f"{BASE_URL}/market/ticker"
FUNDING_RATE_URL = f"{BASE_URL}/public/funding-rate"

# Supported pairs (OKX format uses hyphens)
SUPPORTED_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]


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


def _normalize_pair(pair: str) -> str:
    """Normalize pair format to OKX style (BTC-USDT)."""
    # Convert BTCUSDT -> BTC-USDT
    pair_upper = pair.upper()
    if "-" in pair_upper:
        return pair_upper
    # Handle common formats
    for suffix in ["USDT", "USD", "USDC"]:
        if pair_upper.endswith(suffix):
            base = pair_upper[: -len(suffix)]
            return f"{base}-{suffix}"
    return pair_upper


def fetch_okx_price(pair: str) -> Dict[str, Any]:
    """
    Fetch current spot price from OKX.

    Args:
        pair: Trading pair (e.g., "BTC-USDT", "ETH-USDT", "BTCUSDT")

    Returns:
        Dict with keys: price, bid, ask, volume_24h, ts, status

    Example:
        >>> data = fetch_okx_price("BTC-USDT")
        >>> print(data["price"])  # 84500.00
    """
    normalized = _normalize_pair(pair)

    if normalized not in SUPPORTED_PAIRS:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Unsupported pair: {pair}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    data = _fetch_json(TICKER_URL, {"instId": normalized})

    if not data:
        return {
            "pair": pair,
            "status": "error",
            "error": "Failed to fetch data from OKX API",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    if data.get("code") != "0":
        return {
            "pair": pair,
            "status": "error",
            "error": data.get("msg", "Unknown OKX error"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    try:
        ticker = data.get("data", [{}])[0]

        return {
            "pair": normalized,
            "price": float(ticker.get("last", 0)),
            "bid": float(ticker.get("bidPx", 0)),
            "ask": float(ticker.get("askPx", 0)),
            "volume_24h": float(ticker.get("vol24h", 0)),
            "volume_24h_usd": float(ticker.get("volCcy24h", 0)),
            "high_24h": float(ticker.get("high24h", 0)),
            "low_24h": float(ticker.get("low24h", 0)),
            "open_24h": float(ticker.get("open24h", 0)),
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "okx",
            "status": "ok",
        }
    except (ValueError, TypeError, IndexError, KeyError) as e:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Failed to parse response: {e}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def fetch_okx_funding_rate(pair: str) -> Dict[str, Any]:
    """
    Fetch current funding rate from OKX perpetual swaps.

    Args:
        pair: Trading pair (e.g., "BTC-USDT", "ETH-USDT")
              Note: For perpetuals, OKX uses format like "BTC-USDT-SWAP"

    Returns:
        Dict with keys: funding_rate, next_funding_time, ts, status

    Example:
        >>> data = fetch_okx_funding_rate("BTC-USDT")
        >>> print(data["funding_rate"])  # 0.0001
    """
    normalized = _normalize_pair(pair)

    # OKX perpetual swaps use "-SWAP" suffix
    swap_inst = f"{normalized}-SWAP"

    data = _fetch_json(FUNDING_RATE_URL, {"instId": swap_inst})

    if not data:
        return {
            "pair": pair,
            "status": "error",
            "error": "Failed to fetch funding rate from OKX API",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    if data.get("code") != "0":
        return {
            "pair": pair,
            "status": "error",
            "error": data.get("msg", "Unknown OKX error"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    try:
        rate_data = data.get("data", [{}])[0]

        funding_rate = float(rate_data.get("fundingRate", 0))
        next_funding_ts = int(rate_data.get("nextFundingTime", 0))

        # Convert timestamp to ISO format
        if next_funding_ts > 0:
            next_funding_time = datetime.fromtimestamp(next_funding_ts / 1000, tz=timezone.utc).isoformat()
        else:
            next_funding_time = None

        # Annualize: funding rate per 8h * 3 * 365 = APY
        annualized_pct = funding_rate * 3 * 365 * 100

        return {
            "pair": normalized,
            "inst_id": swap_inst,
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100, 6),
            "annualized_pct": round(annualized_pct, 2),
            "next_funding_time": next_funding_time,
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "okx",
            "status": "ok",
        }
    except (ValueError, TypeError, IndexError, KeyError) as e:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Failed to parse funding rate: {e}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def fetch_all_okx_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetch prices for all supported OKX pairs.

    Returns:
        Dict mapping pair names to price data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = fetch_okx_price(pair)
    return results


def fetch_all_okx_funding_rates() -> Dict[str, Dict[str, Any]]:
    """
    Fetch funding rates for all supported OKX pairs.

    Returns:
        Dict mapping pair names to funding rate data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = fetch_okx_funding_rate(pair)
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("OKX Exchange Connector Test")
    print("=" * 70)

    print("\nSpot Prices:")
    for pair in SUPPORTED_PAIRS:
        data = fetch_okx_price(pair)
        if data.get("status") == "ok":
            print(f"  {pair}: ${data['price']:,.2f} | Bid: ${data['bid']:,.2f} | Ask: ${data['ask']:,.2f}")
        else:
            print(f"  {pair}: Error - {data.get('error')}")

    print("\nFunding Rates:")
    for pair in SUPPORTED_PAIRS:
        data = fetch_okx_funding_rate(pair)
        if data.get("status") == "ok":
            print(f"  {pair}: {data['funding_rate_pct']:.4f}% (8h) | Annualized: {data['annualized_pct']:.2f}%")
        else:
            print(f"  {pair}: Error - {data.get('error')}")
