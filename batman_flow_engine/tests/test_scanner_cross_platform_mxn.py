"""Tests for Scanner I: Cross-Platform MXN"""

from unittest.mock import patch


def test_scanner_i_imports():
    """Scanner I modules import correctly."""
    from core.scanner_cross_platform_mxn import (
        scan_cross_platform_mxn,
        fetch_binance_p2p_mxn,
        fetch_bitso_spot_mxn,
    )

    assert callable(scan_cross_platform_mxn)
    assert callable(fetch_binance_p2p_mxn)
    assert callable(fetch_bitso_spot_mxn)


def test_sanity_check_rejects_outliers():
    """Sanity check should reject prices >3% from reference."""
    from core.scanner_cross_platform_mxn import _sanity_check

    prices = {
        "bitso_spot": {"buy": 17.90, "sell": 17.88, "last": 17.89, "status": "ok", "reliable": True},
        "binance_p2p": {"buy": 17.95, "sell": 18.00, "status": "ok", "reliable": True},
        "bybit_p2p": {"buy": 17.12, "sell": 17.92, "status": "ok", "reliable": True},
    }

    result = _sanity_check(prices)
    assert result["bitso_spot"]["reliable"] is True
    assert result["binance_p2p"]["reliable"] is True
    assert result["bybit_p2p"]["reliable"] is False


def test_sanity_check_accepts_close_prices():
    """Prices within 3% of reference should pass."""
    from core.scanner_cross_platform_mxn import _sanity_check

    prices = {
        "bitso_spot": {"buy": 17.90, "sell": 17.88, "last": 17.89, "status": "ok", "reliable": True},
        "binance_p2p": {"buy": 17.95, "sell": 18.00, "status": "ok", "reliable": True},
        "okx_p2p": {"buy": 18.02, "sell": 17.90, "status": "ok", "reliable": True},
    }

    result = _sanity_check(prices)
    assert all(v.get("reliable", False) for v in result.values() if v.get("status") == "ok")


def test_find_opportunities_only_reliable():
    """Only reliable platforms should produce opportunities."""
    from core.scanner_cross_platform_mxn import find_cross_platform_opportunities

    prices = {
        "bitso_spot": {"buy": 17.90, "sell": 17.88, "status": "ok", "reliable": True},
        "binance_p2p": {"buy": 17.95, "sell": 18.05, "status": "ok", "reliable": True},
        "bybit_p2p": {"buy": 15.00, "sell": 19.00, "status": "ok", "reliable": False},
    }

    opps = find_cross_platform_opportunities(prices, threshold=0.0)
    platforms_used = set()
    for o in opps:
        platforms_used.add(o["buy_platform"])
        platforms_used.add(o["sell_platform"])
    assert "bybit_p2p" not in platforms_used


def test_find_opportunities_calculates_fees():
    """Opportunities should account for fees and transfer costs."""
    from core.scanner_cross_platform_mxn import find_cross_platform_opportunities

    prices = {
        "bitso_spot": {"buy": 17.50, "sell": 17.48, "status": "ok", "reliable": True},
        "binance_p2p": {"buy": 17.95, "sell": 18.00, "status": "ok", "reliable": True},
    }

    opps = find_cross_platform_opportunities(prices, threshold=0.0)
    assert len(opps) > 0
    best = opps[0]
    assert best["gross_spread_pct"] > 0
    assert best["total_friction_pct"] > 0
    assert best["edge_net"] < best["gross_spread_pct"]


def test_find_opportunities_empty_high_threshold():
    """No viable routes when threshold is very high."""
    from core.scanner_cross_platform_mxn import find_cross_platform_opportunities

    prices = {
        "bitso_spot": {"buy": 17.90, "sell": 17.88, "status": "ok", "reliable": True},
        "binance_p2p": {"buy": 17.91, "sell": 17.89, "status": "ok", "reliable": True},
    }

    opps = find_cross_platform_opportunities(prices, threshold=5.0)
    viable = [o for o in opps if o["viable"]]
    assert len(viable) == 0


def test_scanner_i_handles_api_errors():
    """Scanner should not crash if APIs fail."""
    from core.scanner_cross_platform_mxn import scan_cross_platform_mxn

    with patch("core.scanner_cross_platform_mxn._fetch_json", return_value=None):
        results = scan_cross_platform_mxn(log_to_file=False)
        assert isinstance(results, list)
