"""
Tests for MEXC Exchange Connector

Mocks all HTTP calls for isolated testing.
"""

from unittest.mock import patch

from core.exchange_mexc import (
    fetch_mexc_price,
    fetch_mexc_ticker,
    fetch_all_mexc_prices,
    PAIRS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_mexc_price
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_mexc._fetch_json")
def test_fetch_mexc_price_success(mock_fetch):
    """Test successful price fetch with bid/ask."""
    mock_fetch.side_effect = [
        {"symbol": "BTCUSDT", "price": "65432.50"},
        {"symbol": "BTCUSDT", "bidPrice": "65430.00", "askPrice": "65435.00"},
    ]

    result = fetch_mexc_price("BTCUSDT")

    assert result is not None
    assert result["price"] == 65432.50
    assert result["bid"] == 65430.00
    assert result["ask"] == 65435.00
    assert "ts" in result


@patch("core.exchange_mexc._fetch_json")
def test_fetch_mexc_price_returns_none_on_failure(mock_fetch):
    """Test returns None on fetch failure."""
    mock_fetch.return_value = None

    result = fetch_mexc_price("BTCUSDT")

    assert result is None


@patch("core.exchange_mexc._fetch_json")
def test_fetch_mexc_price_without_book_data(mock_fetch):
    """Test price fetch when book data is unavailable."""
    mock_fetch.side_effect = [
        {"symbol": "BTCUSDT", "price": "65432.50"},
        None,  # Book data fails
    ]

    result = fetch_mexc_price("BTCUSDT")

    assert result is not None
    assert result["price"] == 65432.50
    # Falls back to using price for bid/ask
    assert result["bid"] == 65432.50
    assert result["ask"] == 65432.50


@patch("core.exchange_mexc._fetch_json")
def test_fetch_mexc_price_invalid_response(mock_fetch):
    """Test handling response without price field."""
    mock_fetch.return_value = {"symbol": "BTCUSDT"}  # No price

    result = fetch_mexc_price("BTCUSDT")

    assert result is None


@patch("core.exchange_mexc._fetch_json")
def test_fetch_mexc_price_includes_timestamp(mock_fetch):
    """Test timestamp is included in result."""
    mock_fetch.side_effect = [
        {"price": "3500.00"},
        {"bidPrice": "3499.00", "askPrice": "3501.00"},
    ]

    result = fetch_mexc_price("ETHUSDT")

    assert "ts" in result
    assert "T" in result["ts"]  # ISO format


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_mexc_ticker (alias)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_mexc._fetch_json")
def test_fetch_mexc_ticker_is_alias(mock_fetch):
    """Test ticker function is alias for price function."""
    mock_fetch.side_effect = [
        {"price": "150.00"},
        {"bidPrice": "149.00", "askPrice": "151.00"},
    ]

    result = fetch_mexc_ticker("SOLUSDT")

    assert result is not None
    assert result["price"] == 150.00


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all_mexc_prices
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_mexc.fetch_mexc_price")
def test_fetch_all_mexc_prices(mock_fetch):
    """Test fetching all prices."""
    mock_fetch.side_effect = [
        {"price": 65000, "bid": 64999, "ask": 65001},
        {"price": 3500, "bid": 3499, "ask": 3501},
        None,  # SOL fails
    ]

    result = fetch_all_mexc_prices()

    assert "BTCUSDT" in result
    assert "ETHUSDT" in result
    assert "SOLUSDT" not in result  # Failed


# ─────────────────────────────────────────────────────────────────────────────
# Test constants
# ─────────────────────────────────────────────────────────────────────────────


def test_pairs_list():
    """Test expected pairs are defined."""
    assert "BTCUSDT" in PAIRS
    assert "ETHUSDT" in PAIRS
    assert "SOLUSDT" in PAIRS
