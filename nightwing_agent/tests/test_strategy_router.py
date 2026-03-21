"""
Tests for Strategy Router

Tests routing opportunities to correct strategy paths.
"""

from core.strategy_router import (
    STRATEGY_MAP,
    get_strategy_name,
    get_action_type,
    get_priority,
    format_alert_message,
    route_opportunity,
    list_strategies,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test STRATEGY_MAP
# ─────────────────────────────────────────────────────────────────────────────


def test_strategy_map_has_all_types():
    """Test all opportunity types A-H are defined."""
    expected_types = ["A", "B", "C", "D", "E", "F", "G", "H"]
    for t in expected_types:
        assert t in STRATEGY_MAP


def test_strategy_map_has_required_fields():
    """Test each strategy has required fields."""
    required = ["strategy_name", "action_type", "priority", "template"]
    for opp_type, info in STRATEGY_MAP.items():
        for field in required:
            assert field in info, f"Type {opp_type} missing {field}"


# ─────────────────────────────────────────────────────────────────────────────
# Test get_strategy_name
# ─────────────────────────────────────────────────────────────────────────────


def test_get_strategy_name_valid():
    """Test getting strategy name for valid type."""
    assert get_strategy_name("C") == "p2p_spot_arb"
    assert get_strategy_name("D") == "multi_exchange"
    assert get_strategy_name("F") == "cross_currency_p2p"


def test_get_strategy_name_unknown():
    """Test getting strategy name for unknown type."""
    assert get_strategy_name("Z") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test get_action_type
# ─────────────────────────────────────────────────────────────────────────────


def test_get_action_type_execute():
    """Test type C has EXECUTE action."""
    assert get_action_type("C") == "EXECUTE"


def test_get_action_type_alert():
    """Test type D has ALERT action."""
    assert get_action_type("D") == "ALERT"


def test_get_action_type_unknown():
    """Test unknown type defaults to OBSERVE."""
    assert get_action_type("Z") == "OBSERVE"


# ─────────────────────────────────────────────────────────────────────────────
# Test get_priority
# ─────────────────────────────────────────────────────────────────────────────


def test_get_priority_values():
    """Test priority values are in valid range."""
    for opp_type in STRATEGY_MAP:
        priority = get_priority(opp_type)
        assert 1 <= priority <= 5


def test_get_priority_unknown():
    """Test unknown type defaults to lowest priority."""
    assert get_priority("Z") == 5


# ─────────────────────────────────────────────────────────────────────────────
# Test format_alert_message
# ─────────────────────────────────────────────────────────────────────────────


def test_format_alert_message_type_c():
    """Test formatting alert for type C."""
    opp = {
        "type": "C",
        "market": "MXN",
        "edge_net": 0.55,
        "depth_estimate": 15000,
    }
    msg = format_alert_message(opp)
    assert "P2P" in msg
    assert "MXN" in msg
    assert "0.55" in msg


def test_format_alert_message_type_d():
    """Test formatting alert for type D."""
    opp = {
        "type": "D",
        "asset": "BTC",
        "buy_exchange": "binance",
        "sell_exchange": "okx",
        "buy_price": 65000,
        "sell_price": 65100,
        "edge_net": 0.15,
    }
    msg = format_alert_message(opp)
    assert "BTC" in msg
    assert "binance" in msg
    assert "okx" in msg


def test_format_alert_message_type_h_depeg():
    """Test formatting alert for type H depeg event."""
    opp = {
        "type": "H",
        "event_type": "depeg",
        "stablecoin": "USDT",
        "exchange": "binance",
        "price": 0.990,
        "depeg_direction": "low",
    }
    msg = format_alert_message(opp)
    assert "USDT" in msg
    assert "depeg" in msg


def test_format_alert_message_unknown_type():
    """Test formatting alert for unknown type."""
    opp = {"type": "Z", "opp_id": "OPP-Z-001"}
    msg = format_alert_message(opp)
    assert "Unknown" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Test route_opportunity
# ─────────────────────────────────────────────────────────────────────────────


def test_route_opportunity_returns_all_fields():
    """Test route returns all required fields."""
    opp = {
        "opp_id": "OPP-C-001",
        "type": "C",
        "market": "MXN",
        "edge_net": 0.55,
        "depth_estimate": 15000,
        "viable": True,
    }
    result = route_opportunity(opp)

    assert "strategy_name" in result
    assert "action_type" in result
    assert "priority" in result
    assert "alert_message" in result
    assert "opp_id" in result
    assert "opp_type" in result
    assert "edge_net" in result
    assert "viable" in result


def test_route_opportunity_type_c():
    """Test routing type C opportunity."""
    opp = {
        "opp_id": "OPP-C-001",
        "type": "C",
        "market": "MXN",
        "edge_net": 0.55,
        "depth_estimate": 15000,
        "viable": True,
    }
    result = route_opportunity(opp)

    assert result["strategy_name"] == "p2p_spot_arb"
    assert result["action_type"] == "EXECUTE"
    assert result["edge_net"] == 0.55
    assert result["viable"] is True


def test_route_opportunity_type_g():
    """Test routing type G opportunity."""
    opp = {
        "opp_id": "OPP-G-001",
        "type": "G",
        "fiat": "MXN",
        "best_buy_price": 17.50,
        "best_sell_price": 17.65,
        "merchant_spread_pct": 0.86,
        "viable": True,
    }
    result = route_opportunity(opp)

    assert result["strategy_name"] == "p2p_merchant"
    assert result["action_type"] == "ALERT"
    # Should use merchant_spread_pct as edge
    assert result["edge_net"] == 0.86


def test_route_opportunity_fallback_edge():
    """Test edge_net fallback to alternative fields."""
    opp = {
        "opp_id": "OPP-E-001",
        "type": "E",
        "asset": "BTC",
        "exchange": "bybit",
        "funding_rate": 0.015,
        "annualized_pct": 19.71,
        "viable": True,
    }
    result = route_opportunity(opp)

    # Should use funding_rate as edge
    assert result["edge_net"] == 0.015


def test_route_opportunity_unknown_type():
    """Test routing unknown type."""
    opp = {
        "opp_id": "OPP-Z-001",
        "type": "Z",
        "edge_net": 0.50,
    }
    result = route_opportunity(opp)

    assert result["strategy_name"] == "unknown"
    assert result["action_type"] == "OBSERVE"
    assert result["priority"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# Test list_strategies
# ─────────────────────────────────────────────────────────────────────────────


def test_list_strategies_returns_all():
    """Test list returns all strategies."""
    strategies = list_strategies()
    assert len(strategies) == 8  # A-H


def test_list_strategies_format():
    """Test list returns correct format."""
    strategies = list_strategies()
    for opp_type, info in strategies.items():
        assert "strategy_name" in info
        assert "action_type" in info
        assert "priority" in info
