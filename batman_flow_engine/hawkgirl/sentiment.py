"""Public sentiment helpers for HAWKGIRL."""

from __future__ import annotations

from typing import Any

import requests

USER_AGENT = "batman-flow-engine/1.0"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_COIN_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"


class SentimentAnalyzer:
    """Fetch market-wide sentiment and trending public crypto signals."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _get_coin_details(self, coin_id: str) -> dict[str, Any]:
        try:
            return self._get_json(
                COINGECKO_COIN_URL.format(coin_id=coin_id),
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "true",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
        except requests.RequestException:
            return {}

    def get_market_sentiment(self) -> dict[str, Any]:
        """Return a compact public market sentiment snapshot."""
        fear_greed = self._get_json(FEAR_GREED_URL, params={"limit": 1, "format": "json"})
        global_data = self._get_json(COINGECKO_GLOBAL_URL)

        fear_greed_data = fear_greed.get("data", [{}])[0]
        global_payload = global_data.get("data", {})
        market_cap_pct = global_payload.get("market_cap_percentage", {})

        fear_greed_index = int(fear_greed_data.get("value", 0) or 0)
        fear_greed_label = str(fear_greed_data.get("value_classification", "Unknown"))
        market_cap_change = float(global_payload.get("market_cap_change_percentage_24h_usd", 0.0) or 0.0)
        btc_dominance = float(market_cap_pct.get("btc", 0.0) or 0.0)

        sentiment_label = "neutral"
        if fear_greed_index >= 60 and market_cap_change > 0:
            sentiment_label = "bullish"
        elif fear_greed_index <= 40 and market_cap_change < 0:
            sentiment_label = "bearish"

        return {
            "fear_greed_index": fear_greed_index,
            "fear_greed_label": fear_greed_label,
            "market_cap_change_24h": market_cap_change,
            "btc_dominance": btc_dominance,
            "sentiment_label": sentiment_label,
        }

    def get_trending_coins(self) -> list[dict[str, Any]]:
        """Return the top seven CoinGecko trending coins sorted by 24h change."""
        trending = self._get_json(COINGECKO_TRENDING_URL)
        results: list[dict[str, Any]] = []

        for entry in trending.get("coins", [])[:7]:
            item = entry.get("item", {})
            coin_id = item.get("id") or item.get("coin_id")
            details = self._get_coin_details(str(coin_id)) if coin_id else {}

            price_change = (
                item.get("data", {})
                .get("price_change_percentage_24h", {})
                .get("usd")
            )
            if price_change is None:
                price_change = (
                    details.get("market_data", {})
                    .get("price_change_percentage_24h_in_currency", {})
                    .get("usd", 0.0)
                )

            results.append(
                {
                    "id": coin_id,
                    "name": item.get("name", ""),
                    "symbol": str(item.get("symbol", "")).upper(),
                    "market_cap_rank": int(item.get("market_cap_rank") or details.get("market_cap_rank") or 999999),
                    "price_change_24h": float(price_change or 0.0),
                    "categories": details.get("categories", []),
                    "social_volume": int(details.get("watchlist_portfolio_users") or 0),
                }
            )

        return sorted(results, key=lambda coin: coin.get("price_change_24h", 0.0), reverse=True)
