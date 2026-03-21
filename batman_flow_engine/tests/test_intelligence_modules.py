"""Tests for intelligence modules: spread_tracker, pattern_analyzer, network_status"""

import json
from unittest.mock import patch
from pathlib import Path


# ─── Spread Tracker Tests ───


def test_spread_tracker_imports():
    from core.spread_tracker import build_lifetimes, get_lifetime_stats, init_db

    assert callable(build_lifetimes)
    assert callable(get_lifetime_stats)
    assert callable(init_db)


def test_spread_tracker_init_db(tmp_path):
    """Database should initialize with correct schema."""
    from core.spread_tracker import init_db

    with patch("core.spread_tracker.DB_FILE", tmp_path / "test.db"):
        conn = init_db()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor]
        assert "spread_lifetimes" in tables
        conn.close()


def test_get_lifetime_stats_empty():
    """Should return empty dict when no database exists."""
    from core.spread_tracker import get_lifetime_stats

    with patch("core.spread_tracker.DB_FILE", Path("/nonexistent/path.db")):
        result = get_lifetime_stats()
        assert result == {}


# ─── Pattern Analyzer Tests ───


def test_pattern_analyzer_imports():
    from core.pattern_analyzer import analyze_patterns

    assert callable(analyze_patterns)


def test_pattern_analyzer_no_data(tmp_path):
    """Should return error when no data file exists."""
    from core.pattern_analyzer import analyze_patterns

    with patch("core.pattern_analyzer.OPPS_FILE", tmp_path / "nonexistent.jsonl"):
        result = analyze_patterns()
        assert "error" in result


def test_pattern_analyzer_with_data(tmp_path):
    """Should analyze patterns from JSONL data."""
    from core.pattern_analyzer import analyze_patterns

    opps_file = tmp_path / "opportunities.jsonl"
    opps = [
        {"ts": "2026-03-20T10:00:00+00:00", "type": "C", "edge_net": 0.5, "viable": True},
        {"ts": "2026-03-20T11:00:00+00:00", "type": "C", "edge_net": 0.7, "viable": True},
        {"ts": "2026-03-20T14:00:00+00:00", "type": "G", "edge_net": 0.8, "viable": True},
        {"ts": "2026-03-20T15:00:00+00:00", "type": "G", "edge_net": -0.2, "viable": False},
    ]
    opps_file.write_text("\n".join(json.dumps(o) for o in opps))

    with (
        patch("core.pattern_analyzer.OPPS_FILE", opps_file),
        patch("core.pattern_analyzer.PATTERNS_FILE", tmp_path / "patterns.json"),
    ):
        result = analyze_patterns(hours_back=9999)
        assert result["total_opportunities"] == 4
        assert result["total_viable"] == 3
        assert "best_hours" in result
        assert "scanners" in result
        assert "C" in result["scanners"]
        assert "G" in result["scanners"]


# ─── Network Status Tests ───


def test_network_status_imports():
    from core.network_status import (
        full_network_check,
        get_cheapest_route,
    )

    assert callable(full_network_check)
    assert callable(get_cheapest_route)


def test_cheapest_route_binance_to_okx():
    """Should find cheapest transfer route."""
    from core.network_status import get_cheapest_route

    result = get_cheapest_route("binance", "okx")
    assert result["status"] == "ok"
    assert "cheapest" in result
    assert result["cheapest"]["fee_usdt"] >= 0
    assert result["cheapest"]["est_time_min"] > 0


def test_cheapest_route_no_common_network():
    """Should handle exchanges with no common networks."""
    from core.network_status import get_cheapest_route

    result = get_cheapest_route("nonexistent_exchange", "another")
    assert result["status"] == "no_common_network"


def test_typical_fees_structure():
    """All exchanges should have fee data."""
    from core.network_status import TYPICAL_FEES

    assert "binance" in TYPICAL_FEES
    assert "okx" in TYPICAL_FEES
    assert "bybit" in TYPICAL_FEES
    assert "bitso" in TYPICAL_FEES

    for exchange, networks in TYPICAL_FEES.items():
        for network, data in networks.items():
            assert "fee_usdt" in data
            assert "min_withdrawal" in data
            assert "est_time_min" in data
            assert data["fee_usdt"] >= 0


def test_okx_has_zero_fee_networks():
    """OKX should have 0-fee withdrawal on some networks."""
    from core.network_status import TYPICAL_FEES

    okx_fees = TYPICAL_FEES["okx"]
    zero_fee_networks = [n for n, d in okx_fees.items() if d["fee_usdt"] == 0]
    assert len(zero_fee_networks) > 0
