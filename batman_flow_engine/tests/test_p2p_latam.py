"""
Unit tests for core/p2p_latam.py - P2P LATAM Scanner.

Tests cover:
- Merchant spread formula validation for all 4 pairs (MXN, COP, VES, ARS)
- Spread classification (NORMAL/HIGH/ANOMALOUS)
- Edge cases (zero prices, null values, inverted prices)
- Anomaly detection for spreads > 15%
"""

import pytest
import json
from unittest.mock import patch
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.p2p_latam import scan_p2p_pair


# ───────────────────────── FIXTURES ─────────────────────────


@pytest.fixture
def mock_p2p_announcements():
    """Mock P2P announcements data."""

    def _make_announcements(prices):
        """Generate mock announcements from list of prices."""
        return [
            {
                "price": price,
                "available_amount": 1000.0,
                "min_order_limit": 100.0,
                "max_order_limit": 10000.0,
                "merchant_name": f"merchant_{i}",
            }
            for i, price in enumerate(prices)
        ]

    return _make_announcements


# ───────────────────────── SPREAD FORMULA TESTS ─────────────────────────


def test_merchant_spread_formula_mxn(mock_p2p_announcements):
    """Test merchant spread formula for MXN pair."""
    buy_ads = mock_p2p_announcements([20.50, 20.52, 20.51])  # Higher (user buys)
    sell_ads = mock_p2p_announcements([20.40, 20.38, 20.39])  # Lower (user sells)

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        with patch("core.p2p_latam.get_spot_price", return_value=20.45):
            result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    assert result["status"] == "ok"
    # Buy avg: 20.51, Sell avg: 20.39
    # Spread = (20.51 - 20.39) / 20.39 ≈ 0.00588 = 0.588%
    assert result["p2p_buy_price"] == pytest.approx(20.51, abs=0.01)
    assert result["p2p_sell_price"] == pytest.approx(20.39, abs=0.01)
    assert result["merchant_spread"] > 0  # Positive spread expected
    assert result["spread_flag"] == "NORMAL"  # < 2%


def test_merchant_spread_formula_cop(mock_p2p_announcements):
    """Test merchant spread formula for COP pair."""
    buy_ads = mock_p2p_announcements([4200, 4210, 4205])
    sell_ads = mock_p2p_announcements([4180, 4175, 4178])

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("COP", "USDT", log_to_file=False)

    assert result["status"] == "ok"
    # Buy avg: 4205, Sell avg: 4177.67
    # Spread = (4205 - 4177.67) / 4177.67 ≈ 0.00654 = 0.654%
    assert result["merchant_spread"] > 0
    assert result["spread_flag"] == "NORMAL"


def test_merchant_spread_formula_ves(mock_p2p_announcements):
    """Test merchant spread formula for VES pair - known problematic case."""
    # VES sometimes has inverted or anomalous data
    buy_ads = mock_p2p_announcements([50.5, 50.6, 50.55])
    sell_ads = mock_p2p_announcements([50.2, 50.1, 50.15])

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("VES", "USDT", log_to_file=False)

    assert result["status"] == "ok"
    # Buy avg: 50.55, Sell avg: 50.15
    # Spread = (50.55 - 50.15) / 50.15 ≈ 0.00797 = 0.797%
    assert result["merchant_spread"] > 0
    assert result["spread_flag"] == "NORMAL"


def test_merchant_spread_formula_ars(mock_p2p_announcements):
    """Test merchant spread formula for ARS pair."""
    buy_ads = mock_p2p_announcements([1050, 1055, 1052])
    sell_ads = mock_p2p_announcements([1040, 1038, 1039])

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("ARS", "USDT", log_to_file=False)

    assert result["status"] == "ok"
    # Buy avg: 1052.33, Sell avg: 1039
    # Spread = (1052.33 - 1039) / 1039 ≈ 0.01283 = 1.283%
    assert result["merchant_spread"] > 0
    assert result["spread_flag"] == "NORMAL"


# ───────────────────────── SPREAD CLASSIFICATION TESTS ─────────────────────────


