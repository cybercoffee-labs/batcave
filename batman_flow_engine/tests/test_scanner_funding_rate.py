"""
Tests for Scanner E: Funding Rate Arbitrage Scanner

All HTTP calls are mocked - no real network requests.
"""

from unittest.mock import patch
from core.scanner_funding_rate import (
    fetch_all_funding_rates,
    analyze_funding_rates,
    scan_funding_rates,
    _fetch_binance_funding_rate,
    _fetch_okx_funding_rate,
    _fetch_bybit_funding_rate,
    SCANNER_ID,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Response Helpers
# ─────────────────────────────────────────────────────────────────────────────


def mock_binance_funding(rate="0.0001"):
    """Create mock Binance funding rate response."""
    return [{"symbol": "BTCUSDT", "fundingRate": rate, "fundingTime": "1710691200000"}]


def mock_okx_funding(rate="0.00012"):
    """Create mock OKX funding rate response."""
    return {"code": "0", "data": [{"fundingRate": rate, "nextFundingTime": "1710691200000", "instId": "BTC-USDT-SWAP"}]}


def mock_bybit_funding(rate="0.00015"):
    """Create mock Bybit funding rate response."""
    return {
        "retCode": 0,
        "result": {"list": [{"symbol": "BTCUSDT", "fundingRate": rate, "fundingRateTimestamp": "1710691200000"}]},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test Individual Exchange Fetchers
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_funding_rate._fetch_json")
def test_fetch_binance_funding_rate_success(mock_fetch):
    """Test successful Binance funding rate fetch."""
    mock_fetch.return_value = mock_binance_funding("0.0001")

    result = _fetch_binance_funding_rate("BTCUSDT")

    assert result is not None
    assert result["exchange"] == "binance"
    assert result["funding_rate"] == 0.0001
    assert result["funding_rate_pct"] == 0.01
    assert "next_funding_time" in result


@patch("core.scanner_funding_rate._fetch_json")
def test_fetch_okx_funding_rate_success(mock_fetch):
    """Test successful OKX funding rate fetch."""
    mock_fetch.return_value = mock_okx_funding("0.00012")

    result = _fetch_okx_funding_rate("BTC-USDT-SWAP")

    assert result is not None
    assert result["exchange"] == "okx"
    assert result["funding_rate"] == 0.00012
    assert result["funding_rate_pct"] == 0.012
    assert "next_funding_time" in result


@patch("core.scanner_funding_rate._fetch_json")
def test_fetch_bybit_funding_rate_success(mock_fetch):
    """Test successful Bybit funding rate fetch."""
    mock_fetch.return_value = mock_bybit_funding("0.00015")

    result = _fetch_bybit_funding_rate("BTCUSDT")

    assert result is not None
    assert result["exchange"] == "bybit"
    assert result["funding_rate"] == 0.00015
    assert result["funding_rate_pct"] == 0.015
    assert "next_funding_time" in result


@patch("core.scanner_funding_rate._fetch_json")
def test_fetch_funding_rate_returns_none_on_failure(mock_fetch):
    """Test that funding rate fetchers return None on API failure."""
    mock_fetch.return_value = None

    assert _fetch_binance_funding_rate("BTCUSDT") is None
    assert _fetch_okx_funding_rate("BTC-USDT-SWAP") is None
    assert _fetch_bybit_funding_rate("BTCUSDT") is None


@patch("core.scanner_funding_rate._fetch_json")
def test_fetch_binance_empty_list(mock_fetch):
    """Test Binance fetcher handles empty list."""
    mock_fetch.return_value = []

    result = _fetch_binance_funding_rate("BTCUSDT")

    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all_funding_rates
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_funding_rate._fetch_bybit_funding_rate")
@patch("core.scanner_funding_rate._fetch_okx_funding_rate")
@patch("core.scanner_funding_rate._fetch_binance_funding_rate")
def test_fetch_all_funding_rates_aggregates_exchanges(mock_binance, mock_okx, mock_bybit):
    """Test that fetch_all_funding_rates aggregates data from all exchanges."""
    mock_binance.return_value = {"exchange": "binance", "funding_rate": 0.0001, "funding_rate_pct": 0.01}
    mock_okx.return_value = {"exchange": "okx", "funding_rate": 0.00012, "funding_rate_pct": 0.012}
    mock_bybit.return_value = {"exchange": "bybit", "funding_rate": 0.00015, "funding_rate_pct": 0.015}

    result = fetch_all_funding_rates("BTC")

    assert "binance" in result
    assert "okx" in result
    assert "bybit" in result
    assert len(result) == 3


@patch("core.scanner_funding_rate._fetch_bybit_funding_rate")
@patch("core.scanner_funding_rate._fetch_okx_funding_rate")
@patch("core.scanner_funding_rate._fetch_binance_funding_rate")
def test_fetch_all_funding_rates_handles_partial_failure(mock_binance, mock_okx, mock_bybit):
    """Test that partial exchange failures don't break the whole fetch."""
    mock_binance.return_value = {"exchange": "binance", "funding_rate": 0.0001, "funding_rate_pct": 0.01}
    mock_okx.return_value = None  # OKX failed
    mock_bybit.return_value = {"exchange": "bybit", "funding_rate": 0.00015, "funding_rate_pct": 0.015}

    result = fetch_all_funding_rates("BTC")

    assert "binance" in result
    assert "okx" not in result
    assert "bybit" in result
    assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test analyze_funding_rates
# ─────────────────────────────────────────────────────────────────────────────


def test_analyze_funding_rates_detects_high_funding():
    """Test that high funding rates are detected."""
    rates = {
        "binance": {"exchange": "binance", "funding_rate": 0.0002, "funding_rate_pct": 0.02, "next_funding_time": None},
        "okx": {"exchange": "okx", "funding_rate": 0.0001, "funding_rate_pct": 0.01, "next_funding_time": None},
    }

    # Threshold 0.015% should catch Binance (0.02%) but not OKX (0.01%)
    opportunities = analyze_funding_rates("BTC", rates, threshold=0.015)

    high_funding_opps = [o for o in opportunities if o["opportunity_type"] == "high_funding"]
    assert len(high_funding_opps) >= 1
    assert any(o["exchange"] == "binance" for o in high_funding_opps)


def test_analyze_funding_rates_calculates_annualized():
    """Test that annualized rate is calculated correctly."""
    rates = {
        "binance": {"exchange": "binance", "funding_rate": 0.0001, "funding_rate_pct": 0.01, "next_funding_time": None},
    }

    opportunities = analyze_funding_rates("BTC", rates, threshold=0.001)

    if opportunities:
        opp = opportunities[0]
        # 0.01% * 3 * 365 = 10.95%
        expected_annualized = 0.01 * 3 * 365
        assert abs(opp["annualized_pct"] - expected_annualized) < 0.1


def test_analyze_funding_rates_detects_cross_exchange_spread():
    """Test that cross-exchange funding rate spread is detected."""
    rates = {
        "binance": {"exchange": "binance", "funding_rate": 0.0001, "funding_rate_pct": 0.01, "next_funding_time": None},
        "okx": {"exchange": "okx", "funding_rate": 0.0004, "funding_rate_pct": 0.04, "next_funding_time": None},
    }

    # Spread = 0.04 - 0.01 = 0.03%, threshold * 2 = 0.02%
    opportunities = analyze_funding_rates("BTC", rates, threshold=0.01)

    cross_opps = [o for o in opportunities if o["opportunity_type"] == "cross_exchange_funding"]
    assert len(cross_opps) >= 1

    opp = cross_opps[0]
    assert opp["high_exchange"] == "okx"
    assert opp["low_exchange"] == "binance"
    assert opp["cross_exchange_spread"] == 0.03


def test_analyze_funding_rates_direction_positive():
    """Test that direction is 'short' for positive funding rates."""
    rates = {
        "binance": {"exchange": "binance", "funding_rate": 0.0002, "funding_rate_pct": 0.02, "next_funding_time": None},
    }

    opportunities = analyze_funding_rates("BTC", rates, threshold=0.01)

    high_funding_opps = [o for o in opportunities if o["opportunity_type"] == "high_funding"]
    assert len(high_funding_opps) >= 1
    assert high_funding_opps[0]["direction"] == "short"


def test_analyze_funding_rates_direction_negative():
    """Test that direction is 'long' for negative funding rates."""
    rates = {
        "binance": {
            "exchange": "binance",
            "funding_rate": -0.0002,
            "funding_rate_pct": -0.02,
            "next_funding_time": None,
        },
    }

    opportunities = analyze_funding_rates("BTC", rates, threshold=0.01)

    high_funding_opps = [o for o in opportunities if o["opportunity_type"] == "high_funding"]
    assert len(high_funding_opps) >= 1
    assert high_funding_opps[0]["direction"] == "long"


def test_analyze_funding_rates_empty_rates():
    """Test that empty rates return no opportunities."""
    opportunities = analyze_funding_rates("BTC", {}, threshold=0.01)
    assert opportunities == []


# ─────────────────────────────────────────────────────────────────────────────
# Test scan_funding_rates
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_funding_rate._append_to_log")
@patch("core.scanner_funding_rate.fetch_all_funding_rates")
def test_scan_funding_rates_returns_list(mock_fetch_all, mock_log):
    """Test that scan_funding_rates returns a list of opportunities."""
    mock_fetch_all.return_value = {
        "binance": {"exchange": "binance", "funding_rate": 0.0001, "funding_rate_pct": 0.01, "next_funding_time": None},
    }
    mock_log.return_value = True

    results = scan_funding_rates(log_to_file=False)

    assert isinstance(results, list)


@patch("core.scanner_funding_rate._append_to_log")
@patch("core.scanner_funding_rate.fetch_all_funding_rates")
def test_scan_funding_rates_opportunity_format(mock_fetch_all, mock_log):
    """Test that opportunity records have correct format."""
    mock_fetch_all.return_value = {
        "binance": {"exchange": "binance", "funding_rate": 0.0005, "funding_rate_pct": 0.05, "next_funding_time": None},
    }
    mock_log.return_value = True

    with patch("core.scanner_funding_rate._load_threshold", return_value=0.01):
        results = scan_funding_rates(log_to_file=True)

    # Check we have results
    assert len(results) >= 1

    opp = results[0]
    assert opp["type"] == "E"
    assert opp["scanner_id"] == SCANNER_ID
    assert opp["opp_id"].startswith("OPP-E-")
    assert "ts" in opp
    assert "asset" in opp
    assert opp["observe_only"] is True


@patch("core.scanner_funding_rate._append_to_log")
@patch("core.scanner_funding_rate.fetch_all_funding_rates")
def test_scan_funding_rates_logs_to_file(mock_fetch_all, mock_log):
    """Test that opportunities are logged to JSONL."""
    mock_fetch_all.return_value = {
        "binance": {"exchange": "binance", "funding_rate": 0.0005, "funding_rate_pct": 0.05, "next_funding_time": None},
    }
    mock_log.return_value = True

    with patch("core.scanner_funding_rate._load_threshold", return_value=0.01):
        results = scan_funding_rates(log_to_file=True)

    # Should have called append_to_log for each opportunity
    assert mock_log.called


# ─────────────────────────────────────────────────────────────────────────────
# Test Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


def test_analyze_funding_rates_single_exchange():
    """Test that single exchange can still detect high funding."""
    rates = {
        "binance": {"exchange": "binance", "funding_rate": 0.0005, "funding_rate_pct": 0.05, "next_funding_time": None},
    }

    opportunities = analyze_funding_rates("BTC", rates, threshold=0.01)

    # Should detect high funding but not cross-exchange
    high_funding_opps = [o for o in opportunities if o["opportunity_type"] == "high_funding"]
    cross_opps = [o for o in opportunities if o["opportunity_type"] == "cross_exchange_funding"]

    assert len(high_funding_opps) >= 1
    assert len(cross_opps) == 0


def test_analyze_funding_rates_no_opportunity_below_threshold():
    """Test that no opportunity is returned when rates are below threshold."""
    rates = {
        "binance": {
            "exchange": "binance",
            "funding_rate": 0.00001,
            "funding_rate_pct": 0.001,
            "next_funding_time": None,
        },
        "okx": {"exchange": "okx", "funding_rate": 0.00001, "funding_rate_pct": 0.001, "next_funding_time": None},
    }

    opportunities = analyze_funding_rates("BTC", rates, threshold=0.01)

    # No high funding (0.001% < 0.01%)
    # No cross-exchange (spread 0% < 0.02%)
    assert len(opportunities) == 0
