"""
Tests for Scanner F: P2P Cross-Currency Premium Scanner

Mocks all HTTP calls for isolated testing.
"""

import json
from unittest.mock import patch

from core.scanner_p2p_cross_currency import (
    calculate_premium,
    find_cross_currency_opportunities,
    fetch_all_premiums,
    scan_cross_currency,
    _get_transfer_cost,
    _load_threshold,
    SCANNER_ID,
    CURRENCIES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test calculate_premium
# ─────────────────────────────────────────────────────────────────────────────


def test_calculate_premium_positive():
    """Test premium calculation when P2P > spot (positive premium)."""
    p2p_buy = 17.50
    spot_rate = 17.00
    result = calculate_premium(p2p_buy, spot_rate)
    expected = ((17.50 - 17.00) / 17.00) * 100  # 2.94%
    assert abs(result - expected) < 0.01


def test_calculate_premium_negative():
    """Test premium calculation when P2P < spot (negative premium/discount)."""
    p2p_buy = 16.50
    spot_rate = 17.00
    result = calculate_premium(p2p_buy, spot_rate)
    assert result < 0


def test_calculate_premium_zero_spot():
    """Test premium returns 0 when spot rate is zero (avoid division by zero)."""
    result = calculate_premium(17.50, 0)
    assert result == 0.0


def test_calculate_premium_equal():
    """Test premium calculation when P2P equals spot."""
    result = calculate_premium(17.00, 17.00)
    assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test _get_transfer_cost
# ─────────────────────────────────────────────────────────────────────────────


def test_get_transfer_cost_known_pair():
    """Test transfer cost for known currency pairs."""
    cost = _get_transfer_cost("MXN", "ARS")
    assert cost == 1.0


def test_get_transfer_cost_reverse_order():
    """Test transfer cost works regardless of order."""
    cost1 = _get_transfer_cost("MXN", "ARS")
    cost2 = _get_transfer_cost("ARS", "MXN")
    assert cost1 == cost2


def test_get_transfer_cost_unknown_pair():
    """Test default cost for unknown pair."""
    cost = _get_transfer_cost("USD", "EUR")
    assert cost == 1.0  # Default


# ─────────────────────────────────────────────────────────────────────────────
# Test find_cross_currency_opportunities
# ─────────────────────────────────────────────────────────────────────────────


def test_find_opportunities_with_spread():
    """Test finding opportunities when cross-spread exceeds threshold."""
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50},
        "ARS": {"status": "ok", "premium_pct": 3.0, "p2p_buy": 1050.0},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 1
    assert opps[0]["buy_fiat"] == "MXN"
    assert opps[0]["sell_fiat"] == "ARS"
    assert opps[0]["cross_premium_spread"] == 2.5


def test_find_opportunities_below_threshold():
    """Test no opportunities when spread below threshold."""
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 2.0, "p2p_buy": 17.50},
        "ARS": {"status": "ok", "premium_pct": 2.5, "p2p_buy": 1050.0},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 0


def test_find_opportunities_insufficient_currencies():
    """Test no opportunities with only one valid currency."""
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 2.0, "p2p_buy": 17.50},
        "ARS": {"status": "error", "error": "No data"},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 0


def test_find_opportunities_viable_flag():
    """Test viable flag set correctly based on edge_net."""
    # Create scenario where edge_net > 0 (viable)
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 0.0, "p2p_buy": 17.00},
        "ARS": {"status": "ok", "premium_pct": 3.0, "p2p_buy": 1050.0},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 1
    # Spread 3.0%, transfer cost 1.0%, edge_net = 2.0%
    assert opps[0]["viable"] is True
    assert opps[0]["edge_net"] == 2.0


def test_find_opportunities_not_viable():
    """Test viable=False when edge_net <= 0."""
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.00},
        "VES": {"status": "ok", "premium_pct": 1.5, "p2p_buy": 50.0},
    }
    # Spread: 1.5 - 0.5 = 1.0%, transfer cost MXN-VES = 1.2%, edge = -0.2%
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 1
    assert opps[0]["viable"] is False


