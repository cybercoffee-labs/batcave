"""Tests for PostgreSQL database module."""

from unittest.mock import patch


def test_postgres_module_imports():
    from database.postgres import (
        save_opportunity,
        save_trade,
        save_hodl_position,
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
        "opp_id",
        "ts",
        "type",
        "scanner_id",
        "asset",
        "market",
        "venue",
        "buy_price",
        "sell_price",
        "spot_price",
        "gross_spread_pct",
        "total_friction_pct",
        "edge_net",
        "viable",
        "depth_estimate",
        "observe_only",
    }
    opp = {
        "opp_id": "OPP-C-TEST",
        "type": "C",
        "asset": "USDT",
        "edge_net": 0.71,
        "viable": True,
        "custom_field": "extra",
        "merchant_count": 10,
    }
    metadata = {k: v for k, v in opp.items() if k not in standard_keys}
    assert "custom_field" in metadata
    assert "merchant_count" in metadata
    assert "opp_id" not in metadata


def test_trade_structure():
    trade = {
        "trade_id": "T-NW-001",
        "agent": "nightwing",
        "asset": "USDT",
        "side": "BUY",
        "price": 17.95,
        "quantity": 28,
    }
    assert trade["side"] in ("BUY", "SELL")
    assert trade["price"] > 0


def test_hodl_position_structure():
    pos = {
        "token": "XRP",
        "exchange": "binance",
        "quantity": 100,
        "avg_buy_price": 0.55,
        "take_profit_1": 1.00,
        "take_profit_2": 1.50,
        "take_profit_3": 2.50,
        "stop_loss": 0.40,
        "trailing_stop_pct": 15.0,
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


# ─────────────────── SHARED AVAILABILITY STATE (2026-04-21 unification) ───────────────────


def test_pg_available_probes_on_first_call_and_caches():
    """First call probes; second call within the retry window must not re-probe."""
    from database import postgres as pg

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = None
    pg._pg_last_check_ts = None
    try:
        with patch(
            "database.postgres.check_connection",
            return_value={"status": "ok", "version": "x", "tables": 0},
        ) as mocked:
            assert pg.pg_available() is True
            assert mocked.call_count == 1
            assert pg.pg_available() is True  # cached — no second probe
            assert mocked.call_count == 1
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts


def test_pg_available_reprobes_after_recheck_interval_when_down():
    """While down, pg_available re-probes after PG_RECHECK_INTERVAL_SEC elapses."""
    import time

    from database import postgres as pg

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = False
    pg._pg_last_check_ts = time.monotonic() - (pg.PG_RECHECK_INTERVAL_SEC + 1)
    try:
        with patch(
            "database.postgres.check_connection",
            return_value={"status": "ok"},
        ) as mocked:
            assert pg.pg_available() is True
            assert mocked.call_count == 1
            assert pg._pg_available is True
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts


def test_mark_pg_unavailable_flushes_pool_on_connection_error():
    """mark_pg_unavailable flushes the pool ONLY for connection-class errors."""
    from database import postgres as pg

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    previous_pool = pg._pool
    try:
        # Set up a sentinel "pool" we can observe being flushed.
        pg._pool = object()  # truthy stand-in; pg_reset_pool handles non-pool gracefully
        pg._pg_available = True
        pg._pg_last_check_ts = None

        # Non-connection error → state flips, pool is NOT touched.
        pg.mark_pg_unavailable("bad data", exc=ValueError("bad value"))
        assert pg._pg_available is False
        assert pg._pool is not None

        # Connection-class error → state flips, pool IS flushed.
        # Re-arm state so we can observe the second transition.
        pg._pg_available = True
        connection_err = Exception("could not connect to server: Connection refused")
        pg.mark_pg_unavailable("conn refused", exc=connection_err)
        assert pg._pg_available is False
        assert pg._pool is None
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts
        pg._pool = previous_pool


def test_pg_probe_forces_immediate_check():
    """pg_probe() bypasses the retry-window cache."""
    import time

    from database import postgres as pg

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = False
    pg._pg_last_check_ts = time.monotonic()  # inside retry window — pg_available would skip
    try:
        with patch(
            "database.postgres.check_connection",
            return_value={"status": "ok"},
        ) as mocked:
            # pg_available stays False (retry window not elapsed).
            assert pg.pg_available() is False
            assert mocked.call_count == 0
            # pg_probe forces a fresh probe regardless of window.
            assert pg.pg_probe() is True
            assert mocked.call_count == 1
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts
