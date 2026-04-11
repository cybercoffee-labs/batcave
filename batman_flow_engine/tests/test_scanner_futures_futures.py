"""Tests for Scanner K: Futures vs Futures"""

from unittest.mock import patch


def test_scanner_k_imports():
    """Scanner K modules import correctly."""
    from core.scanner_futures_futures import (
        scan_futures_futures,
    )

    assert callable(scan_futures_futures)


def test_scanner_k_assets():
    """Scanner K should have 10 assets configured."""
    from core.scanner_futures_futures import ASSETS

    assert len(ASSETS) == 10
    for asset in ASSETS:
        assert "asset" in asset
        assert "binance" in asset
        assert "okx" in asset
        assert "bybit" in asset


def test_scanner_k_fees():
    """All exchanges should have futures fees defined."""
    from core.scanner_futures_futures import FEES

    assert "binance" in FEES
    assert "okx" in FEES
    assert "bybit" in FEES
    for fee in FEES.values():
        assert 0 < fee < 1.0


def test_scanner_k_handles_no_data():
    """Scanner should handle API failures gracefully."""
    from core.scanner_futures_futures import scan_futures_futures

    with patch("core.scanner_futures_futures._fetch_json", return_value=None):
        results = scan_futures_futures(log_to_file=False)
        assert isinstance(results, list)
        assert len(results) == 0


def test_fetch_binance_futures_parses_response():
    """Binance futures fetcher should parse bookTicker response."""
    from core.scanner_futures_futures import _fetch_binance_futures

    mock_ticker = {"bidPrice": "69500.00", "askPrice": "69510.00"}
    mock_funding = {"lastFundingRate": "0.0001"}

    def side_effect(url, params=None):
        if "bookTicker" in url:
            return mock_ticker
        if "premiumIndex" in url:
            return mock_funding
        return None

    with patch("core.scanner_futures_futures._fetch_json", side_effect=side_effect):
        result = _fetch_binance_futures("BTCUSDT")
        assert result is not None
        assert result["bid"] == 69500.0
        assert result["ask"] == 69510.0
        assert result["funding_rate"] == 0.0001


def test_fetch_okx_futures_parses_response():
    """OKX futures fetcher should parse ticker + funding rate."""
    from core.scanner_futures_futures import _fetch_okx_futures

    mock_ticker = {"code": "0", "data": [{"bidPx": "69500", "askPx": "69510", "last": "69505"}]}
    mock_funding = {"code": "0", "data": [{"fundingRate": "0.00015"}]}

    def side_effect(url, params=None):
        if "ticker" in url:
            return mock_ticker
        if "funding-rate" in url:
            return mock_funding
        return None

    with patch("core.scanner_futures_futures._fetch_json", side_effect=side_effect):
        result = _fetch_okx_futures("BTC-USDT-SWAP")
        assert result is not None
        assert result["bid"] == 69500.0
        assert result["funding_rate"] == 0.00015


def test_fetch_bybit_futures_parses_response():
    """Bybit futures fetcher should parse linear ticker."""
    from core.scanner_futures_futures import _fetch_bybit_futures

    mock_data = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "bid1Price": "69500",
                    "ask1Price": "69510",
                    "lastPrice": "69505",
                    "fundingRate": "0.0002",
                }
            ]
        },
    }

    with patch("core.scanner_futures_futures._fetch_json", return_value=mock_data):
        result = _fetch_bybit_futures("BTCUSDT")
        assert result is not None
        assert result["bid"] == 69500.0
        assert result["funding_rate"] == 0.0002


def test_scanner_k_detects_spread():
    """Scanner should detect spread between exchanges."""
    from core.scanner_futures_futures import scan_futures_futures

    def mock_fetcher(url, params=None):
        if "fapi.binance" in url:
            if "bookTicker" in url:
                return {"bidPrice": "69500.00", "askPrice": "69510.00"}
            return {"lastFundingRate": "0.0001"}
        if "okx.com" in url:
            if "ticker" in url:
                return {"code": "0", "data": [{"bidPx": "69600", "askPx": "69610", "last": "69605"}]}
            return {"code": "0", "data": [{"fundingRate": "0.0002"}]}
        if "bybit.com" in url:
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        {"bid1Price": "69550", "ask1Price": "69560", "lastPrice": "69555", "fundingRate": "0.00015"}
                    ]
                },
            }
        return None

    with patch("core.scanner_futures_futures._fetch_json", side_effect=mock_fetcher):
        results = scan_futures_futures(log_to_file=False)
        assert isinstance(results, list)
        for r in results:
            assert "asset" in r
            assert "long_exchange" in r
            assert "short_exchange" in r
            assert "edge_net" in r
            assert "funding_diff_annualized_pct" in r
