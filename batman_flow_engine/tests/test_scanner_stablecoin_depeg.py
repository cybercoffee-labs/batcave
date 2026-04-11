"""
Tests for Scanner H: Stablecoin Depeg Scanner

Mocks all HTTP calls for isolated testing.
"""

from unittest.mock import patch

from core.scanner_stablecoin_depeg import (
    check_depeg,
    find_depeg_opportunities,
    fetch_stablecoin_price,
    fetch_all_stablecoin_prices,
    scan_stablecoin_depeg,
    _load_threshold,
    SCANNER_ID,
    STABLECOINS,
    DEPEG_LOW,
    DEPEG_HIGH,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test check_depeg
# ─────────────────────────────────────────────────────────────────────────────


def test_check_depeg_low():
    """Test detecting low depeg (< 0.995)."""
    result = check_depeg(0.990)
    assert result == "low"


def test_check_depeg_high():
    """Test detecting high depeg (> 1.005)."""
    result = check_depeg(1.010)
    assert result == "high"


def test_check_depeg_normal():
    """Test normal price range (no depeg)."""
    result = check_depeg(1.000)
    assert result is None

    result = check_depeg(0.998)
    assert result is None

    result = check_depeg(1.003)
    assert result is None


def test_check_depeg_boundary_low():
    """Test boundary at DEPEG_LOW."""
    result = check_depeg(DEPEG_LOW)
    assert result is None  # Exactly 0.995 is not depeg


def test_check_depeg_boundary_high():
    """Test boundary at DEPEG_HIGH."""
    result = check_depeg(DEPEG_HIGH)
    assert result is None  # Exactly 1.005 is not depeg


# ─────────────────────────────────────────────────────────────────────────────
# Test find_depeg_opportunities
# ─────────────────────────────────────────────────────────────────────────────


def test_find_depeg_opportunities_depeg_event():
    """Test finding depeg events."""
    prices = {
        "USDT": {"binance": 0.990, "okx": 0.998},
    }

    with patch("core.scanner_stablecoin_depeg._load_threshold", return_value=0.2):
        opps = find_depeg_opportunities(prices)

    depeg_opps = [o for o in opps if o["event_type"] == "depeg"]
    assert len(depeg_opps) == 1
    assert depeg_opps[0]["stablecoin"] == "USDT"
    assert depeg_opps[0]["exchange"] == "binance"
    assert depeg_opps[0]["depeg_direction"] == "low"


def test_find_depeg_opportunities_arbitrage():
    """Test finding arbitrage opportunities."""
    prices = {
        "USDC": {"binance": 0.998, "okx": 1.003},  # 0.5% spread
    }

    with patch("core.scanner_stablecoin_depeg._load_threshold", return_value=0.2):
        opps = find_depeg_opportunities(prices)

    arb_opps = [o for o in opps if o["event_type"] == "arbitrage"]
    assert len(arb_opps) == 1
    assert arb_opps[0]["buy_exchange"] == "binance"
    assert arb_opps[0]["sell_exchange"] == "okx"
    assert arb_opps[0]["spread_pct"] > 0


def test_find_depeg_opportunities_no_arb_below_threshold():
    """Test no arbitrage when spread below threshold."""
    prices = {
        "USDC": {"binance": 0.9990, "okx": 1.0000},  # 0.1% spread
    }

    with patch("core.scanner_stablecoin_depeg._load_threshold", return_value=0.2):
        opps = find_depeg_opportunities(prices)

    arb_opps = [o for o in opps if o["event_type"] == "arbitrage"]
    assert len(arb_opps) == 0


def test_find_depeg_opportunities_empty_prices():
    """Test handling empty price data."""
    prices = {"USDT": {}}

    with patch("core.scanner_stablecoin_depeg._load_threshold", return_value=0.2):
        opps = find_depeg_opportunities(prices)

    assert len(opps) == 0


def test_find_depeg_opportunities_single_exchange():
    """Test no arbitrage with only one exchange."""
    prices = {
        "USDC": {"binance": 1.000},  # Only one exchange
    }

    with patch("core.scanner_stablecoin_depeg._load_threshold", return_value=0.2):
        opps = find_depeg_opportunities(prices)

    arb_opps = [o for o in opps if o["event_type"] == "arbitrage"]
    assert len(arb_opps) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_stablecoin_price (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_stablecoin_depeg.fetch_binance_price")
def test_fetch_stablecoin_price_binance(mock_binance):
    """Test fetching price from Binance."""
    mock_binance.return_value = {"price": 1.0005}

    result = fetch_stablecoin_price("binance", "USDC")

    assert result == 1.0005


@patch("core.scanner_stablecoin_depeg.fetch_okx_price")
def test_fetch_stablecoin_price_okx(mock_okx):
    """Test fetching price from OKX."""
    mock_okx.return_value = {"price": 0.9998}

    result = fetch_stablecoin_price("okx", "USDC")

    assert result == 0.9998


@patch("core.scanner_stablecoin_depeg.fetch_bybit_price")
def test_fetch_stablecoin_price_bybit(mock_bybit):
    """Test fetching price from Bybit."""
    mock_bybit.return_value = {"price": 1.0002}

    result = fetch_stablecoin_price("bybit", "USDC")

    assert result == 1.0002


@patch("core.scanner_stablecoin_depeg.fetch_binance_price")
def test_fetch_stablecoin_price_error(mock_binance):
    """Test handling fetch error."""
    mock_binance.side_effect = Exception("API error")

    result = fetch_stablecoin_price("binance", "USDC")

    assert result is None


def test_fetch_stablecoin_price_unknown_exchange():
    """Test handling unknown exchange."""
    result = fetch_stablecoin_price("unknown", "USDT")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_all_stablecoin_prices (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_stablecoin_depeg.fetch_stablecoin_price")
def test_fetch_all_stablecoin_prices(mock_fetch):
    """Test fetching all prices."""
    mock_fetch.side_effect = [
        # USDT: binance, okx, bybit
        1.0001,
        1.0002,
        None,
        # USDC: binance, okx, bybit
        0.9998,
        1.0000,
        1.0001,
        # DAI: binance, okx, bybit
        1.0003,
        1.0005,
        0.9999,
    ]

    result = fetch_all_stablecoin_prices()

    assert "USDT" in result
    assert "USDC" in result
    assert "DAI" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test scan_stablecoin_depeg (mocked)
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.scanner_stablecoin_depeg._append_to_log")
@patch("core.scanner_stablecoin_depeg.fetch_all_stablecoin_prices")
def test_scan_stablecoin_depeg_logs_opportunities(mock_fetch, mock_log):
    """Test scan logs opportunities."""
    mock_fetch.return_value = {
        "USDT": {"binance": 0.990, "okx": 0.998},  # Depeg on binance
    }
    mock_log.return_value = True

    result = scan_stablecoin_depeg(log_to_file=True)

    assert len(result) >= 1
    mock_log.assert_called()


@patch("core.scanner_stablecoin_depeg._append_to_log")
@patch("core.scanner_stablecoin_depeg.fetch_all_stablecoin_prices")
def test_scan_stablecoin_depeg_opportunity_format(mock_fetch, mock_log):
    """Test opportunity output format."""
    mock_fetch.return_value = {
        "USDC": {"binance": 0.990, "okx": 1.000},  # Depeg + arb
    }
    mock_log.return_value = True

    result = scan_stablecoin_depeg(log_to_file=False)

    for opp in result:
        assert opp["type"] == "H"
        assert opp["scanner_id"] == SCANNER_ID
        assert opp["opp_id"].startswith("OPP-H-")
        assert "ts" in opp
        assert "stablecoin" in opp
        assert opp["observe_only"] is True


@patch("core.scanner_stablecoin_depeg.fetch_all_stablecoin_prices")
def test_scan_stablecoin_depeg_returns_list(mock_fetch):
    """Test scan always returns a list."""
    mock_fetch.return_value = {}

    result = scan_stablecoin_depeg(log_to_file=False)

    assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# Test _load_threshold
# ─────────────────────────────────────────────────────────────────────────────


def test_load_threshold_default():
    """Test default threshold when config not available."""
    with patch("core.scanner_stablecoin_depeg.CONFIG_FILE") as mock_path:
        mock_path.exists.return_value = False
        result = _load_threshold()
        assert result == 0.2


# ─────────────────────────────────────────────────────────────────────────────
# Test constants
# ─────────────────────────────────────────────────────────────────────────────


def test_scanner_id_format():
    """Test scanner ID follows convention."""
    assert SCANNER_ID == "H-STABLECOIN-DEPEG"


def test_stablecoins_list():
    """Test expected stablecoins are included."""
    assert "USDT" in STABLECOINS
    assert "USDC" in STABLECOINS
    assert "DAI" in STABLECOINS


def test_depeg_thresholds():
    """Test depeg threshold values."""
    assert DEPEG_LOW == 0.995
    assert DEPEG_HIGH == 1.005