def test_find_opportunities_route_format():
    """Test route string is formatted correctly."""
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50},
        "ARS": {"status": "ok", "premium_pct": 3.0, "p2p_buy": 1050.0},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert "MXN→USDT(Binance P2P)→USDT→ARS(Binance P2P)" in opps[0]["route"]


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all_premiums (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_p2p_cross_currency.get_fiat_spot_rates")
@patch("core.scanner_p2p_cross_currency.get_p2p_price_binance")
def test_fetch_all_premiums_success(mock_p2p, mock_spot):
    """Test fetching premiums for all currencies."""
    mock_spot.return_value = {
        "MXN": {"rate": 17.00, "source": "open.er-api.com", "rate_type": "official"},
        "ARS": {"rate": 1000.00, "source": "open.er-api.com", "rate_type": "official"},
        "COP": {"rate": 4000.00, "source": "open.er-api.com", "rate_type": "official"},
        "VES": {"rate": 45.00, "source": "dolarapi.com", "rate_type": "parallel"},
    }
    mock_p2p.side_effect = lambda fiat, asset, trade_type: {
        "MXN": 17.50,
        "ARS": 1050.00,
        "COP": 4100.00,
        "VES": 46.00,
    }.get(fiat)

    result = fetch_all_premiums()

    assert "MXN" in result
    assert result["MXN"]["status"] == "ok"
    assert result["MXN"]["premium_pct"] > 0


@patch("core.scanner_p2p_cross_currency.get_fiat_spot_rates")
@patch("core.scanner_p2p_cross_currency.get_p2p_price_binance")
def test_fetch_all_premiums_partial_failure(mock_p2p, mock_spot):
    """Test handling partial failures."""
    mock_spot.return_value = {
        "MXN": {"rate": 17.00, "source": "test"},
        "ARS": {"rate": None},  # Missing rate
    }
    mock_p2p.side_effect = lambda fiat, asset, trade_type: {
        "MXN": 17.50,
        "ARS": None,  # No P2P data
    }.get(fiat)

    result = fetch_all_premiums()

    assert result["MXN"]["status"] == "ok"
    assert result["ARS"]["status"] == "no_data"


@patch("core.scanner_p2p_cross_currency.get_fiat_spot_rates")
@patch("core.scanner_p2p_cross_currency.get_p2p_price_binance")
def test_fetch_all_premiums_exception(mock_p2p, mock_spot):
    """Test handling exceptions during fetch."""
    mock_spot.return_value = {"MXN": {"rate": 17.00}}
    mock_p2p.side_effect = Exception("API error")

    result = fetch_all_premiums()

    assert result["MXN"]["status"] == "error"
    assert "API error" in result["MXN"]["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test scan_cross_currency (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_p2p_cross_currency._append_to_log")
@patch("core.scanner_p2p_cross_currency.fetch_all_premiums")
def test_scan_cross_currency_logs_opportunities(mock_fetch, mock_log):
    """Test scan logs opportunities to file."""
    mock_fetch.return_value = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50},
        "ARS": {"status": "ok", "premium_pct": 3.5, "p2p_buy": 1050.0},
    }
    mock_log.return_value = True

    result = scan_cross_currency(log_to_file=True)

    assert len(result) == 1
    mock_log.assert_called()


@patch("core.scanner_p2p_cross_currency._append_to_log")
@patch("core.scanner_p2p_cross_currency.fetch_all_premiums")
def test_scan_cross_currency_opportunity_format(mock_fetch, mock_log):
    """Test opportunity output format."""
    mock_fetch.return_value = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50},
        "ARS": {"status": "ok", "premium_pct": 3.5, "p2p_buy": 1050.0},
    }
    mock_log.return_value = True

    result = scan_cross_currency(log_to_file=False)

    assert len(result) == 1
    opp = result[0]
    assert opp["type"] == "F"
    assert opp["scanner_id"] == SCANNER_ID
    assert opp["opp_id"].startswith("OPP-F-")
    assert "ts" in opp
    assert "buy_fiat" in opp
    assert "sell_fiat" in opp
    assert "edge_net" in opp
    assert opp["observe_only"] is True
    assert opp["asset"] == "USDT"
    assert opp["market"] == f"{opp['buy_fiat']}/{opp['sell_fiat']}"


@patch("core.scanner_p2p_cross_currency._append_to_log")
@patch("core.scanner_p2p_cross_currency.fetch_all_premiums")
def test_scan_cross_currency_no_log_when_disabled(mock_fetch, mock_log):
    """Test no logging when log_to_file=False."""
    mock_fetch.return_value = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50},
        "ARS": {"status": "ok", "premium_pct": 3.5, "p2p_buy": 1050.0},
    }

    scan_cross_currency(log_to_file=False)

    mock_log.assert_not_called()


