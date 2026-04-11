"""
Tests for Bybit Exchange Connector

All HTTP calls are mocked - no real network requests.
"""

from unittest.mock import patch
from core.exchange_bybit import (
    fetch_bybit_price,
    fetch_bybit_funding_rate,
    fetch_all_bybit_prices,
    fetch_all_bybit_funding_rates,
    _normalize_pair,
    SUPPORTED_PAIRS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Response Helpers
# ─────────────────────────────────────────────────────────────────────────────


def mock_ticker_response(pair: str):
    """Create a mock Bybit ticker API response."""
    prices = {
        "BTCUSDT": {
            "lastPrice": "84500.00",
            "bid1Price": "84490.00",
            "ask1Price": "84510.00",
            "volume24h": "15000.5",
            "turnover24h": "1267542500.00",
            "highPrice24h": "85000.00",
            "lowPrice24h": "83000.00",
            "price24hPcnt": "0.005",
        },
        "ETHUSDT": {
            "lastPrice": "3200.00",
            "bid1Price": "3199.00",
            "ask1Price": "3201.00",
            "volume24h": "120000.25",
            "turnover24h": "384000800.00",
            "highPrice24h": "3300.00",
            "lowPrice24h": "3100.00",
            "price24hPcnt": "0.015",
        },
        "SOLUSDT": {
            "lastPrice": "145.00",
            "bid1Price": "144.90",
            "ask1Price": "145.10",
            "volume24h": "500000.00",
            "turnover24h": "72500000.00",
            "highPrice24h": "150.00",
            "lowPrice24h": "140.00",
            "price24hPcnt": "0.02",
        },
    }
    return {"retCode": 0, "retMsg": "OK", "result": {"category": "spot", "list": [prices.get(pair, prices["BTCUSDT"])]}}


def mock_funding_rate_response(pair: str):
    """Create a mock Bybit funding rate API response."""
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [{"symbol": pair, "fundingRate": "0.0001", "fundingRateTimestamp": "1710691200000"}],
        },
    }


def mock_error_response():
    """Create a mock Bybit error response."""
    return {"retCode": 10001, "retMsg": "Invalid symbol"}


def mock_empty_response():
    """Create a mock Bybit empty list response."""
    return {"retCode": 0, "retMsg": "OK", "result": {"list": []}}


# ─────────────────────────────────────────────────────────────────────────────
# Test _normalize_pair
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_pair_already_formatted():
    """Test that already formatted pairs pass through."""
    assert _normalize_pair("BTCUSDT") == "BTCUSDT"
    assert _normalize_pair("ETHUSDT") == "ETHUSDT"


def test_normalize_pair_with_hyphen():
    """Test conversion from BTC-USDT to BTCUSDT format."""
    assert _normalize_pair("BTC-USDT") == "BTCUSDT"
    assert _normalize_pair("ETH-USDT") == "ETHUSDT"
    assert _normalize_pair("SOL-USDT") == "SOLUSDT"


def test_normalize_pair_lowercase():
    """Test that lowercase pairs are uppercased."""
    assert _normalize_pair("btcusdt") == "BTCUSDT"
    assert _normalize_pair("eth-usdt") == "ETHUSDT"


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_bybit_price
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_price_success(mock_fetch):
    """Test successful price fetch for BTCUSDT."""
    mock_fetch.return_value = mock_ticker_response("BTCUSDT")

    result = fetch_bybit_price("BTCUSDT")

    assert result["status"] == "ok"
    assert result["pair"] == "BTCUSDT"
    assert result["price"] == 84500.00
    assert result["bid"] == 84490.00
    assert result["ask"] == 84510.00
    assert result["exchange"] == "bybit"
    assert "ts" in result


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_price_eth(mock_fetch):
    """Test successful price fetch for ETHUSDT."""
    mock_fetch.return_value = mock_ticker_response("ETHUSDT")

    result = fetch_bybit_price("ETHUSDT")

    assert result["status"] == "ok"
    assert result["price"] == 3200.00
    assert result["bid"] == 3199.00
    assert result["ask"] == 3201.00


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_price_api_failure(mock_fetch):
    """Test handling of API failure (None response)."""
    mock_fetch.return_value = None

    result = fetch_bybit_price("BTCUSDT")

    assert result["status"] == "error"
    assert "Failed to fetch" in result["error"]


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_price_api_error_response(mock_fetch):
    """Test handling of Bybit API error response."""
    mock_fetch.return_value = mock_error_response()

    result = fetch_bybit_price("BTCUSDT")

    assert result["status"] == "error"
    assert "Invalid symbol" in result["error"]


