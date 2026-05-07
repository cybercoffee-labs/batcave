"""Narrative heuristics for HAWKGIRL."""

from __future__ import annotations

from typing import Any

MEME_SYMBOLS = {"DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "BRETT", "MOG", "PENGU"}
LAYER2_SYMBOLS = {"ARB", "OP", "STRK", "MNT", "METIS", "ZK", "LRC", "IMX"}
DEFI_SYMBOLS = {"UNI", "AAVE", "MKR", "CRV", "COMP", "SUSHI", "DYDX", "JUP", "PENDLE", "ENA"}
AI_SYMBOLS = {"FET", "AGIX", "OCEAN", "TAO", "RNDR", "RENDER", "ARKM", "AIXBT", "VIRTUAL"}
LATAM_P2P_SYMBOLS = {"USDT", "USDC", "BTC", "ETH", "XRP", "LTC", "TRX", "BNB", "DAI", "SOL", "DOGE"}


class NarrativeDetector:
    """Detect simple narrative clusters from trending tokens."""

    def _coin_matches(self, coin: dict[str, Any], symbols: set[str], category_terms: tuple[str, ...]) -> bool:
        symbol = str(coin.get("symbol", "")).upper()
        name = str(coin.get("name", "")).lower()
        categories = " ".join(str(category).lower() for category in coin.get("categories", []))
        return symbol in symbols or any(term in name or term in categories for term in category_terms)

    def detect_narratives(self, trending_coins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Identify dominant themes among the current trending set."""
        narrative_rules = [
            ("meme_season", MEME_SYMBOLS, ("meme", "dog-themed", "frog-themed")),
            ("layer2_season", LAYER2_SYMBOLS, ("layer 2", "rollup", "scaling")),
            ("defi_season", DEFI_SYMBOLS, ("decentralized finance", "defi", "dex")),
            ("ai_narrative", AI_SYMBOLS, ("artificial intelligence", "ai", "big data")),
        ]

        narratives: list[dict[str, Any]] = []
        for label, symbols, terms in narrative_rules:
            matching = [coin for coin in trending_coins if self._coin_matches(coin, symbols, terms)]
            if len(matching) >= 3:
                narratives.append(
                    {
                        "name": label,
                        "tokens": [coin["symbol"] for coin in matching],
                        "count": len(matching),
                    }
                )

        latam_tokens = [coin["symbol"] for coin in trending_coins if str(coin.get("symbol", "")).upper() in LATAM_P2P_SYMBOLS]
        if len(latam_tokens) >= 2:
            narratives.append(
                {
                    "name": "latam_opportunity",
                    "tokens": latam_tokens,
                    "count": len(latam_tokens),
                }
            )

        return sorted(narratives, key=lambda item: item["count"], reverse=True)

    def get_narrative_alert(self, narrative: dict[str, Any]) -> str:
        """Format a Clark Kent ready narrative alert."""
        tokens = ", ".join(f"${symbol}" for symbol in narrative.get("tokens", []))
        return (
            "📡 Batcave Narrative Alert\n"
            f"Detectando: {narrative.get('name', 'unknown')} en cripto\n"
            f"Tokens relacionados: {tokens}\n"
            "On-chain: verificar con CYBORG\n"
            "DYOR | No financial advice\n"
            "#crypto #analysis"
        )
