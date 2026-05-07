"""
Bitget Exchange Connector

DATA SOURCES:
    - Spot Ticker: ccxt bitget.fetch_ticker({PAIR})
    - Order Book: ccxt bitget.fetch_order_book({PAIR})
    - Funding Rate: ccxt bitget.fetch_funding_rate({PERP_PAIR})
    - P2P Price: Not exposed via ccxt for Bitget

PAIRS: BTC/USDT, ETH/USDT, SOL/USDT

Uses BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE from .env.
Public endpoints work without keys, but credentials are loaded when present.
"""

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ccxt

TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-flow-engine/1.0"

BASE_DIR = Path(__file__).resolve().parent.parent

# Supported pairs (Bitget unified CCXT format)
SUPPORTED_PAIRS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "DOT/USDT",
    "MATIC/USDT",
    "UNI/USDT",
    "ATOM/USDT",
    "NEAR/USDT",
    "APT/USDT",
    "ARB/USDT",
    "OP/USDT",
    "FIL/USDT",
    "LTC/USDT",
    "BCH/USDT",
    "XLM/USDT",
]

_EXCHANGE_CACHE: dict[str, ccxt.Exchange] = {}


def _load_env() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env()

API_KEY = os.environ.get("BITGET_API_KEY", "")
API_SECRET = os.environ.get("BITGET_API_SECRET", "")
API_PASSPHRASE = os.environ.get("BITGET_PASSPHRASE", "")


def _get_exchange(default_type: str = "spot") -> ccxt.Exchange:
    """Create or return a cached Bitget ccxt client."""
    exchange = _EXCHANGE_CACHE.get(default_type)
    if exchange is not None:
        return exchange

    config: dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": TIMEOUT * 1000,
        "headers": {"User-Agent": USER_AGENT},
        "options": {"defaultType": default_type},
    }

    if API_KEY and API_SECRET and API_PASSPHRASE:
        config.update(
            {
                "apiKey": API_KEY,
                "secret": API_SECRET,
                "password": API_PASSPHRASE,
            }
        )

    exchange = ccxt.bitget(config)
    _EXCHANGE_CACHE[default_type] = exchange
    return exchange


def _normalize_pair(pair: str) -> str:
    """Normalize pair format to Bitget ccxt style (BTC/USDT)."""
    cleaned = pair.upper().replace("-", "/")
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0]
    if "/" in cleaned:
        base, quote = cleaned.split("/", 1)
        return f"{base}/{quote}"
    if cleaned.endswith("USDT") and len(cleaned) > 4:
        return f"{cleaned[:-4]}/USDT"
    return cleaned


def _normalize_swap_pair(pair: str) -> str:
    """Normalize pair format to Bitget linear perpetual style (BTC/USDT:USDT)."""
    normalized = _normalize_pair(pair)
    if ":" in pair:
        return pair.upper()
    if "/" in normalized:
        base, quote = normalized.split("/", 1)
        return f"{base}/{quote}:{quote}"
    return normalized


def _call_exchange(default_type: str, method_name: str, *args: Any, **kwargs: Any) -> tuple[Any | None, str | None]:
    """Call a ccxt Bitget method with retry logic."""
    last_error = None

    for attempt in range(RETRIES):
        try:
            exchange = _get_exchange(default_type)
            method = getattr(exchange, method_name)
            return method(*args, **kwargs), None
        except Exception as exc:
            last_error = str(exc)
            if attempt == RETRIES - 1:
                return None, last_error
            time.sleep(2**attempt)

    return None, last_error


def get_spot_price(symbol: str) -> dict[str, Any]:
    """
    Fetch current spot price from Bitget.

    Args:
        symbol: Trading pair (e.g., "BTC/USDT", "ETHUSDT", "BTC-USDT")

    Returns:
        Dict with keys: price, bid, ask, volume_24h, ts, status
    """
    normalized = _normalize_pair(symbol)

    if normalized not in SUPPORTED_PAIRS:
        return {
            "pair": symbol,
            "status": "error",
            "error": f"Unsupported pair: {symbol}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(UTC).isoformat(),
        }

    data, error = _call_exchange("spot", "fetch_ticker", normalized)

    if not data:
        return {
            "pair": symbol,
            "status": "error",
            "error": error or "Failed to fetch data from Bitget API",
            "ts": datetime.now(UTC).isoformat(),
        }

    try:
        return {
            "pair": normalized,
            "price": float(data.get("last") or 0),
            "bid": float(data.get("bid") or 0),
            "ask": float(data.get("ask") or 0),
            "volume_24h": float(data.get("baseVolume") or 0),
            "turnover_24h": float(data.get("quoteVolume") or 0),
            "high_24h": float(data.get("high") or 0),
            "low_24h": float(data.get("low") or 0),
            "price_change_pct_24h": float(data.get("percentage") or 0),
            "ts": datetime.now(UTC).isoformat(),
            "exchange": "bitget",
            "status": "ok",
        }
    except (ValueError, TypeError, KeyError) as exc:
        return {
            "pair": symbol,
            "status": "error",
            "error": f"Failed to parse response: {exc}",
            "ts": datetime.now(UTC).isoformat(),
        }


