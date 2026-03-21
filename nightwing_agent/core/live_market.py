"""
Live market ingestion helpers for Nightwing.

Role:
- Provide optional real exchange data for the existing market-data layer.
- Keep the integration read-only, timeout-bounded, and easy to audit.

Behavior:
- Uses Binance public endpoints plus a public USD/MXN exchange-rate endpoint.
- Retries transient failures a small number of times.
- Raises clear errors upward so the caller can fall back to simulated data.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BINANCE_SPOT_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_RETRIES = 2


def _request_json(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> Any:
    """Fetch JSON with basic timeout and retry protection."""
    payload = None
    headers = {"User-Agent": "nightwing-agent/1.0"}
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.25 * (attempt + 1))
    if last_error is None:
        raise RuntimeError("live_market_request_failed")
    raise RuntimeError(str(last_error))


def _to_float(value: Any) -> float | None:
    """Convert a numeric-looking value to float, returning None on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_p2p_trade_offers(
    symbol: str,
    fiat: str,
    trade_type: str,
    rows: int,
    timeout: float,
    retries: int,
) -> list[dict[str, Any]]:
    """Fetch one side of the Binance P2P book and normalize the top rows."""
    payload = {
        "asset": symbol,
        "fiat": fiat,
        "merchantCheck": False,
        "page": 1,
        "payTypes": [],
        "publisherType": None,
        "rows": rows,
        "tradeType": trade_type,
    }
    data = _request_json(
        BINANCE_P2P_URL,
        method="POST",
        data=payload,
        timeout=timeout,
        retries=retries,
    )
    offers = []
    for item in data.get("data", []):
        adv = item.get("adv") or {}
        advertiser = item.get("advertiser") or {}
        price = _to_float(adv.get("price"))
        max_single_trans_amount = _to_float(adv.get("dynamicMaxSingleTransAmount"))
        if price is None:
            continue
        offers.append(
            {
                "price": price,
                "min_single_trans_amount": adv.get("minSingleTransAmount"),
                "max_single_trans_amount": adv.get("dynamicMaxSingleTransAmount"),
                "max_single_trans_amount_value": max_single_trans_amount or 0.0,
                "nick_name": advertiser.get("nickName"),
                "trade_type": trade_type,
            }
        )
    return offers


def fetch_binance_spot_prices(
    timeout: float = DEFAULT_TIMEOUT_SECONDS, retries: int = DEFAULT_RETRIES
) -> dict[str, Any]:
    """Fetch Binance spot prices for the symbols Nightwing already monitors."""
    data = _request_json(BINANCE_SPOT_URL, timeout=timeout, retries=retries)
    wanted = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
    prices = {}
    for item in data:
        symbol = item.get("symbol")
        if symbol in wanted:
            try:
                prices[symbol] = float(item["price"])
            except (KeyError, TypeError, ValueError):
                continue
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "binance_spot",
        "prices": prices,
    }


def fetch_binance_p2p_offers(
    fiat: str = "MXN",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Fetch a compact snapshot of Binance P2P buy offers for one fiat market."""
    offers = _fetch_p2p_trade_offers("USDT", fiat, "BUY", 5, timeout, retries)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "binance_p2p",
        "fiat": fiat,
        "offers": offers,
    }


def fetch_p2p_depth(
    symbol: str = "USDT",
    fiat: str = "MXN",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Fetch top-of-book P2P depth and derive compact supervision metrics."""
    buy_offers = _fetch_p2p_trade_offers(symbol, fiat, "BUY", 10, timeout, retries)
    sell_offers = _fetch_p2p_trade_offers(symbol, fiat, "SELL", 10, timeout, retries)

    best_buy = max((offer["price"] for offer in buy_offers), default=None)
    best_sell = min((offer["price"] for offer in sell_offers), default=None)

    all_offers = buy_offers + sell_offers
    total_weight = sum(offer["max_single_trans_amount_value"] for offer in all_offers)
    if total_weight > 0:
        weighted_average = (
            sum(offer["price"] * offer["max_single_trans_amount_value"] for offer in all_offers) / total_weight
        )
    else:
        weighted_average = None

    liquidity_estimate = sum(offer["max_single_trans_amount_value"] for offer in all_offers)
    merchant_names = {offer["nick_name"] for offer in all_offers if offer.get("nick_name")}

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "binance_p2p_depth",
        "symbol": symbol,
        "fiat": fiat,
        "buy_offers": buy_offers,
        "sell_offers": sell_offers,
        "best_buy": best_buy,
        "best_sell": best_sell,
        "weighted_average": weighted_average,
        "merchant_count": len(merchant_names),
        "liquidity_estimate": liquidity_estimate,
    }


def fetch_exchange_rate(
    base: str = "USD",
    quote: str = "MXN",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Fetch a public FX rate used to contextualize live P2P prices."""
    if base != "USD":
        raise RuntimeError("only_usd_base_supported")
    data = _request_json(EXCHANGE_RATE_URL, timeout=timeout, retries=retries)
    rates = data.get("rates") or {}
    if quote not in rates:
        raise RuntimeError(f"missing_rate_{quote}")
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "exchange_rate_api",
        "base": base,
        "quote": quote,
        "rate": float(rates[quote]),
    }
