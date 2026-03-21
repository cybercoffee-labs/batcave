"""Tests for Scanner J: DEX vs CEX"""

from unittest.mock import patch


def test_scanner_j_imports():
    """Scanner J modules import correctly."""
    from core.scanner_dex import (
        scan_dex_cex,
        fetch_dexscreener_price,
        fetch_cex_price,
    )

    assert callable(scan_dex_cex)
    assert callable(fetch_dexscreener_price)
    assert callable(fetch_cex_price)


def test_scanner_j_token_list():
    """Scanner J should have 10 tokens configured."""
    from core.scanner_dex import TOKENS

    assert len(TOKENS) == 10
    for token in TOKENS:
        assert "asset" in token
        assert "chain" in token
        assert "cex_symbol_binance" in token


def test_scanner_j_gas_costs():
    """All chains should have gas costs defined."""
    from core.scanner_dex import GAS_COSTS, TOKENS

    chains = set(t["chain"] for t in TOKENS)
    for chain in chains:
        assert chain in GAS_COSTS, f"Missing gas cost for {chain}"


def test_scanner_j_handles_no_data():
    """Scanner should handle missing DEX data gracefully."""
    from core.scanner_dex import scan_dex_cex

    with patch("core.scanner_dex._fetch_json", return_value=None):
        results = scan_dex_cex(log_to_file=False)
        assert isinstance(results, list)
        assert len(results) == 0


def test_scanner_j_edge_calculation():
    """Edge should account for gas + CEX fee + DEX fee."""
    from core.scanner_dex import CEX_FEE_PCT, DEX_FEE_PCT, GAS_COSTS

    gas_pct = (GAS_COSTS["ethereum"] / 100) * 100
    total_fees = CEX_FEE_PCT + DEX_FEE_PCT + gas_pct
    assert total_fees > 8.0

    gas_pct_sol = (GAS_COSTS["solana"] / 100) * 100
    total_fees_sol = CEX_FEE_PCT + DEX_FEE_PCT + gas_pct_sol
    assert total_fees_sol < 1.0


def test_scanner_j_min_edge():
    """MIN_EDGE_PCT should be defined and positive."""
    from core.scanner_dex import MIN_EDGE_PCT

    assert MIN_EDGE_PCT > 0
    assert MIN_EDGE_PCT <= 5.0


def test_fetch_cex_price_returns_dict_or_none():
    """CEX price fetcher should return dict with bid/ask/price or None."""
    from core.scanner_dex import fetch_cex_price

    with patch("core.scanner_dex._fetch_json", return_value={"bidPrice": "100.5", "askPrice": "100.6"}):
        result = fetch_cex_price("BTCUSDT")
        assert result is not None
        assert "bid" in result
        assert "ask" in result
        assert "price" in result
        assert result["bid"] == 100.5

    with patch("core.scanner_dex._fetch_json", return_value=None):
        result = fetch_cex_price("BTCUSDT")
        assert result is None
