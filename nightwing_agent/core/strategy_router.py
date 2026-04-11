"""
STRATEGY ROUTER — Routes opportunities to correct execution paths.

Maps opportunity types (A-H) to strategy names, alert templates, and actions.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("nightwing.strategy_router")

# ─────────────────────────────────────────────────────────────────────────────
# Strategy Mapping
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_MAP = {
    "A": {
        "strategy_name": "cross_exchange",
        "action_type": "ALERT",
        "priority": 2,
        "template": "Cross-exchange arbitrage: Buy {asset} on {buy_exchange}, sell on {sell_exchange}. Spread: {spread_pct:.2f}%",
    },
    "B": {
        "strategy_name": "basis_trade",
        "action_type": "ALERT",
        "priority": 2,
        "template": "Basis trade: {asset} spot vs futures. Basis: {basis_pct:.2f}%",
    },
    "C": {
        "strategy_name": "p2p_spot_arb",
        "action_type": "EXECUTE",
        "priority": 1,
        "template": "P2P spot arbitrage: {market} edge {edge_net:.2f}%. Depth: ${depth_estimate:,.0f}",
    },
    "D": {
        "strategy_name": "multi_exchange",
        "action_type": "ALERT",
        "priority": 2,
        "template": "Multi-exchange arb: {asset} buy@{buy_exchange} ${buy_price:,.2f} → sell@{sell_exchange} ${sell_price:,.2f}. Edge: {edge_net:.2f}%",
    },
    "E": {
        "strategy_name": "funding_rate",
        "action_type": "ALERT",
        "priority": 3,
        "template": "Funding rate opportunity: {asset} on {exchange}. Rate: {funding_rate:.4f}% ({annualized_pct:.1f}% APY)",
    },
    "F": {
        "strategy_name": "cross_currency_p2p",
        "action_type": "ALERT",
        "priority": 2,
        "template": "Cross-currency P2P: Buy USDT with {buy_fiat}, sell for {sell_fiat}. Edge: {edge_net:.2f}%",
    },
    "G": {
        "strategy_name": "p2p_merchant",
        "action_type": "ALERT",
        "priority": 2,
        "template": "P2P merchant spread: {fiat} buy@{best_buy_price:.2f} → sell@{best_sell_price:.2f}. Spread: {merchant_spread_pct:.2f}%",
    },
    "H": {
        "strategy_name": "stablecoin_depeg",
        "action_type": "ALERT",
        "priority": 1,
        "template": "Stablecoin {event_type}: {stablecoin} — {alert_detail}",
    },
}


def get_strategy_name(opp_type: str) -> Optional[str]:
    """
    Get strategy name for an opportunity type.

    Args:
        opp_type: Opportunity type (A-H)

    Returns:
        Strategy name or None if unknown
    """
    strategy = STRATEGY_MAP.get(opp_type)
    return strategy["strategy_name"] if strategy else None


def get_action_type(opp_type: str) -> str:
    """
    Get action type for an opportunity type.

    Args:
        opp_type: Opportunity type (A-H)

    Returns:
        Action type: EXECUTE, ALERT, or OBSERVE
    """
    strategy = STRATEGY_MAP.get(opp_type)
    return strategy["action_type"] if strategy else "OBSERVE"


def get_priority(opp_type: str) -> int:
    """
    Get priority level for an opportunity type.

    Args:
        opp_type: Opportunity type (A-H)

    Returns:
        Priority: 1 (highest) to 5 (lowest)
    """
    strategy = STRATEGY_MAP.get(opp_type)
    return strategy["priority"] if strategy else 5


def _format_h_detail(opp: Dict[str, Any]) -> str:
    """Format detail string for stablecoin depeg alerts."""
    event_type = opp.get("event_type", "unknown")

    if event_type == "depeg":
        return f"Price {opp.get('price', 0):.4f} on {opp.get('exchange', 'unknown')} ({opp.get('depeg_direction', '')})"
    elif event_type == "arbitrage":
        return f"Buy@{opp.get('buy_exchange', '')} → Sell@{opp.get('sell_exchange', '')}. Spread: {opp.get('spread_pct', 0):.2f}%"
    else:
        return "Unknown event"


def format_alert_message(opp: Dict[str, Any]) -> str:
    """
    Format alert message for an opportunity.

    Args:
        opp: Opportunity dict with type and data fields

    Returns:
        Formatted alert message string
    """
    opp_type = opp.get("type")
    strategy = STRATEGY_MAP.get(opp_type)

    if not strategy:
        return f"Unknown opportunity type: {opp_type}"

    template = strategy["template"]

    # Handle special case for type H (stablecoin depeg)
    if opp_type == "H":
        opp = {**opp, "alert_detail": _format_h_detail(opp)}

    try:
        return template.format(**opp)
    except KeyError as e:
        logger.warning(f"Missing field {e} for alert template type={opp_type}")
        return f"{strategy['strategy_name']}: {opp.get('opp_id', 'unknown')} — edge {opp.get('edge_net', 0):.2f}%"


def route_opportunity(opp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route an opportunity to its strategy and generate routing info.

    Args:
        opp: Opportunity dict with type and data fields

    Returns:
        Dict with routing information:
        {
            "strategy_name": str,
            "action_type": str,
            "priority": int,
            "alert_message": str,
            "opp_id": str,
            "opp_type": str,
            "edge_net": float,
            "viable": bool,
        }
    """
    opp_type = opp.get("type")
    opp_id = opp.get("opp_id", "unknown")

    strategy_name = get_strategy_name(opp_type)
    action_type = get_action_type(opp_type)
    priority = get_priority(opp_type)
    alert_message = format_alert_message(opp)

    # Get edge_net (try multiple fields)
    edge_net = opp.get("edge_net")
    if edge_net is None:
        for alt in ("spread_pct", "p2p_premium", "merchant_spread_pct", "funding_rate"):
            if opp.get(alt) is not None:
                edge_net = opp[alt]
                break
    if edge_net is None:
        edge_net = 0.0

    logger.info(
        "Routed opp_id=%s type=%s → strategy=%s action=%s priority=%d",
        opp_id,
        opp_type,
        strategy_name,
        action_type,
        priority,
    )

    return {
        "strategy_name": strategy_name or "unknown",
        "action_type": action_type,
        "priority": priority,
        "alert_message": alert_message,
        "opp_id": opp_id,
        "opp_type": opp_type,
        "edge_net": edge_net,
        "viable": opp.get("viable", False),
    }


def list_strategies() -> Dict[str, Dict[str, Any]]:
    """
    Return all available strategies.

    Returns:
        Dict mapping type to strategy info
    """
    return {
        opp_type: {
            "strategy_name": info["strategy_name"],
            "action_type": info["action_type"],
            "priority": info["priority"],
        }
        for opp_type, info in STRATEGY_MAP.items()
    }
