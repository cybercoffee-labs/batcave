"""
Tests for Scanner G: P2P Merchant Spread Scanner

Mocks all HTTP calls for isolated testing.
"""

import json
from unittest.mock import patch, MagicMock

from core.scanner_p2p_merchant import (
    parse_ads,
    calculate_merchant_spread,
    analyze_fiat,
    scan_merchant_spread,
    fetch_p2p_ads,
    _load_threshold,
    SCANNER_ID,
    FIATS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock data
# ─────────────────────────────────────────────────────────────────────────────

MOCK_BUY_ADS_RAW = [
    {
        "adv": {
            "price": "17.50",
            "tradableQuantity": "5000",
            "minSingleTransAmount": "100",
            "dynamicMaxSingleTransAmount": "2000",
        },
        "advertiser": {
            "nickName": "Merchant1",
            "monthOrderCount": 150,
            "monthFinishRate": "0.98",
        },
    },
    {
        "adv": {
            "price": "17.55",
            "tradableQuantity": "3000",
            "minSingleTransAmount": "50",
            "dynamicMaxSingleTransAmount": "1500",
        },
        "advertiser": {
            "nickName": "Merchant2",
            "monthOrderCount": 80,
            "monthFinishRate": "0.95",
        },
    },
]

MOCK_SELL_ADS_RAW = [
    {
        "adv": {
            "price": "17.65",
            "tradableQuantity": "4000",
            "minSingleTransAmount": "100",
            "dynamicMaxSingleTransAmount": "2500",
        },
        "advertiser": {
            "nickName": "Seller1",
            "monthOrderCount": 200,
            "monthFinishRate": "0.99",
        },
    },
    {
        "adv": {
            "price": "17.60",
            "tradableQuantity": "2500",
            "minSingleTransAmount": "50",
            "dynamicMaxSingleTransAmount": "1000",
        },
        "advertiser": {
            "nickName": "Seller2",
            "monthOrderCount": 120,
            "monthFinishRate": "0.96",
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Test parse_ads
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_ads_extracts_price():
    """Test price extraction from ads."""
    parsed = parse_ads(MOCK_BUY_ADS_RAW)
    assert len(parsed) == 2
    assert parsed[0]["price"] == 17.50
    assert parsed[1]["price"] == 17.55


def test_parse_ads_extracts_quantity():
    """Test quantity extraction."""
    parsed = parse_ads(MOCK_BUY_ADS_RAW)
    assert parsed[0]["available_usdt"] == 5000.0
    assert parsed[1]["available_usdt"] == 3000.0


def test_parse_ads_extracts_advertiser_info():
    """Test advertiser info extraction."""
    parsed = parse_ads(MOCK_BUY_ADS_RAW)
    assert parsed[0]["nick_name"] == "Merchant1"
    assert parsed[0]["monthly_orders"] == 150
    assert parsed[0]["completion_rate"] == 98.0


def test_parse_ads_empty_list():
    """Test handling empty ad list."""
    parsed = parse_ads([])
    assert parsed == []


# ─────────────────────────────────────────────────────────────────────────────
# Test calculate_merchant_spread
# ─────────────────────────────────────────────────────────────────────────────


def test_calculate_spread_positive():
    """Test spread calculation with positive merchant margin."""
    buy_ads = [{"price": 17.50, "available_usdt": 5000}]
    sell_ads = [{"price": 17.65, "available_usdt": 4000}]

    result = calculate_merchant_spread(buy_ads, sell_ads)

    assert result["status"] == "ok"
    assert result["best_buy_price"] == 17.50
    assert result["best_sell_price"] == 17.65
    assert result["merchant_spread"] == 0.15
    # Spread % = 0.15 / 17.50 * 100 = 0.857%
    assert abs(result["merchant_spread_pct"] - 0.8571) < 0.01


def test_calculate_spread_negative():
    """Test spread when sell price < buy price (negative margin)."""
    buy_ads = [{"price": 17.65, "available_usdt": 5000}]
    sell_ads = [{"price": 17.50, "available_usdt": 4000}]

    result = calculate_merchant_spread(buy_ads, sell_ads)

    assert result["status"] == "ok"
    assert result["merchant_spread"] < 0
    assert result["merchant_spread_pct"] < 0


def test_calculate_spread_missing_buy_ads():
    """Test handling missing buy ads."""
    result = calculate_merchant_spread([], [{"price": 17.65}])
    assert result["status"] == "insufficient_data"


def test_calculate_spread_missing_sell_ads():
    """Test handling missing sell ads."""
    result = calculate_merchant_spread([{"price": 17.50}], [])
    assert result["status"] == "insufficient_data"


def test_calculate_spread_zero_price():
    """Test handling zero buy price."""
    buy_ads = [{"price": 0, "available_usdt": 5000}]
    sell_ads = [{"price": 17.65, "available_usdt": 4000}]

    result = calculate_merchant_spread(buy_ads, sell_ads)
    assert result["status"] == "invalid_price"


def test_calculate_spread_depth():
    """Test depth calculation."""
    buy_ads = [
        {"price": 17.50, "available_usdt": 5000},
        {"price": 17.55, "available_usdt": 3000},
    ]
    sell_ads = [
        {"price": 17.65, "available_usdt": 4000},
        {"price": 17.60, "available_usdt": 2500},
    ]

    result = calculate_merchant_spread(buy_ads, sell_ads)

    assert result["depth_buy_usd"] == 8000.0
    assert result["depth_sell_usd"] == 6500.0


def test_calculate_spread_finds_best_prices():
    """Test finds lowest buy and highest sell."""
    buy_ads = [
        {"price": 17.55, "available_usdt": 3000},
        {"price": 17.50, "available_usdt": 5000},  # Best buy
        {"price": 17.60, "available_usdt": 2000},
    ]
    sell_ads = [
        {"price": 17.60, "available_usdt": 4000},
        {"price": 17.70, "available_usdt": 2500},  # Best sell
        {"price": 17.65, "available_usdt": 1500},
    ]

    result = calculate_merchant_spread(buy_ads, sell_ads)

    assert result["best_buy_price"] == 17.50
    assert result["best_sell_price"] == 17.70


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_p2p_ads (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_p2p_merchant.urllib.request.urlopen")
def test_fetch_p2p_ads_success(mock_urlopen):
    """Test successful ad fetch."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"data": MOCK_BUY_ADS_RAW}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock()
    mock_urlopen.return_value = mock_response

    result = fetch_p2p_ads("MXN", "BUY")

    assert result is not None
    assert len(result) == 2


@patch("core.scanner_p2p_merchant.urllib.request.urlopen")
def test_fetch_p2p_ads_timeout(mock_urlopen):
    """Test handling timeout error."""
    mock_urlopen.side_effect = TimeoutError("Connection timed out")

    result = fetch_p2p_ads("MXN", "BUY")

    assert result is None


@patch("core.scanner_p2p_merchant.urllib.request.urlopen")
def test_fetch_p2p_ads_invalid_json(mock_urlopen):
    """Test handling invalid JSON response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"invalid json"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock()
    mock_urlopen.return_value = mock_response

    result = fetch_p2p_ads("MXN", "BUY")

    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Test analyze_fiat (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_p2p_merchant.fetch_p2p_ads")
def test_analyze_fiat_success(mock_fetch):
    """Test analyzing a fiat currency."""
    mock_fetch.side_effect = [MOCK_BUY_ADS_RAW, MOCK_SELL_ADS_RAW]

    result = analyze_fiat("MXN")

    assert result["fiat"] == "MXN"
    assert result["status"] == "ok"
    assert "best_buy_price" in result
    assert "merchant_spread_pct" in result


@patch("core.scanner_p2p_merchant.fetch_p2p_ads")
def test_analyze_fiat_fetch_error(mock_fetch):
    """Test handling fetch error."""
    mock_fetch.return_value = None

    result = analyze_fiat("MXN")

    assert result["status"] == "fetch_error"


# ─────────────────────────────────────────────────────────────────────────────
# Test scan_merchant_spread (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_p2p_merchant._append_to_log")
@patch("core.scanner_p2p_merchant.analyze_fiat")
def test_scan_merchant_spread_logs_opportunities(mock_analyze, mock_log):
    """Test scan logs opportunities when spread exceeds threshold."""
    mock_analyze.return_value = {
        "fiat": "MXN",
        "status": "ok",
        "best_buy_price": 17.50,
        "best_sell_price": 17.65,
        "merchant_spread_pct": 0.86,
        "num_buy_ads": 5,
        "num_sell_ads": 5,
        "depth_buy_usd": 8000.0,
        "depth_sell_usd": 6500.0,
    }
    mock_log.return_value = True

    result = scan_merchant_spread(log_to_file=True)

    assert len(result) == 2  # MXN and ARS both pass
    mock_log.assert_called()


@patch("core.scanner_p2p_merchant._append_to_log")
@patch("core.scanner_p2p_merchant.analyze_fiat")
def test_scan_merchant_spread_opportunity_format(mock_analyze, mock_log):
    """Test opportunity output format."""
    mock_analyze.return_value = {
        "fiat": "MXN",
        "status": "ok",
        "best_buy_price": 17.50,
        "best_sell_price": 17.65,
        "merchant_spread_pct": 0.86,
        "num_buy_ads": 5,
        "num_sell_ads": 5,
        "depth_buy_usd": 8000.0,
        "depth_sell_usd": 6500.0,
    }
    mock_log.return_value = True

    result = scan_merchant_spread(log_to_file=False)

    opp = result[0]
    assert opp["type"] == "G"
    assert opp["scanner_id"] == SCANNER_ID
    assert opp["opp_id"].startswith("OPP-G-")
    assert "ts" in opp
    assert "fiat" in opp
    assert "merchant_spread_pct" in opp
    assert opp["observe_only"] is True


@patch("core.scanner_p2p_merchant.analyze_fiat")
def test_scan_merchant_spread_below_threshold(mock_analyze):
    """Test no opportunities below threshold."""
    mock_analyze.return_value = {
        "fiat": "MXN",
        "status": "ok",
        "best_buy_price": 17.50,
        "best_sell_price": 17.51,
        "merchant_spread_pct": 0.05,  # Below 0.5% threshold
        "num_buy_ads": 5,
        "num_sell_ads": 5,
        "depth_buy_usd": 8000.0,
        "depth_sell_usd": 6500.0,
    }

    result = scan_merchant_spread(log_to_file=False)

    assert len(result) == 0


@patch("core.scanner_p2p_merchant.analyze_fiat")
def test_scan_merchant_spread_returns_list(mock_analyze):
    """Test scan always returns a list."""
    mock_analyze.return_value = {
        "fiat": "MXN",
        "status": "error",
        "error": "Test error",
    }

    result = scan_merchant_spread(log_to_file=False)

    assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# Test _load_threshold
# ─────────────────────────────────────────────────────────────────────────────


def test_load_threshold_default():
    """Test default threshold when config not available."""
    with patch("core.scanner_p2p_merchant.CONFIG_FILE") as mock_path:
        mock_path.exists.return_value = False
        result = _load_threshold()
        assert result == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Test constants
# ─────────────────────────────────────────────────────────────────────────────


def test_scanner_id_format():
    """Test scanner ID follows convention."""
    assert SCANNER_ID == "G-P2P-MERCHANT"


def test_fiats_list():
    """Test expected fiats are included."""
    assert "MXN" in FIATS
    assert "ARS" in FIATS