def test_fetch_bybit_price_unsupported_pair():
    """Test handling of unsupported trading pair."""
    result = fetch_bybit_price("DOGEUSDT")

    assert result["status"] == "error"
    assert "Unsupported pair" in result["error"]


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_price_empty_list(mock_fetch):
    """Test handling of empty ticker list."""
    mock_fetch.return_value = mock_empty_response()

    result = fetch_bybit_price("BTCUSDT")

    assert result["status"] == "error"
    assert "No ticker data" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_bybit_funding_rate
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_funding_rate_success(mock_fetch):
    """Test successful funding rate fetch."""
    mock_fetch.return_value = mock_funding_rate_response("BTCUSDT")

    result = fetch_bybit_funding_rate("BTCUSDT")

    assert result["status"] == "ok"
    assert result["pair"] == "BTCUSDT"
    assert result["funding_rate"] == 0.0001
    assert result["funding_rate_pct"] == 0.01
    assert result["annualized_pct"] > 0
    assert result["exchange"] == "bybit"
    assert "funding_time" in result


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_funding_rate_annualization(mock_fetch):
    """Test that funding rate is correctly annualized."""
    mock_fetch.return_value = mock_funding_rate_response("BTCUSDT")

    result = fetch_bybit_funding_rate("BTCUSDT")

    # 0.0001 * 3 * 365 * 100 = 10.95%
    expected_annualized = 0.0001 * 3 * 365 * 100
    assert abs(result["annualized_pct"] - expected_annualized) < 0.01


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_funding_rate_api_failure(mock_fetch):
    """Test handling of funding rate API failure."""
    mock_fetch.return_value = None

    result = fetch_bybit_funding_rate("BTCUSDT")

    assert result["status"] == "error"
    assert "Failed to fetch" in result["error"]


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_funding_rate_api_error(mock_fetch):
    """Test handling of Bybit API error for funding rate."""
    mock_fetch.return_value = mock_error_response()

    result = fetch_bybit_funding_rate("BTCUSDT")

    assert result["status"] == "error"


def test_fetch_bybit_funding_rate_unsupported_pair():
    """Test handling of unsupported pair for funding rate."""
    result = fetch_bybit_funding_rate("INVALID")

    assert result["status"] == "error"
    assert "Unsupported pair" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all functions
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bybit._fetch_json")
def test_fetch_all_bybit_prices_returns_all_pairs(mock_fetch):
    """Test that fetch_all_bybit_prices returns data for all supported pairs."""

    def side_effect(url, params=None):
        pair = params.get("symbol", "BTCUSDT") if params else "BTCUSDT"
        return mock_ticker_response(pair)

    mock_fetch.side_effect = side_effect

    results = fetch_all_bybit_prices()

    assert len(results) == len(SUPPORTED_PAIRS)
    for pair in SUPPORTED_PAIRS:
        assert pair in results
        assert results[pair]["status"] == "ok"


@patch("core.exchange_bybit._fetch_json")
def test_fetch_all_bybit_funding_rates_returns_all_pairs(mock_fetch):
    """Test that fetch_all_bybit_funding_rates returns data for all supported pairs."""

    def side_effect(url, params=None):
        pair = params.get("symbol", "BTCUSDT") if params else "BTCUSDT"
        return mock_funding_rate_response(pair)

    mock_fetch.side_effect = side_effect

    results = fetch_all_bybit_funding_rates()

    assert len(results) == len(SUPPORTED_PAIRS)
    for pair in SUPPORTED_PAIRS:
        assert pair in results


# ─────────────────────────────────────────────────────────────────────────────
# Test pair format conversion
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bybit._fetch_json")
def test_fetch_bybit_price_accepts_different_formats(mock_fetch):
    """Test that different pair formats are accepted and normalized."""
    mock_fetch.return_value = mock_ticker_response("BTCUSDT")

    # Test without hyphen
    result1 = fetch_bybit_price("BTCUSDT")
    assert result1["status"] == "ok"
    assert result1["pair"] == "BTCUSDT"

    # Test with hyphen
    result2 = fetch_bybit_price("BTC-USDT")
    assert result2["status"] == "ok"
    assert result2["pair"] == "BTCUSDT"

    # Test lowercase
    result3 = fetch_bybit_price("btcusdt")
    assert result3["status"] == "ok"
    assert result3["pair"] == "BTCUSDT"