@patch("core.scanner_p2p_cross_currency.fetch_all_premiums")
def test_scan_cross_currency_returns_list(mock_fetch):
    """Test scan always returns a list."""
    mock_fetch.return_value = {
        "MXN": {"status": "error", "error": "Test"},
        "ARS": {"status": "error", "error": "Test"},
    }

    result = scan_cross_currency(log_to_file=False)

    assert isinstance(result, list)
    assert len(result) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test _load_threshold
# ─────────────────────────────────────────────────────────────────────────────


def test_load_threshold_default():
    """Test default threshold when config not available."""
    with patch("core.scanner_p2p_cross_currency.CONFIG_FILE") as mock_path:
        mock_path.exists.return_value = False
        result = _load_threshold()
        assert result == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Test JSON serialization (numpy.bool_ / numpy.float64 regression)
# ─────────────────────────────────────────────────────────────────────────────


def test_find_opportunities_json_serializable():
    """Regression: viable must be native bool, all floats native — no numpy types."""
    try:
        import numpy as np

        buy_premium = np.float64(0.5)
        sell_premium = np.float64(3.0)
    except ImportError:
        buy_premium = 0.5
        sell_premium = 3.0

    premiums = {
        "MXN": {"status": "ok", "premium_pct": buy_premium, "p2p_buy": float(17.50)},
        "ARS": {"status": "ok", "premium_pct": sell_premium, "p2p_buy": float(1050.0)},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 1

    # Must not raise TypeError: Object of type bool_ is not JSON serializable
    serialized = json.dumps(opps[0])
    parsed = json.loads(serialized)

    assert isinstance(parsed["viable"], bool)
    assert isinstance(parsed["edge_net"], float)
    assert isinstance(parsed["buy_premium_pct"], float)
    assert isinstance(parsed["sell_premium_pct"], float)
    assert isinstance(parsed["buy_p2p_price"], float)


# ─────────────────────────────────────────────────────────────────────────────
# Test reference_price output contract (Patch C — normalized schema)
# ─────────────────────────────────────────────────────────────────────────────


def test_find_opportunities_has_reference_price():
    """reference_price must be present and equal buy_data spot_rate."""
    premiums = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50, "spot_rate": 17.00},
        "ARS": {"status": "ok", "premium_pct": 3.0, "p2p_buy": 1050.0, "spot_rate": 1000.0},
    }
    opps = find_cross_currency_opportunities(premiums, threshold=1.0)
    assert len(opps) == 1
    opp = opps[0]
    assert "reference_price" in opp
    # buy_fiat is MXN (lower premium), reference_price = MXN spot_rate
    assert opp["reference_price"] == 17.00
    assert opp["reference_price"] > 0


@patch("core.scanner_p2p_cross_currency._append_to_log")
@patch("core.scanner_p2p_cross_currency.fetch_all_premiums")
def test_scan_cross_currency_record_has_reference_price(mock_fetch, mock_log):
    """Full scan output records must carry reference_price for ALFRED validation."""
    mock_fetch.return_value = {
        "MXN": {"status": "ok", "premium_pct": 0.5, "p2p_buy": 17.50, "spot_rate": 17.00},
        "ARS": {"status": "ok", "premium_pct": 3.5, "p2p_buy": 1050.0, "spot_rate": 1000.0},
    }
    mock_log.return_value = True

    result = scan_cross_currency(log_to_file=False)

    assert len(result) == 1
    opp = result[0]
    assert "reference_price" in opp
    assert isinstance(opp["reference_price"], float)
    assert opp["reference_price"] > 0
    # spot_price is absent — reference_price is the sole price reference
    assert "spot_price" not in opp


# ─────────────────────────────────────────────────────────────────────────────
# Test constants
# ─────────────────────────────────────────────────────────────────────────────


def test_scanner_id_format():
    """Test scanner ID follows convention."""
    assert SCANNER_ID == "F-P2P-CROSS-CURRENCY"


def test_currencies_list():
    """Test expected currencies are included."""
    assert "MXN" in CURRENCIES
    assert "ARS" in CURRENCIES
    assert "COP" in CURRENCIES
    assert "VES" in CURRENCIES
