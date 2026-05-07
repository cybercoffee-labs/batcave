"""AQUAMAN — Market depth and liquidity verification."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import ccxt


logger = logging.getLogger("batman.aquaman")

MIN_DEPTH_USD = 500.0
MAX_SLIPPAGE_PCT = 0.5
DEFAULT_TRADE_USD = 100.0
SUPPORTED_EXCHANGES = ("binance", "bybit", "bitget")
FIAT_CODES = {"MXN", "ARS", "COP", "VES", "BRL", "CLP", "PEN", "USD", "EUR"}
STABLECOINS = {"USDT", "USDC", "DAI"}

# Cache TTL for liquidity snapshots. Success-only — error paths are never cached.
CACHE_TTL_SECONDS = 60.0


class Aquaman:
    """Market Depth & Liquidity Analyzer."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.exchanges = {
            "binance": ccxt.binance({"enableRateLimit": True}),
            "bybit": ccxt.bybit({"enableRateLimit": True}),
            "bitget": ccxt.bitget({"enableRateLimit": True}),
        }
        # Cache entry: (monotonic_timestamp, result_dict). Only success results are stored.
        self._liquidity_cache: dict[tuple[str, str, float], tuple[float, dict[str, Any]]] = {}
        self._cache_lock = threading.Lock()

    def check_liquidity(self, exchange_id: str, symbol: str, amount_usd: float = DEFAULT_TRADE_USD) -> dict[str, Any]:
        """
        Check whether a market has enough real depth for a small trade.

        Returns:
            {
                'is_liquid': bool,
                'depth_usd': float,
                'slippage_pct': float,
                'bid_depth_usd': float,
                'ask_depth_usd': float,
                'spread_pct': float,
                'status': 'ok' | 'error',
            }
        """
        exchange = self.exchanges.get(exchange_id)
        if exchange is None:
            return self._error_result(f"unsupported_exchange:{exchange_id}")
        cache_key = (exchange_id, symbol, float(amount_usd))
        now = time.monotonic()

        with self._cache_lock:
            cached = self._liquidity_cache.get(cache_key)
            if cached is not None:
                ts, payload = cached
                if now - ts <= CACHE_TTL_SECONDS:
                    return dict(payload)
                # Expired — drop and fall through to a fresh fetch.
                del self._liquidity_cache[cache_key]

        try:
            order_book = exchange.fetch_order_book(symbol, limit=50)
            bids = order_book.get("bids") or []
            asks = order_book.get("asks") or []
            if not bids or not asks:
                return self._error_result("empty_order_book")

            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid_price = (best_bid + best_ask) / 2
            band_low = mid_price * 0.99
            band_high = mid_price * 1.01

            bid_depth_usd = self._depth_within_band(bids, minimum_price=band_low)
            ask_depth_usd = self._depth_within_band(asks, maximum_price=band_high)
            spread_pct = ((best_ask - best_bid) / mid_price) * 100 if mid_price else 0.0
            slippage_pct = self._estimate_slippage(asks, amount_usd)
            depth_usd = min(bid_depth_usd, ask_depth_usd)
            is_liquid = depth_usd >= MIN_DEPTH_USD and slippage_pct <= MAX_SLIPPAGE_PCT

            result = {
                "is_liquid": is_liquid,
                "depth_usd": round(depth_usd, 2),
                "slippage_pct": round(slippage_pct, 4),
                "bid_depth_usd": round(bid_depth_usd, 2),
                "ask_depth_usd": round(ask_depth_usd, 2),
                "spread_pct": round(spread_pct, 4),
                "status": "ok",
                "exchange_id": exchange_id,
                "symbol": symbol,
            }
            with self._cache_lock:
                self._liquidity_cache[cache_key] = (time.monotonic(), dict(result))
            return result
        except Exception as exc:
            logger.warning("AQUAMAN liquidity check failed for %s %s: %s", exchange_id, symbol, exc)
            # Do NOT cache error results — a one-off exchange hiccup must not
            # poison the cache with a permanent "error" verdict.
            return self._error_result(str(exc), exchange_id=exchange_id, symbol=symbol)

    def verify_opportunity(self, opportunity: dict[str, Any]) -> dict[str, Any] | None:
        """
        Verify a Batman opportunity has real liquidity.

        Anti-Joker Rule:
        - Min $500 USD depth within 1% of price
        - Max 0.5% slippage for $100 USD trade
        """
        exchange_id = self.infer_exchange_id(opportunity)
        symbol = self._infer_symbol(opportunity)
        if not exchange_id or not symbol:
            return None

        result = self.check_liquidity(exchange_id, symbol, amount_usd=DEFAULT_TRADE_USD)
        if result.get("status") != "ok":
            return None
        if not result.get("is_liquid"):
            return None

        enriched = {
            **result,
            "exchange_id": exchange_id,
            "symbol": symbol,
            "opp_id": opportunity.get("opp_id"),
        }
        return enriched

    def get_market_summary(self, symbols: list[str] | None = None) -> dict[str, Any]:
        """
        Return a real depth snapshot for core markets.

        Used by Clark Kent for Stablecoin Watch posts.
        """
        if symbols is None:
            symbols = ["USDT/MXN", "BTC/USDT", "ETH/USDT", "SOL/USDT"]

        summaries: list[dict[str, Any]] = []
        for symbol in symbols:
            for exchange_id in SUPPORTED_EXCHANGES:
                result = self.check_liquidity(exchange_id, symbol)
                if result.get("status") == "ok":
                    summaries.append(result)
                    break
            else:
                summaries.append({"symbol": symbol, "status": "error", "is_liquid": False})

        best = None
        successful = [item for item in summaries if item.get("status") == "ok"]
        if successful:
            best = max(successful, key=lambda item: item.get("depth_usd", 0.0))

        return {
            "markets": summaries,
            "best_market": best,
        }

    def infer_exchange_id(self, opportunity: dict[str, Any]) -> str | None:
        """Resolve the best supported exchange from opportunity metadata.

        Returns None when the opportunity's metadata doesn't name a supported
        venue. Historically this silently returned "binance", which meant
        Bitso / Kucoin / MEXC / OKX opportunities got a Binance depth verdict
        they never asked for. Callers must now handle None explicitly.
        """
        candidates = [
            opportunity.get("exchange"),
            opportunity.get("venue"),
            opportunity.get("buy_exchange"),
            opportunity.get("sell_exchange"),
            opportunity.get("buy_platform"),
            opportunity.get("sell_platform"),
            opportunity.get("scanner_id"),
        ]
        joined = " ".join(str(value or "").lower() for value in candidates)
        for exchange_id in SUPPORTED_EXCHANGES:
            if exchange_id in joined:
                return exchange_id
        # No silent fallback. If the opportunity doesn't carry a supported
        # venue, we refuse to guess — the caller must treat this as unverified.
        return None

    def _infer_symbol(self, opportunity: dict[str, Any]) -> str | None:
        """Map Batman opportunities to a tradeable spot symbol when possible."""
        market = str(opportunity.get("market") or "").upper().strip()
        asset = str(opportunity.get("asset") or "").upper().strip()

        if "/" in market:
            base, quote = market.split("/", 1)
            if quote and quote not in FIAT_CODES:
                return f"{base}/{quote}"
            return None

        if asset and asset not in STABLECOINS and asset not in FIAT_CODES:
            return f"{asset}/USDT"
        return None

    def _depth_within_band(
        self,
        side: list[list[float]],
        minimum_price: float | None = None,
        maximum_price: float | None = None,
    ) -> float:
        depth_usd = 0.0
        for price, amount in side:
            price = float(price)
            amount = float(amount)
            if minimum_price is not None and price < minimum_price:
                continue
            if maximum_price is not None and price > maximum_price:
                continue
            depth_usd += price * amount
        return depth_usd

    def _estimate_slippage(self, asks: list[list[float]], amount_usd: float) -> float:
        if not asks:
            return 100.0

        target_usd = float(amount_usd)
        best_ask = float(asks[0][0])
        remaining_usd = target_usd
        acquired = 0.0
        spent = 0.0

        for price, amount in asks:
            price = float(price)
            amount = float(amount)
            level_value = price * amount
            take_value = min(level_value, remaining_usd)
            if take_value <= 0:
                break
            spent += take_value
            acquired += take_value / price
            remaining_usd -= take_value
            if remaining_usd <= 0:
                break

        if remaining_usd > 0 or acquired <= 0:
            return 100.0

        average_fill = spent / acquired
        return ((average_fill - best_ask) / best_ask) * 100 if best_ask else 100.0

    def _error_result(self, reason: str, exchange_id: str | None = None, symbol: str | None = None) -> dict[str, Any]:
        return {
            "is_liquid": False,
            "depth_usd": 0.0,
            "slippage_pct": 100.0,
            "bid_depth_usd": 0.0,
            "ask_depth_usd": 0.0,
            "spread_pct": 0.0,
            "status": "error",
            "exchange_id": exchange_id,
            "symbol": symbol,
            "reason": reason,
        }
