"""Tests for PostgreSQL database module."""
import pytest
from unittest.mock import patch, MagicMock


def test_postgres_module_imports():
    from database.postgres import (
        save_opportunity, get_viable_opportunities, get_best_opportunity,
        save_trade, get_daily_pnl, save_hodl_position, update_hodl_prices,
        get_hodl_alerts, get_all_hodl, save_venture_position, get_all_ventures,
        save_portfolio_snapshot, get_portfolio_overview, log_scanner_run,
        get_scanner_performance, save_engine_run_pg, save_alert,
        get_unread_alerts, get_database_stats, check_connection,
    )
    assert callable(save_opportunity)
    assert callable(save_trade)
    assert callable(save_hodl_position)


def test_db_config_defaults():
    from database.postgres import DB_CONFIG
    assert DB_CONFIG["host"] == "localhost"
    assert DB_CONFIG["port"] == 5432
    assert DB_CONFIG["dbname"] == "batman_lab"


def test_opportunity_metadata_extraction():
    standard_keys = {
        "opp_id", "ts", "type", "scanner_id", "asset", "market", "venue",
        "buy_price", "sell_price", "spot_price", "gross_spread_pct",
        "total_friction_pct", "edge_net", "viable", "depth_estimate", "observe_only"
    }
    opp = {
        "opp_id": "OPP-C-TEST", "type": "C", "asset": "USDT",
        "edge_net": 0.71, "viable": True,
        "custom_field": "extra", "merchant_count": 10,
    }
    metadata = {k: v for k, v in opp.items() if k not in standard_keys}
    assert "custom_field" in metadata
    assert "merchant_count" in metadata
    assert "opp_id" not in metadata


def test_trade_structure():
    trade = {
        "trade_id": "T-NW-001", "agent": "nightwing",
        "asset": "USDT", "side": "BUY", "price": 17.95, "quantity": 28,
    }
    assert trade["side"] in ("BUY", "SELL")
    assert trade["price"] > 0


def test_hodl_position_structure():
    pos = {
        "token": "XRP", "exchange": "binance", "quantity": 100,
        "avg_buy_price": 0.55, "take_profit_1": 1.00,
        "take_profit_2": 1.50, "take_profit_3": 2.50,
        "stop_loss": 0.40, "trailing_stop_pct": 15.0,
    }
    assert pos["take_profit_1"] > pos["avg_buy_price"]
    assert pos["stop_loss"] < pos["avg_buy_price"]


def test_venture_position_structure():
    pos = {"token": "XPIN", "chain": "ethereum", "quantity": 10000, "avg_buy_price": 0.001}
    assert pos["quantity"] > 0


def test_portfolio_snapshot_structure():
    balances = [
        {"platform": "cetes", "instrument": "CETES 28d", "balance": 5000, "category": "renta_fija"},
        {"platform": "nu", "instrument": "Nu Cuenta", "balance": 3000, "category": "renta_fija"},
        {"platform": "gbm", "instrument": "VOO ETF", "balance": 2000, "category": "bolsa"},
        {"platform": "binance", "instrument": "USDT", "balance": 28, "category": "crypto"},
    ]
    categories = set(b["category"] for b in balances)
    assert "renta_fija" in categories
    assert "crypto" in categories


def test_check_connection_returns_dict_on_error():
    from database.postgres import check_connection
    with patch("database.postgres.get_pool", side_effect=Exception("No DB")):
        result = check_connection()
        assert isinstance(result, dict)
        assert result["status"] == "error"


def test_get_viable_returns_empty_on_error():
    from database.postgres import get_viable_opportunities
    with patch("database.postgres.get_pool", side_effect=Exception("No DB")):
        result = get_viable_opportunities()
        assert isinstance(result, list)
        assert len(result) == 0


def test_get_hodl_alerts_returns_empty_on_error():
    from database.postgres import get_hodl_alerts
    with patch("database.postgres.get_pool", side_effect=Exception("No DB")):
        result = get_hodl_alerts()
        assert isinstance(result, list)


def test_get_database_stats_returns_empty_on_error():
    from database.postgres import get_database_stats
    with patch("database.postgres.get_pool", side_effect=Exception("No DB")):
        result = get_database_stats()
        assert isinstance(result, dict)
        assert len(result) == 0
