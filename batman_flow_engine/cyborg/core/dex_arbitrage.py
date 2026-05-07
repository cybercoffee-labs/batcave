"""DEX versus CEX arbitrage scanner for CYBORG."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/search"
USER_AGENT = "batman-flow-engine/cyborg/0.1.0"


@dataclass(frozen=True)
class ArbitragePair:
    token: str
    binance_symbol: str
    search_terms: tuple[str, ...]


DEFAULT_PAIRS = (
    ArbitragePair("ETH", "ETHUSDT", ("ETH", "WETH", "ETH USDT")),
    ArbitragePair("SOL", "SOLUSDT", ("SOL", "SOL USDC", "SOL USDT")),
    ArbitragePair("ARB", "ARBUSDT", ("ARB", "ARB USDC", "ARB USDT")),
    ArbitragePair("OP", "OPUSDT", ("OP", "OP USDC", "OP USDT")),
    ArbitragePair("AVAX", "AVAXUSDT", ("AVAX", "WAVAX", "AVAX USDT")),
    ArbitragePair("LINK", "LINKUSDT", ("LINK", "LINK USDC", "LINK USDT")),
    ArbitragePair("UNI", "UNIUSDT", ("UNI", "UNI USDC", "UNI USDT")),
)


class DexArbitrageScanner:
    """Compare Binance prices with liquid DEX pairs from DexScreener."""

    def __init__(
        self,
        min_spread_pct: float = 0.5,
        timeout: float = 10.0,
        dry_run: bool = False,
    ) -> None:
        self.min_spread_pct = min_spread_pct
        self.timeout = timeout
        self.dry_run = dry_run

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if self.dry_run:
            return None
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def _fetch_binance_price(
        self,
        client: httpx.AsyncClient,
        pair: ArbitragePair,
    ) -> float | None:
        data = await self._get_json(client, BINANCE_URL, {"symbol": pair.binance_symbol})
        if not data:
            return None
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError):
            return None

    async def _fetch_dex_quote(
        self,
        client: httpx.AsyncClient,
        pair: ArbitragePair,
    ) -> dict[str, Any] | None:
        for term in pair.search_terms:
            data = await self._get_json(client, DEXSCREENER_URL, {"q": term})
            best = self._select_best_pair(pair.token, data or {})
            if best:
                return best
        return None

    def _select_best_pair(self, token: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        pairs = payload.get("pairs")
        if not isinstance(pairs, list):
            return None

        candidates: list[dict[str, Any]] = []
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            base_symbol = str(pair.get("baseToken", {}).get("symbol", "")).upper()
            quote_symbol = str(pair.get("quoteToken", {}).get("symbol", "")).upper()
            if base_symbol != token.upper():
                continue
            if quote_symbol not in {"USDT", "USDC", "USD"}:
                continue
            try:
                price_usd = float(pair["priceUsd"])
            except (KeyError, TypeError, ValueError):
                continue
            if price_usd <= 0:
                continue
            candidates.append(pair)

        if not candidates:
            return None

        def score(pair: dict[str, Any]) -> tuple[float, float]:
            liquidity = _safe_float(pair.get("liquidity", {}).get("usd"))
            volume = _safe_float(pair.get("volume", {}).get("h24"))
            return (liquidity, volume)

        return max(candidates, key=score)

    async def scan_all_pairs(self) -> list[dict[str, Any]]:
        if self.dry_run:
            return [
                {
                    "token": "ETH",
                    "cex_exchange": "Binance",
                    "cex_symbol": "ETHUSDT",
                    "cex_price": 3000.0,
                    "dex_price": 3018.0,
                    "dex_name": "uniswap",
                    "chain": "ethereum",
                    "spread_pct": 0.6,
                    "direction": "buy_cex_sell_dex",
                    "pair_address": "dry-run",
                    "flagged": True,
                }
            ]

        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            opportunities: list[dict[str, Any]] = []
            for pair in DEFAULT_PAIRS:
                cex_price = await self._fetch_binance_price(client, pair)
                dex_pair = await self._fetch_dex_quote(client, pair)
                if cex_price is None or dex_pair is None:
                    continue

                dex_price = _safe_float(dex_pair.get("priceUsd"))
                if dex_price <= 0 or cex_price <= 0:
                    continue

                spread_pct = abs((dex_price - cex_price) / cex_price) * 100
                if spread_pct <= self.min_spread_pct:
                    continue

                direction = "buy_dex_sell_cex" if dex_price < cex_price else "buy_cex_sell_dex"
                opportunities.append(
                    {
                        "token": pair.token,
                        "cex_exchange": "Binance",
                        "cex_symbol": pair.binance_symbol,
                        "cex_price": round(cex_price, 8),
                        "dex_price": round(dex_price, 8),
                        "dex_name": dex_pair.get("dexId", "unknown"),
                        "chain": dex_pair.get("chainId", "unknown"),
                        "spread_pct": round(spread_pct, 4),
                        "direction": direction,
                        "pair_address": dex_pair.get("pairAddress", ""),
                        "flagged": True,
                    }
                )
            return opportunities

    def format_opportunity(self, opp: dict[str, Any]) -> str:
        return (
            f"[CYBORG][DEX_ARB] {opp['token']} {opp['spread_pct']:.2f}% spread | "
            f"CEX ${opp['cex_price']:.4f} vs DEX ${opp['dex_price']:.4f} | "
            f"{opp['direction']} via {opp['dex_name']} ({opp['chain']})"
        )


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
