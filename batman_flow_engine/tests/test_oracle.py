"""Tests for ORACLE HODL portfolio module."""
import pytest
from unittest.mock import patch


def test_oracle_imports():
    from core.oracle import (
        fetch_price, fetch_all_prices, evaluate_position,
        check_all_positions, add_position, print_status,
    )
    assert callable(fetch_price)
    assert callable(evaluate_position)


def test_evaluate_hold_signal():
    """Position with no targets hit should return HOLD."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 0.55, "quantity": 100,
           "take_profit_1": 1.00, "take_profit_2": 1.50, "take_profit_3": 2.50,
           "stop_loss": 0.40, "trailing_stop_pct": 15, "peak_price": 0.60}
    result = evaluate_position(pos, current_price=0.58)
    assert result["signal"] == "HOLD"
    assert result["pnl_pct"] > 0


def test_evaluate_stop_loss():
    """Price below stop loss should trigger STOP_LOSS_HIT."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 0.55, "quantity": 100,
           "take_profit_1": 1.00, "stop_loss": 0.40, "trailing_stop_pct": 15, "peak_price": 0.55}
    result = evaluate_position(pos, current_price=0.38)
    assert result["signal"] == "STOP_LOSS_HIT"
    assert result["urgency"] == "critical"


def test_evaluate_trailing_stop():
    """Price dropping 15% from peak should trigger TRAILING_STOP."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 0.55, "quantity": 100,
           "take_profit_1": 1.00, "stop_loss": 0.30, "trailing_stop_pct": 15, "peak_price": 1.00}
    result = evaluate_position(pos, current_price=0.84)  # 16% below peak
    assert result["signal"] == "TRAILING_STOP"
    assert result["urgency"] == "critical"


def test_evaluate_tp1():
    """Price hitting TP1 should trigger TP1_HIT."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 0.55, "quantity": 100,
           "take_profit_1": 1.00, "take_profit_2": 1.50, "take_profit_3": 2.50,
           "stop_loss": 0.40, "trailing_stop_pct": 15, "peak_price": 1.00,
           "tp1_hit": False, "tp2_hit": False, "tp3_hit": False}
    result = evaluate_position(pos, current_price=1.05)
    assert result["signal"] == "TP1_HIT"
    assert result["urgency"] == "medium"


def test_evaluate_tp3_moon():
    """Price hitting TP3 should tell you to keep moon bag."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 0.55, "quantity": 100,
           "take_profit_1": 1.00, "take_profit_2": 1.50, "take_profit_3": 2.50,
           "stop_loss": 0.40, "trailing_stop_pct": 15, "peak_price": 2.50,
           "tp1_hit": True, "tp2_hit": True, "tp3_hit": False}
    result = evaluate_position(pos, current_price=2.60)
    assert result["signal"] == "TP3_HIT"
    assert "moon bag" in result["action"].lower()


def test_evaluate_pnl_calculation():
    """P&L should be calculated correctly."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 0.50, "quantity": 200,
           "trailing_stop_pct": 15, "peak_price": 0}
    result = evaluate_position(pos, current_price=1.00)
    assert result["pnl_pct"] == 100.0
    assert result["pnl_usd"] == 100.0  # (1.00 - 0.50) * 200
    assert result["multiplier"] == 2.0


def test_evaluate_negative_pnl():
    """Negative P&L should be calculated correctly."""
    from core.oracle import evaluate_position
    pos = {"token": "XRP", "avg_buy_price": 1.00, "quantity": 100,
           "stop_loss": 0.50, "trailing_stop_pct": 15, "peak_price": 1.00}
    result = evaluate_position(pos, current_price=0.80)
    assert result["pnl_pct"] == -20.0
    assert result["pnl_usd"] == -20.0


def test_binance_symbols_mapping():
    """All common tokens should have Binance symbol mappings."""
    from core.oracle import BINANCE_SYMBOLS
    assert "BTC" in BINANCE_SYMBOLS
    assert "ETH" in BINANCE_SYMBOLS
    assert "XRP" in BINANCE_SYMBOLS
    assert "ENA" in BINANCE_SYMBOLS
    assert "SOL" in BINANCE_SYMBOLS


def test_fetch_price_with_mock():
    """fetch_price should return float from mocked API."""
    from core.oracle import fetch_price
    import json

    mock_response = json.dumps({"symbol": "XRPUSDT", "price": "0.5500"}).encode()

    with patch("core.oracle.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.read.return_value = mock_response
        price = fetch_price("XRP")
        assert price == 0.55