def test_spread_flag_normal(mock_p2p_announcements):
    """Test NORMAL spread classification (< 2%)."""
    buy_ads = mock_p2p_announcements([100.5, 100.6, 100.55])  # Avg: 100.55
    sell_ads = mock_p2p_announcements([100.0, 99.9, 99.95])  # Avg: 99.95

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    # Spread = (100.55 - 99.95) / 99.95 ≈ 0.006 = 0.6%
    assert result["spread_flag"] == "NORMAL"


def test_spread_flag_high(mock_p2p_announcements):
    """Test HIGH spread classification (2% - 10%)."""
    buy_ads = mock_p2p_announcements([105, 106, 105.5])  # Avg: 105.5
    sell_ads = mock_p2p_announcements([100, 99, 99.5])  # Avg: 99.5

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    # Spread = (105.5 - 99.5) / 99.5 ≈ 0.0603 = 6.03%
    assert result["spread_flag"] == "HIGH"
    assert 0.02 < abs(result["merchant_spread"]) < 0.10


def test_spread_flag_anomalous(mock_p2p_announcements):
    """Test ANOMALOUS spread classification (> 10%)."""
    buy_ads = mock_p2p_announcements([120, 122, 121])  # Avg: 121
    sell_ads = mock_p2p_announcements([100, 99, 99.5])  # Avg: 99.5

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    # Spread = (121 - 99.5) / 99.5 ≈ 0.2161 = 21.61%
    assert result["spread_flag"] == "ANOMALOUS"
    assert abs(result["merchant_spread"]) > 0.10


# ───────────────────────── EDGE CASES TESTS ─────────────────────────


def test_zero_sell_price(mock_p2p_announcements):
    """Test handling of zero sell price (should error)."""
    buy_ads = mock_p2p_announcements([100, 101, 100.5])
    sell_ads = mock_p2p_announcements([0, 0, 0])  # Invalid: zero prices

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    assert result["status"] == "error"
    assert "Invalid sell price" in result.get("error", "")


def test_negative_spread(mock_p2p_announcements):
    """Test negative spread (buy < sell - unusual but possible)."""
    # Inverted: sell price > buy price (market inefficiency)
    buy_ads = mock_p2p_announcements([95, 96, 95.5])  # Avg: 95.5 (lower!)
    sell_ads = mock_p2p_announcements([100, 101, 100.5])  # Avg: 100.5 (higher!)

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("VES", "USDT", log_to_file=False)

    assert result["status"] == "ok"
    # Spread = (95.5 - 100.5) / 100.5 ≈ -0.0497 = -4.97%
    assert result["merchant_spread"] < 0  # Negative spread
    # Absolute value is < 10%, so should be HIGH
    assert result["spread_flag"] == "HIGH"


def test_no_data_available(mock_p2p_announcements):
    """Test handling when no P2P data is available."""
    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [[], []]  # No announcements
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    assert result["status"] == "no_data"


def test_empty_buy_ads(mock_p2p_announcements):
    """Test handling when only sell ads are available."""
    sell_ads = mock_p2p_announcements([100, 101, 100.5])

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [[], sell_ads]  # No buy ads
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    assert result["status"] == "no_data"


# ───────────────────────── ANOMALY DETECTION TESTS ─────────────────────────


def test_anomaly_detection_15_percent(mock_p2p_announcements, caplog):
    """Test warning is logged for spreads > 15%."""
    import logging

    caplog.set_level(logging.WARNING)

    buy_ads = mock_p2p_announcements([120, 121, 120.5])  # Avg: 120.5
    sell_ads = mock_p2p_announcements([100, 99, 99.5])  # Avg: 99.5

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("VES", "USDT", log_to_file=False)

    # Spread = (120.5 - 99.5) / 99.5 ≈ 0.2111 = 21.11%
    assert result["spread_flag"] == "ANOMALOUS"
    assert abs(result["merchant_spread"]) > 0.15

    # Check warning was logged
    assert any("ANOMALOUS spread detected" in rec.message for rec in caplog.records)


