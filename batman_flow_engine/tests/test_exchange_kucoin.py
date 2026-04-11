"""
Tests for KuCoin Exchange Connector

Mocks all HTTP calls for isolated testing.
"""

from unittest.mock import patch

from core.exchange_kucoin import (
    fetch_kucoin_price,
    fetch_kucoin_ticker,
    fetch_all_kucoin_prices,
    PAIRS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock response data
# ─────────────────────────────────────────────────────────────────────────────

MOCK_KUCOIN_RESPONSE = {
    "code": "200000",
    "data": {
        "sequence": "1234567890",
        "price": "65432.50",
        "size": "0.001",
        "bestBid": "65430.00",
        "bestAsk": "65435.00",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_kucoin_price
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_price_success(mock_fetch):
    """Test successful price fetch."""
    mock_fetch.return_value = MOCK_KUCOIN_RESPONSE

    result = fetch_kucoin_price("BTC-USDT")

    assert result is not None
    assert result["price"] == 65432.50
    assert result["bid"] == 65430.00
    assert result["ask"] == 65435.00
    assert "ts" in result


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_price_returns_none_on_failure(mock_fetch):
    """Test returns None on fetch failure."""
    mock_fetch.return_value = None

    result = fetch_kucoin_price("BTC-USDT")

    assert result is None


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_price_invalid_code(mock_fetch):
    """Test handling invalid response code."""
    mock_fetch.return_value = {"code": "400001", "msg": "Bad Request"}

    result = fetch_kucoin_price("BTC-USDT")

    assert result is None


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_price_empty_data(mock_fetch):
    """Test handling empty data field returns None."""
    mock_fetch.return_value = {"code": "200000", "data": {}}

    result = fetch_kucoin_price("BTC-USDT")

    # Empty data returns None (no valid prices)
    assert result is None


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_price_uses_mid_price_if_last_zero(mock_fetch):
    """Test calculates mid price when last price is missing."""
    mock_fetch.return_value = {
        "code": "200000",
        "data": {
            "price": "0",
            "bestBid": "100.00",
            "bestAsk": "100.10",
        },
    }

    result = fetch_kucoin_price("BTC-USDT")

    assert result is not None
    assert result["price"] == 100.05  # Mid price


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_price_includes_sequence(mock_fetch):
    """Test sequence number is included."""
    mock_fetch.return_value = MOCK_KUCOIN_RESPONSE

    result = fetch_kucoin_price("BTC-USDT")

    assert result["sequence"] == "1234567890"


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_kucoin_ticker (alias)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_kucoin._fetch_json")
def test_fetch_kucoin_ticker_is_alias(mock_fetch):
    """Test ticker function is alias for price function."""
    mock_fetch.return_value = MOCK_KUCOIN_RESPONSE

    result = fetch_kucoin_ticker("ETH-USDT")

    assert result is not None
    assert result["price"] == 65432.50


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all_kucoin_prices
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.exchange_kucoin.fetch_kucoin_price")
def test_fetch_all_kucoin_prices(mock_fetch):
    """Test fetching all prices."""
    mock_fetch.side_effect = [
        {"price": 65000, "bid": 64999, "ask": 65001},
        {"price": 3500, "bid": 3499, "ask": 3501},
        None,  # SOL fails
    ]

    result = fetch_all_kucoin_prices()

    assert "BTC-USDT" in result
    assert "ETH-USDT" in result
    assert "SOL-USDT" not in result  # Failed


# ─────────────────────────────────────────────────────────────────────────────
# Test constants
# ─────────────────────────────────────────────────────────────────────────────


def test_pairs_list():
    """Test expected pairs are defined."""
    assert "BTC-USDT" in PAIRS
    assert "ETH-USDT" in PAIRS
    assert "SOL-USDT" in PAIRS
