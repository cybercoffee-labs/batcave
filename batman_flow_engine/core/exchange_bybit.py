"""
Bybit Exchange Connector

DATA SOURCES:
    - Spot Ticker: https://api.bybit.com/v5/market/tickers?category=spot&symbol={PAIR}
    - Funding Rate: https://api.bybit.com/v5/market/funding/history?category=linear&symbol={PAIR}

PAIRS: BTCUSDT, ETHUSDT, SOLUSDT

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

BASE_URL = "https://api.bybit.com/v5"
TICKER_URL = f"{BASE_URL}/market/tickers"
FUNDING_RATE_URL = f"{BASE_URL}/market/funding/history"

# Supported pairs (Bybit format - no hyphen)
SUPPORTED_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


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
    """Normalize pair format to Bybit style (BTCUSDT)."""
    # Remove hyphens: BTC-USDT -> BTCUSDT
    return pair.upper().replace("-", "")


def fetch_bybit_price(pair: str) -> Dict[str, Any]:
    """
    Fetch current spot price from Bybit.

    Args:
        pair: Trading pair (e.g., "BTCUSDT", "ETHUSDT", "BTC-USDT")

    Returns:
        Dict with keys: price, bid, ask, volume_24h, ts, status

    Example:
        >>> data = fetch_bybit_price("BTCUSDT")
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

    data = _fetch_json(TICKER_URL, {"category": "spot", "symbol": normalized})

    if not data:
        return {
            "pair": pair,
            "status": "error",
            "error": "Failed to fetch data from Bybit API",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    if data.get("retCode") != 0:
        return {
            "pair": pair,
            "status": "error",
            "error": data.get("retMsg", "Unknown Bybit error"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    try:
        result = data.get("result", {})
        ticker_list = result.get("list", [])

        if not ticker_list:
            return {
                "pair": pair,
                "status": "error",
                "error": "No ticker data returned",
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        ticker = ticker_list[0]

        return {
            "pair": normalized,
            "price": float(ticker.get("lastPrice", 0)),
            "bid": float(ticker.get("bid1Price", 0)),
            "ask": float(ticker.get("ask1Price", 0)),
            "volume_24h": float(ticker.get("volume24h", 0)),
            "turnover_24h": float(ticker.get("turnover24h", 0)),
            "high_24h": float(ticker.get("highPrice24h", 0)),
            "low_24h": float(ticker.get("lowPrice24h", 0)),
            "price_change_pct_24h": float(ticker.get("price24hPcnt", 0)) * 100,
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "bybit",
            "status": "ok",
        }
    except (ValueError, TypeError, IndexError, KeyError) as e:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Failed to parse response: {e}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def fetch_bybit_funding_rate(pair: str) -> Dict[str, Any]:
    """
    Fetch current funding rate from Bybit perpetual futures.

    Args:
        pair: Trading pair (e.g., "BTCUSDT", "ETHUSDT")

    Returns:
        Dict with keys: funding_rate, next_funding_time, ts, status

    Example:
        >>> data = fetch_bybit_funding_rate("BTCUSDT")
        >>> print(data["funding_rate"])  # 0.0001
    """
    normalized = _normalize_pair(pair)

    if normalized not in SUPPORTED_PAIRS:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Unsupported pair: {pair}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    data = _fetch_json(FUNDING_RATE_URL, {"category": "linear", "symbol": normalized, "limit": "1"})

    if not data:
        return {
            "pair": pair,
            "status": "error",
            "error": "Failed to fetch funding rate from Bybit API",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    if data.get("retCode") != 0:
        return {
            "pair": pair,
            "status": "error",
            "error": data.get("retMsg", "Unknown Bybit error"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    try:
        result = data.get("result", {})
        rate_list = result.get("list", [])

        if not rate_list:
            return {
                "pair": pair,
                "status": "error",
                "error": "No funding rate data returned",
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        rate_data = rate_list[0]

        funding_rate = float(rate_data.get("fundingRate", 0))
        funding_time_ts = int(rate_data.get("fundingRateTimestamp", 0))

        # Convert timestamp to ISO format
        if funding_time_ts > 0:
            funding_time = datetime.fromtimestamp(funding_time_ts / 1000, tz=timezone.utc).isoformat()
        else:
            funding_time = None

        # Annualize: funding rate per 8h * 3 * 365 = APY
        annualized_pct = funding_rate * 3 * 365 * 100

        return {
            "pair": normalized,
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100, 6),
            "annualized_pct": round(annualized_pct, 2),
            "funding_time": funding_time,
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "bybit",
            "status": "ok",
        }
    except (ValueError, TypeError, IndexError, KeyError) as e:
        return {
            "pair": pair,
            "status": "error",
            "error": f"Failed to parse funding rate: {e}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def fetch_all_bybit_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetch prices for all supported Bybit pairs.

    Returns:
        Dict mapping pair names to price data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = fetch_bybit_price(pair)
    return results


def fetch_all_bybit_funding_rates() -> Dict[str, Dict[str, Any]]:
    """
    Fetch funding rates for all supported Bybit pairs.

    Returns:
        Dict mapping pair names to funding rate data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = fetch_bybit_funding_rate(pair)
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Bybit Exchange Connector Test")
    print("=" * 70)

    print("\nSpot Prices:")
    for pair in SUPPORTED_PAIRS:
        data = fetch_bybit_price(pair)
        if data.get("status") == "ok":
            print(f"  {pair}: ${data['price']:,.2f} | Bid: ${data['bid']:,.2f} | Ask: ${data['ask']:,.2f}")
        else:
            print(f"  {pair}: Error - {data.get('error')}")

    print("\nFunding Rates:")
    for pair in SUPPORTED_PAIRS:
        data = fetch_bybit_funding_rate(pair)
        if data.get("status") == "ok":
            print(f"  {pair}: {data['funding_rate_pct']:.4f}% (8h) | Annualized: {data['annualized_pct']:.2f}%")
        else:
            print(f"  {pair}: Error - {data.get('error')}")
