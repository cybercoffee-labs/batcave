"""
Tests for Bitso Exchange Connector

All HTTP calls are mocked - no real network requests.
"""

from unittest.mock import patch
from core.exchange_bitso import (
    fetch_bitso_price,
    fetch_bitso_order_book,
    fetch_all_bitso_prices,
    SUPPORTED_PAIRS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Response Helpers
# ─────────────────────────────────────────────────────────────────────────────


def mock_ticker_response(pair: str):
    """Create a mock Bitso ticker API response."""
    prices = {
        "btc_mxn": {
            "last": "1450000.00",
            "bid": "1449500.00",
            "ask": "1450500.00",
            "volume": "15.5",
            "high": "1460000.00",
            "low": "1440000.00",
            "vwap": "1450100.00",
        },
        "eth_mxn": {
            "last": "52000.00",
            "bid": "51900.00",
            "ask": "52100.00",
            "volume": "100.25",
            "high": "53000.00",
            "low": "51000.00",
            "vwap": "52050.00",
        },
        "usdt_mxn": {
            "last": "17.50",
            "bid": "17.48",
            "ask": "17.52",
            "volume": "500000.00",
            "high": "17.60",
            "low": "17.40",
            "vwap": "17.50",
        },
    }
    return {"success": True, "payload": prices.get(pair, prices["usdt_mxn"])}


def mock_order_book_response(pair: str):
    """Create a mock Bitso order book API response."""
    return {
        "success": True,
        "payload": {
            "bids": [
                {"price": "17.48", "amount": "10000.00"},
                {"price": "17.47", "amount": "15000.00"},
                {"price": "17.46", "amount": "20000.00"},
                {"price": "17.45", "amount": "25000.00"},
                {"price": "17.44", "amount": "30000.00"},
            ],
            "asks": [
                {"price": "17.52", "amount": "8000.00"},
                {"price": "17.53", "amount": "12000.00"},
                {"price": "17.54", "amount": "18000.00"},
                {"price": "17.55", "amount": "22000.00"},
                {"price": "17.56", "amount": "28000.00"},
            ],
        },
    }


def mock_error_response():
    """Create a mock Bitso error response."""
    return {"success": False, "error": {"code": "0201", "message": "Invalid book"}}


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_bitso_price
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_price_success(mock_fetch):
    """Test successful price fetch for USDT/MXN."""
    mock_fetch.return_value = mock_ticker_response("usdt_mxn")

    result = fetch_bitso_price("usdt_mxn")

    assert result["status"] == "ok"
    assert result["pair"] == "usdt_mxn"
    assert result["price"] == 17.50
    assert result["bid"] == 17.48
    assert result["ask"] == 17.52
    assert result["volume_24h"] == 500000.00
    assert result["exchange"] == "bitso"
    assert "ts" in result


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_price_btc(mock_fetch):
    """Test successful price fetch for BTC/MXN."""
    mock_fetch.return_value = mock_ticker_response("btc_mxn")

    result = fetch_bitso_price("btc_mxn")

    assert result["status"] == "ok"
    assert result["price"] == 1450000.00
    assert result["bid"] == 1449500.00
    assert result["ask"] == 1450500.00


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_price_api_failure(mock_fetch):
    """Test handling of API failure (None response)."""
    mock_fetch.return_value = None

    result = fetch_bitso_price("usdt_mxn")

    assert result["status"] == "error"
    assert "Failed to fetch" in result["error"]
    assert result["pair"] == "usdt_mxn"


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_price_api_error_response(mock_fetch):
    """Test handling of Bitso API error response."""
    mock_fetch.return_value = mock_error_response()

    result = fetch_bitso_price("usdt_mxn")

    assert result["status"] == "error"
    assert "Invalid book" in result["error"]


def test_fetch_bitso_price_unsupported_pair():
    """Test handling of unsupported trading pair."""
    result = fetch_bitso_price("doge_mxn")

    assert result["status"] == "error"
    assert "Unsupported pair" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_bitso_order_book
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_order_book_success(mock_fetch):
    """Test successful order book fetch."""
    mock_fetch.return_value = mock_order_book_response("usdt_mxn")

    result = fetch_bitso_order_book("usdt_mxn", limit=5)

    assert result["status"] == "ok"
    assert result["pair"] == "usdt_mxn"
    assert len(result["bids"]) == 5
    assert len(result["asks"]) == 5
    assert result["best_bid"] == 17.48
    assert result["best_ask"] == 17.52
    assert result["spread_pct"] > 0
    assert result["exchange"] == "bitso"


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_order_book_calculates_depth(mock_fetch):
    """Test that order book correctly calculates depth."""
    mock_fetch.return_value = mock_order_book_response("usdt_mxn")

    result = fetch_bitso_order_book("usdt_mxn", limit=5)

    # Sum of mock bid amounts: 10000 + 15000 + 20000 + 25000 + 30000 = 100000
    assert result["bid_depth"] == 100000.0
    # Sum of mock ask amounts: 8000 + 12000 + 18000 + 22000 + 28000 = 88000
    assert result["ask_depth"] == 88000.0


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_order_book_api_failure(mock_fetch):
    """Test handling of order book API failure."""
    mock_fetch.return_value = None

    result = fetch_bitso_order_book("usdt_mxn")

    assert result["status"] == "error"
    assert "Failed to fetch" in result["error"]


def test_fetch_bitso_order_book_unsupported_pair():
    """Test handling of unsupported pair for order book."""
    result = fetch_bitso_order_book("invalid_pair")

    assert result["status"] == "error"
    assert "Unsupported pair" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all_bitso_prices
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bitso._fetch_json")
def test_fetch_all_bitso_prices_returns_all_pairs(mock_fetch):
    """Test that fetch_all_bitso_prices returns data for all supported pairs."""

    def side_effect(url, params=None):
        pair = params.get("book", "usdt_mxn") if params else "usdt_mxn"
        return mock_ticker_response(pair)

    mock_fetch.side_effect = side_effect

    results = fetch_all_bitso_prices()

    assert len(results) == len(SUPPORTED_PAIRS)
    for pair in SUPPORTED_PAIRS:
        assert pair in results
        assert results[pair]["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Test spread calculation
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bitso._fetch_json")
def test_order_book_spread_calculation(mock_fetch):
    """Test that spread percentage is calculated correctly."""
    mock_fetch.return_value = mock_order_book_response("usdt_mxn")

    result = fetch_bitso_order_book("usdt_mxn")

    # Spread = (17.52 - 17.48) / 17.48 * 100 = 0.2288%
    expected_spread = (17.52 - 17.48) / 17.48 * 100
    assert abs(result["spread_pct"] - expected_spread) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Test case insensitivity
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_bitso._fetch_json")
def test_fetch_bitso_price_case_insensitive(mock_fetch):
    """Test that pair names are case insensitive."""
    mock_fetch.return_value = mock_ticker_response("usdt_mxn")

    result_lower = fetch_bitso_price("usdt_mxn")
    result_upper = fetch_bitso_price("USDT_MXN")

    assert result_lower["status"] == "ok"
    assert result_upper["status"] == "ok"