def get_orderbook(symbol: str) -> dict[str, Any]:
    """
    Fetch spot order book from Bitget.

    Args:
        symbol: Trading pair (e.g., "BTC/USDT")

    Returns:
        Dict with keys: bids, asks, best_bid, best_ask, spread, ts, status
    """
    normalized = _normalize_pair(symbol)

    if normalized not in SUPPORTED_PAIRS:
        return {
            "pair": symbol,
            "status": "error",
            "error": f"Unsupported pair: {symbol}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(UTC).isoformat(),
        }

    data, error = _call_exchange("spot", "fetch_order_book", normalized)

    if not data:
        return {
            "pair": symbol,
            "status": "error",
            "error": error or "Failed to fetch order book from Bitget API",
            "ts": datetime.now(UTC).isoformat(),
        }

    try:
        bids = data.get("bids", [])
        asks = data.get("asks", [])

        if not bids or not asks:
            return {
                "pair": symbol,
                "status": "error",
                "error": "No order book data returned",
                "ts": datetime.now(UTC).isoformat(),
            }

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])

        return {
            "pair": normalized,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": best_ask - best_bid,
            "ts": datetime.now(UTC).isoformat(),
            "exchange": "bitget",
            "status": "ok",
        }
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        return {
            "pair": symbol,
            "status": "error",
            "error": f"Failed to parse order book: {exc}",
            "ts": datetime.now(UTC).isoformat(),
        }


def get_funding_rate(symbol: str) -> dict[str, Any]:
    """
    Fetch current funding rate from Bitget perpetual futures.

    Args:
        symbol: Trading pair (e.g., "BTC/USDT", "BTCUSDT")

    Returns:
        Dict with keys: funding_rate, next_funding_time, ts, status
    """
    normalized = _normalize_pair(symbol)
    swap_symbol = _normalize_swap_pair(symbol)

    if normalized not in SUPPORTED_PAIRS:
        return {
            "pair": symbol,
            "status": "error",
            "error": f"Unsupported pair: {symbol}. Supported: {SUPPORTED_PAIRS}",
            "ts": datetime.now(UTC).isoformat(),
        }

    data, error = _call_exchange("swap", "fetch_funding_rate", swap_symbol)

    if not data:
        return {
            "pair": symbol,
            "status": "error",
            "error": error or "Failed to fetch funding rate from Bitget API",
            "ts": datetime.now(UTC).isoformat(),
        }

    try:
        funding_rate = float(data.get("fundingRate") or 0)

        funding_time = None
        funding_time_ms = data.get("fundingTimestamp") or data.get("nextFundingTimestamp")
        if funding_time_ms:
            funding_time = datetime.fromtimestamp(int(funding_time_ms) / 1000, tz=UTC).isoformat()

        annualized_pct = funding_rate * 3 * 365 * 100

        return {
            "pair": normalized,
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100, 6),
            "annualized_pct": round(annualized_pct, 2),
            "funding_time": funding_time,
            "ts": datetime.now(UTC).isoformat(),
            "exchange": "bitget",
            "status": "ok",
        }
    except (ValueError, TypeError, KeyError) as exc:
        return {
            "pair": symbol,
            "status": "error",
            "error": f"Failed to parse funding rate: {exc}",
            "ts": datetime.now(UTC).isoformat(),
        }


def get_p2p_price(fiat: str, side: str) -> dict[str, Any]:
    """
    Fetch Bitget P2P price if available.

    Bitget P2P is not exposed through ccxt, so this returns a structured
    unavailable response instead of silently failing.
    """
    return {
        "fiat": fiat.upper(),
        "side": side.lower(),
        "status": "error",
        "error": "Bitget P2P is not available via ccxt",
        "ts": datetime.now(UTC).isoformat(),
        "exchange": "bitget",
    }


def fetch_all_bitget_prices() -> dict[str, dict[str, Any]]:
    """
    Fetch prices for all supported Bitget pairs.

    Returns:
        Dict mapping pair names to price data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = get_spot_price(pair)
    return results


def fetch_all_bitget_funding_rates() -> dict[str, dict[str, Any]]:
    """
    Fetch funding rates for all supported Bitget pairs.

    Returns:
        Dict mapping pair names to funding rate data
    """
    results = {}
    for pair in SUPPORTED_PAIRS:
        results[pair] = get_funding_rate(pair)
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Bitget Exchange Connector Test")
    print("=" * 70)

    print("\nSpot Prices:")
    for pair in SUPPORTED_PAIRS[:3]:
        data = get_spot_price(pair)
        if data.get("status") == "ok":
            print(f"  {pair}: ${data['price']:,.2f} | Bid: ${data['bid']:,.2f} | Ask: ${data['ask']:,.2f}")
        else:
            print(f"  {pair}: Error - {data.get('error')}")

    print("\nFunding Rates:")
    for pair in SUPPORTED_PAIRS[:3]:
        data = get_funding_rate(pair)
        if data.get("status") == "ok":
            print(f"  {pair}: {data['funding_rate_pct']:.4f}% (8h) | Annualized: {data['annualized_pct']:.2f}%")
        else:
            print(f"  {pair}: Error - {data.get('error')}")
