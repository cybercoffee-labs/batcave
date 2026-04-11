"""
P2P market microstructure metrics for Nightwing.

Role:
- Compute simple read-only depth indicators from an existing P2P depth payload.
- Keep the logic separate from Batman and execution flow.
"""

from __future__ import annotations

from typing import Any


def _offer_size(offer: dict[str, Any]) -> float:
    """Return the normalized offer size used for liquidity calculations."""
    value = offer.get("max_single_trans_amount_value")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _top_liquidity(offers: list[dict[str, Any]], limit: int) -> float:
    """Sum normalized offer sizes for the top N offers on one side."""
    return sum(_offer_size(offer) for offer in offers[:limit])


def compute_depth_metrics(depth_payload: dict[str, Any]) -> dict[str, Any]:
    """Compute compact liquidity and imbalance metrics from a P2P depth snapshot."""
    buy_offers = depth_payload.get("buy_offers")
    if not isinstance(buy_offers, list):
        buy_offers = []

    sell_offers = depth_payload.get("sell_offers")
    if not isinstance(sell_offers, list):
        sell_offers = []

    best_buy = depth_payload.get("best_buy")
    best_sell = depth_payload.get("best_sell")
    spread = None
    if isinstance(best_buy, (int, float)) and isinstance(best_sell, (int, float)):
        spread = float(best_sell) - float(best_buy)

    buy_liquidity = sum(_offer_size(offer) for offer in buy_offers)
    sell_liquidity = sum(_offer_size(offer) for offer in sell_offers)
    total_liquidity = buy_liquidity + sell_liquidity
    if total_liquidity > 0:
        depth_imbalance = (buy_liquidity - sell_liquidity) / total_liquidity
    else:
        depth_imbalance = None

    top5_liquidity = _top_liquidity(buy_offers, 5) + _top_liquidity(sell_offers, 5)
    top10_liquidity = _top_liquidity(buy_offers, 10) + _top_liquidity(sell_offers, 10)

    return {
        "spread": spread,
        "buy_liquidity": buy_liquidity,
        "sell_liquidity": sell_liquidity,
        "depth_imbalance": depth_imbalance,
        "top5_liquidity": top5_liquidity,
        "top10_liquidity": top10_liquidity,
    }