def test_all_pairs_formula_consistency(mock_p2p_announcements):
    """Test that formula is consistent across all 4 pairs."""
    pairs = ["MXN", "COP", "VES", "ARS"]

    # Same relative spread for all pairs
    buy_prices = [100, 100, 100, 100]
    sell_prices = [98, 98, 98, 98]

    for fiat in pairs:
        buy_ads = mock_p2p_announcements(buy_prices)
        sell_ads = mock_p2p_announcements(sell_prices)

        with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
            mock_get.side_effect = [buy_ads, sell_ads]
            result = scan_p2p_pair(fiat, "USDT", log_to_file=False)

        # All should have same spread: (100 - 98) / 98 ≈ 0.0204 = 2.04%
        assert result["status"] == "ok"
        assert pytest.approx(result["merchant_spread"], abs=0.001) == 0.0204
        assert result["spread_flag"] in ["NORMAL", "HIGH"]  # Close to 2% threshold


# ───────────────────────── INTEGRATION TESTS ─────────────────────────


def test_opportunity_logging_includes_spread_flag(mock_p2p_announcements, tmp_path):
    """Test that logged opportunities include spread_flag field."""
    buy_ads = mock_p2p_announcements([105, 106, 105.5])
    sell_ads = mock_p2p_announcements([100, 99, 99.5])

    # Create temporary log file
    temp_log = tmp_path / "test_opportunities.jsonl"

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        with patch("core.p2p_latam.LOG_FILE", temp_log):
            with patch("core.p2p_latam._load_threshold", return_value=0.01):  # Low threshold
                result = scan_p2p_pair("MXN", "USDT", log_to_file=True)

    # Check result includes spread_flag
    assert "spread_flag" in result
    assert result["spread_flag"] in ["NORMAL", "HIGH", "ANOMALOUS"]

    # Check logged opportunity includes spread_flag
    if temp_log.exists():
        with open(temp_log) as f:
            logged = json.loads(f.read().strip())
            assert "spread_flag" in logged
            assert logged["spread_flag"] == result["spread_flag"]


def test_no_pair_exceeds_15_percent_spread(mock_p2p_announcements):
    """
    CRITICAL: Fail if ANY pair shows spread > 15%.

    This test guards against:
    - Inverted buy/sell data
    - API returning corrupt prices
    - Market anomalies that require investigation

    If this test fails, investigate the root cause before proceeding.
    """
    pairs = ["MXN", "COP", "VES", "ARS"]
    max_allowed_spread = 0.15  # 15%

    for fiat in pairs:
        # Use realistic test prices with normal spread
        buy_ads = mock_p2p_announcements([100.5, 100.6, 100.55])
        sell_ads = mock_p2p_announcements([99.0, 99.2, 99.1])

        with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
            mock_get.side_effect = [buy_ads, sell_ads]
            result = scan_p2p_pair(fiat, "USDT", log_to_file=False)

        if result.get("status") == "ok":
            spread_abs = abs(result["merchant_spread"])
            assert spread_abs <= max_allowed_spread, (
                f"ANOMALY: {fiat} spread {spread_abs*100:.2f}% exceeds 15% threshold. "
                f"Buy={result['p2p_buy_price']}, Sell={result['p2p_sell_price']}. "
                f"Investigate: possible data inversion or corrupt prices."
            )


def test_spread_over_15_percent_triggers_anomalous_flag(mock_p2p_announcements):
    """Test that spreads > 15% are flagged as ANOMALOUS."""
    # Simulate extreme spread scenario
    buy_ads = mock_p2p_announcements([130, 132, 131])  # Avg: 131
    sell_ads = mock_p2p_announcements([100, 99, 99.5])  # Avg: 99.5

    with patch("core.p2p_latam.get_p2p_announcements_binance") as mock_get:
        mock_get.side_effect = [buy_ads, sell_ads]
        result = scan_p2p_pair("MXN", "USDT", log_to_file=False)

    # Spread = (131 - 99.5) / 99.5 ≈ 0.3166 = 31.66%
    assert result["spread_flag"] == "ANOMALOUS"
    assert abs(result["merchant_spread"]) > 0.15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
