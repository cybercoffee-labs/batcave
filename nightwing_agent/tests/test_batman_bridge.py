"""
Tests for core/batman_bridge.py — Batman → Nightwing data bridge

All tests use tmp_path for file isolation.
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from core import batman_bridge


# === Helpers ===


def _make_opp(pair="MXN", edge_net=0.5, viable=True, age_seconds=100, opp_id="OPP-C-TEST123"):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    return {
        "opp_id": opp_id,
        "ts": ts,
        "type": "C",
        "asset": "USDT",
        "market": pair,
        "venue": "binance_p2p",
        "p2p_buy_price": 18.05,
        "p2p_sell_price": 17.98,
        "spot_price": 17.89,
        "merchant_spread": 0.002,
        "spread_flag": "NORMAL",
        "p2p_premium": 0.009,
        "premium_quality": "VERIFIED",
        "rate_source": "official",
        "total_friction_pct": 0.25,
        "edge_net": edge_net,
        "viable": viable,
        "depth_estimate": 13000.0,
        "merchant_count": 10,
        "scanner_id": "C-P2P-LATAM",
        "observe_only": True,
    }


def _write_opps(tmp_path, records):
    opps = tmp_path / "opportunities.jsonl"
    opps.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return opps


def _write_latest(tmp_path, age_seconds=100):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"timestamp": ts}))
    return latest


# === fetch_from_batman ===


def test_fetch_returns_ok_for_fresh_data(tmp_path):
    opps = _write_opps(tmp_path, [_make_opp(age_seconds=100)])
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["status"] == "ok"
    assert result["fiat"] == "MXN"
    assert result["market"] == "USDT/MXN"
    assert result["edge_net"] == 0.5
    assert result["viable"] is True
    assert result["opp_id"] == "OPP-C-TEST123"


def test_fetch_returns_stale_for_old_data(tmp_path):
    opps = _write_opps(tmp_path, [_make_opp(age_seconds=1500)])
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["status"] == "stale"
    assert result["age_seconds"] > 1200
    assert "data" in result


def test_fetch_returns_error_for_missing_file(tmp_path):
    with patch.object(batman_bridge, "BATMAN_OPPS", tmp_path / "nonexistent.jsonl"):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["status"] == "error"
    assert "not_found" in result["error"]


def test_fetch_returns_error_for_no_matching_pair(tmp_path):
    opps = _write_opps(tmp_path, [_make_opp(pair="ARS")])
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["status"] == "error"
    assert "no_record_for_MXN" in result["error"]


def test_fetch_finds_correct_pair_among_multiple(tmp_path):
    records = [
        _make_opp(pair="ARS", edge_net=0.3, opp_id="OPP-ARS"),
        _make_opp(pair="MXN", edge_net=0.7, opp_id="OPP-MXN"),
        _make_opp(pair="COP", edge_net=-0.5, opp_id="OPP-COP"),
    ]
    opps = _write_opps(tmp_path, records)
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["status"] == "ok"
    assert result["edge_net"] == 0.7
    assert result["opp_id"] == "OPP-MXN"


def test_fetch_returns_latest_record_for_pair(tmp_path):
    records = [
        _make_opp(pair="MXN", edge_net=0.3, opp_id="OPP-OLD", age_seconds=500),
        _make_opp(pair="MXN", edge_net=0.8, opp_id="OPP-NEW", age_seconds=100),
    ]
    opps = _write_opps(tmp_path, records)
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["opp_id"] == "OPP-NEW"
    assert result["edge_net"] == 0.8


def test_fetch_skips_non_type_c_records(tmp_path):
    basis_record = _make_opp(pair="MXN")
    basis_record["type"] = "B"
    p2p_record = _make_opp(pair="MXN", edge_net=0.6, opp_id="OPP-P2P")
    opps = _write_opps(tmp_path, [basis_record, p2p_record])
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["opp_id"] == "OPP-P2P"


def test_fetch_skips_corrupt_jsonl_lines(tmp_path):
    good = _make_opp(pair="MXN", opp_id="OPP-GOOD")
    opps = tmp_path / "opportunities.jsonl"
    opps.write_text("not valid json\n" + json.dumps(good) + "\n{broken\n")
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["status"] == "ok"
    assert result["opp_id"] == "OPP-GOOD"


def test_fetch_includes_all_expected_fields(tmp_path):
    opps = _write_opps(tmp_path, [_make_opp()])
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    expected_fields = [
        "status",
        "fiat",
        "market",
        "p2p_premium",
        "edge_net",
        "viable",
        "total_friction_pct",
        "spot_price",
        "p2p_buy_price",
        "p2p_sell_price",
        "depth_estimate",
        "merchant_count",
        "premium_quality",
        "rate_source",
        "spread_flag",
        "age_seconds",
        "batman_ts",
        "opp_id",
    ]
    for field in expected_fields:
        assert field in result, f"Missing field: {field}"


def test_fetch_reads_only_last_50_lines(tmp_path):
    """With 60 records, only the last 50 are checked."""
    old_records = [_make_opp(pair="MXN", edge_net=0.1, opp_id=f"OPP-OLD-{i}", age_seconds=100) for i in range(55)]
    new_record = _make_opp(pair="MXN", edge_net=0.9, opp_id="OPP-NEWEST", age_seconds=50)
    opps = _write_opps(tmp_path, old_records + [new_record])
    with patch.object(batman_bridge, "BATMAN_OPPS", opps):
        result = batman_bridge.fetch_from_batman("MXN")
    assert result["opp_id"] == "OPP-NEWEST"


# === is_batman_alive ===


def test_is_alive_true_when_fresh(tmp_path):
    latest = _write_latest(tmp_path, age_seconds=100)
    with patch.object(batman_bridge, "BATMAN_LATEST", latest):
        assert batman_bridge.is_batman_alive() is True


def test_is_alive_false_when_stale(tmp_path):
    latest = _write_latest(tmp_path, age_seconds=1500)
    with patch.object(batman_bridge, "BATMAN_LATEST", latest):
        assert batman_bridge.is_batman_alive() is False


def test_is_alive_false_when_missing(tmp_path):
    with patch.object(batman_bridge, "BATMAN_LATEST", tmp_path / "nonexistent.json"):
        assert batman_bridge.is_batman_alive() is False


def test_is_alive_false_when_corrupt(tmp_path):
    latest = tmp_path / "latest.json"
    latest.write_text("not json")
    with patch.object(batman_bridge, "BATMAN_LATEST", latest):
        assert batman_bridge.is_batman_alive() is False
