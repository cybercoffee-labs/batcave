"""
Tests for OKX Exchange Connector

All HTTP calls are mocked - no real network requests.
"""

from unittest.mock import patch
from core.exchange_okx import (
    fetch_okx_price,
    fetch_okx_funding_rate,
    fetch_all_okx_prices,
    fetch_all_okx_funding_rates,
    _normalize_pair,
    SUPPORTED_PAIRS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Response Helpers
# ─────────────────────────────────────────────────────────────────────────────


def mock_ticker_response(pair: str):
    """Create a mock OKX ticker API response."""
    prices = {
        "BTC-USDT": {
            "last": "84500.00",
            "bidPx": "84490.00",
            "askPx": "84510.00",
            "vol24h": "15000.5",
            "volCcy24h": "1267542500.00",
            "high24h": "85000.00",
            "low24h": "83000.00",
            "open24h": "84000.00",
        },
        "ETH-USDT": {
            "last": "3200.00",
            "bidPx": "3199.00",
            "askPx": "3201.00",
            "vol24h": "120000.25",
            "volCcy24h": "384000800.00",
            "high24h": "3300.00",
            "low24h": "3100.00",
            "open24h": "3150.00",
        },
        "SOL-USDT": {
            "last": "145.00",
            "bidPx": "144.90",
            "askPx": "145.10",
            "vol24h": "500000.00",
            "volCcy24h": "72500000.00",
            "high24h": "150.00",
            "low24h": "140.00",
            "open24h": "142.00",
        },
    }
    return {"code": "0", "msg": "", "data": [prices.get(pair, prices["BTC-USDT"])]}


def mock_funding_rate_response(pair: str):
    """Create a mock OKX funding rate API response."""
    return {
        "code": "0",
        "msg": "",
        "data": [
            {
                "fundingRate": "0.0001",
                "nextFundingTime": "1710691200000",  # Mock timestamp
                "instId": f"{pair}-SWAP",
            }
        ],
    }


def mock_error_response():
    """Create a mock OKX error response."""
    return {"code": "51000", "msg": "Parameter instId error"}


# ─────────────────────────────────────────────────────────────────────────────
# Test _normalize_pair
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_pair_already_formatted():
    """Test that already formatted pairs pass through."""
    assert _normalize_pair("BTC-USDT") == "BTC-USDT"
    assert _normalize_pair("ETH-USDT") == "ETH-USDT"


def test_normalize_pair_no_hyphen():
    """Test conversion from BTCUSDT to BTC-USDT format."""
    assert _normalize_pair("BTCUSDT") == "BTC-USDT"
    assert _normalize_pair("ETHUSDT") == "ETH-USDT"
    assert _normalize_pair("SOLUSDT") == "SOL-USDT"


def test_normalize_pair_lowercase():
    """Test that lowercase pairs are uppercased."""
    assert _normalize_pair("btc-usdt") == "BTC-USDT"
    assert _normalize_pair("ethusdt") == "ETH-USDT"


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_okx_price
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_price_success(mock_fetch):
    """Test successful price fetch for BTC-USDT."""
    mock_fetch.return_value = mock_ticker_response("BTC-USDT")

    result = fetch_okx_price("BTC-USDT")

    assert result["status"] == "ok"
    assert result["pair"] == "BTC-USDT"
    assert result["price"] == 84500.00
    assert result["bid"] == 84490.00
    assert result["ask"] == 84510.00
    assert result["exchange"] == "okx"
    assert "ts" in result


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_price_eth(mock_fetch):
    """Test successful price fetch for ETH-USDT."""
    mock_fetch.return_value = mock_ticker_response("ETH-USDT")

    result = fetch_okx_price("ETH-USDT")

    assert result["status"] == "ok"
    assert result["price"] == 3200.00
    assert result["bid"] == 3199.00
    assert result["ask"] == 3201.00


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_price_api_failure(mock_fetch):
    """Test handling of API failure (None response)."""
    mock_fetch.return_value = None

    result = fetch_okx_price("BTC-USDT")

    assert result["status"] == "error"
    assert "Failed to fetch" in result["error"]


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_price_api_error_response(mock_fetch):
    """Test handling of OKX API error response."""
    mock_fetch.return_value = mock_error_response()

    result = fetch_okx_price("BTC-USDT")

    assert result["status"] == "error"
    assert "Parameter" in result["error"]


def test_fetch_okx_price_unsupported_pair():
    """Test handling of unsupported trading pair."""
    result = fetch_okx_price("DOGE-USDT")

    assert result["status"] == "error"
    assert "Unsupported pair" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_okx_funding_rate
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_funding_rate_success(mock_fetch):
    """Test successful funding rate fetch."""
    mock_fetch.return_value = mock_funding_rate_response("BTC-USDT")

    result = fetch_okx_funding_rate("BTC-USDT")

    assert result["status"] == "ok"
    assert result["pair"] == "BTC-USDT"
    assert result["funding_rate"] == 0.0001
    assert result["funding_rate_pct"] == 0.01
    assert result["annualized_pct"] > 0
    assert result["exchange"] == "okx"
    assert "next_funding_time" in result


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_funding_rate_annualization(mock_fetch):
    """Test that funding rate is correctly annualized."""
    mock_fetch.return_value = mock_funding_rate_response("BTC-USDT")

    result = fetch_okx_funding_rate("BTC-USDT")

    # 0.0001 * 3 * 365 * 100 = 10.95%
    expected_annualized = 0.0001 * 3 * 365 * 100
    assert abs(result["annualized_pct"] - expected_annualized) < 0.01


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_funding_rate_api_failure(mock_fetch):
    """Test handling of funding rate API failure."""
    mock_fetch.return_value = None

    result = fetch_okx_funding_rate("BTC-USDT")

    assert result["status"] == "error"
    assert "Failed to fetch" in result["error"]


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_funding_rate_api_error(mock_fetch):
    """Test handling of OKX API error for funding rate."""
    mock_fetch.return_value = mock_error_response()

    result = fetch_okx_funding_rate("BTC-USDT")

    assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all functions
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_okx._fetch_json")
def test_fetch_all_okx_prices_returns_all_pairs(mock_fetch):
    """Test that fetch_all_okx_prices returns data for all supported pairs."""

    def side_effect(url, params=None):
        pair = params.get("instId", "BTC-USDT") if params else "BTC-USDT"
        return mock_ticker_response(pair)

    mock_fetch.side_effect = side_effect

    results = fetch_all_okx_prices()

    assert len(results) == len(SUPPORTED_PAIRS)
    for pair in SUPPORTED_PAIRS:
        assert pair in results
        assert results[pair]["status"] == "ok"


@patch("core.exchange_okx._fetch_json")
def test_fetch_all_okx_funding_rates_returns_all_pairs(mock_fetch):
    """Test that fetch_all_okx_funding_rates returns data for all supported pairs."""

    def side_effect(url, params=None):
        inst_id = params.get("instId", "BTC-USDT-SWAP") if params else "BTC-USDT-SWAP"
        pair = inst_id.replace("-SWAP", "")
        return mock_funding_rate_response(pair)

    mock_fetch.side_effect = side_effect

    results = fetch_all_okx_funding_rates()

    assert len(results) == len(SUPPORTED_PAIRS)
    for pair in SUPPORTED_PAIRS:
        assert pair in results


# ─────────────────────────────────────────────────────────────────────────────
# Test pair format conversion
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_okx._fetch_json")
def test_fetch_okx_price_accepts_different_formats(mock_fetch):
    """Test that different pair formats are accepted and normalized."""
    mock_fetch.return_value = mock_ticker_response("BTC-USDT")

    # Test with hyphen
    result1 = fetch_okx_price("BTC-USDT")
    assert result1["status"] == "ok"
    assert result1["pair"] == "BTC-USDT"

    # Test without hyphen
    result2 = fetch_okx_price("BTCUSDT")
    assert result2["status"] == "ok"
    assert result2["pair"] == "BTC-USDT"

    # Test lowercase
    result3 = fetch_okx_price("btc-usdt")
    assert result3["status"] == "ok"
    assert result3["pair"] == "BTC-USDT"
