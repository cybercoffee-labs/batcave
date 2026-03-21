"""
Tests for core/gordon.py — GORDON (SHIELD) Security Module

All tests use tmp_path for file isolation.
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from core import gordon


# === Helpers ===


def _write_ledger(tmp_path, records):
    ledger = tmp_path / "trades.jsonl"
    ledger.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return ledger


def _write_batman_latest(tmp_path, age_seconds=100):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"timestamp": ts}))
    return latest


def _today_ts():
    return datetime.now(timezone.utc).isoformat()


def _make_trade(decision="OPPORTUNITY", action="SIMULATED_TRADE", edge_net=0.5, amount_usd=500):
    return {
        "timestamp": _today_ts(),
        "decision": decision,
        "action": action,
        "edge_net": edge_net,
        "amount_usd": amount_usd,
        "fiat": "MXN",
    }


# === Circuit Breaker ===


def test_circuit_breaker_approves_empty_ledger(tmp_path):
    with patch.object(gordon, "LEDGER_FILE", tmp_path / "trades.jsonl"):
        result = gordon.check_circuit_breaker()
    assert result["approved"] is True
    assert result["daily_trades"] == 0


def test_circuit_breaker_approves_positive_pnl(tmp_path):
    ledger = _write_ledger(tmp_path, [_make_trade(edge_net=0.5)])
    with patch.object(gordon, "LEDGER_FILE", ledger):
        result = gordon.check_circuit_breaker()
    assert result["approved"] is True
    assert result["daily_pnl_pct"] > 0


def test_circuit_breaker_blocks_heavy_losses(tmp_path):
    records = [_make_trade(edge_net=-3.0) for _ in range(5)]
    ledger = _write_ledger(tmp_path, records)
    with patch.object(gordon, "LEDGER_FILE", ledger):
        result = gordon.check_circuit_breaker()
    assert result["approved"] is False
    assert "daily_loss" in result.get("blocked_by", "")


def test_circuit_breaker_ignores_pass_decisions(tmp_path):
    records = [_make_trade(decision="PASS", action=None, edge_net=-5.0)]
    ledger = _write_ledger(tmp_path, records)
    with patch.object(gordon, "LEDGER_FILE", ledger):
        result = gordon.check_circuit_breaker()
    assert result["approved"] is True


def test_circuit_breaker_custom_threshold(tmp_path):
    records = [_make_trade(edge_net=-1.5)]
    ledger = _write_ledger(tmp_path, records)
    with patch.object(gordon, "LEDGER_FILE", ledger):
        result = gordon.check_circuit_breaker(limits={"max_daily_loss_pct": -1.0})
    assert result["approved"] is False


# === Batman Heartbeat ===


def test_heartbeat_approves_fresh_data(tmp_path):
    latest = _write_batman_latest(tmp_path, age_seconds=100)
    with patch.object(gordon, "BATMAN_LATEST", latest):
        result = gordon.check_batman_heartbeat()
    assert result["approved"] is True
    assert result["age_seconds"] <= 110


def test_heartbeat_blocks_stale_data(tmp_path):
    latest = _write_batman_latest(tmp_path, age_seconds=3000)
    with patch.object(gordon, "BATMAN_LATEST", latest):
        result = gordon.check_batman_heartbeat()
    assert result["approved"] is False
    assert "batman_silent" in result.get("blocked_by", "")


def test_heartbeat_blocks_missing_file(tmp_path):
    with patch.object(gordon, "BATMAN_LATEST", tmp_path / "nonexistent.json"):
        result = gordon.check_batman_heartbeat()
    assert result["approved"] is False
    assert "not_found" in result.get("blocked_by", "")


def test_heartbeat_custom_threshold(tmp_path):
    latest = _write_batman_latest(tmp_path, age_seconds=500)
    with patch.object(gordon, "BATMAN_LATEST", latest):
        result = gordon.check_batman_heartbeat(limits={"batman_max_silence_seconds": 300})
    assert result["approved"] is False


# === Spread Anomaly ===


def test_spread_anomaly_approves_normal_edge():
    result = gordon.check_spread_anomaly(0.5)
    assert result["approved"] is True
    assert result["warnings"] == []


def test_spread_anomaly_blocks_too_high():
    result = gordon.check_spread_anomaly(5.0)
    assert result["approved"] is False
    assert "too_high" in result.get("blocked_by", "")


def test_spread_anomaly_blocks_too_low():
    result = gordon.check_spread_anomaly(-6.0)
    assert result["approved"] is False
    assert "too_low" in result.get("blocked_by", "")


def test_spread_anomaly_warns_anomalous_flag():
    batman_data = {"spread_flag": "ANOMALOUS", "merchant_count": 10}
    result = gordon.check_spread_anomaly(0.5, batman_data=batman_data)
    assert result["approved"] is True
    assert "batman_spread_ANOMALOUS" in result["warnings"]


def test_spread_anomaly_warns_low_merchants():
    batman_data = {"spread_flag": "NORMAL", "merchant_count": 2}
    result = gordon.check_spread_anomaly(0.5, batman_data=batman_data)
    assert result["approved"] is True
    assert any("low_merchants" in w for w in result["warnings"])


def test_spread_anomaly_custom_threshold():
    result = gordon.check_spread_anomaly(2.0, limits={"max_edge_anomaly_pct": 1.5, "min_edge_sanity_pct": -5.0})
    assert result["approved"] is False


# === Daily Exposure ===


def test_daily_exposure_approves_under_limit(tmp_path):
    with patch.object(gordon, "LEDGER_FILE", tmp_path / "trades.jsonl"):
        result = gordon.check_daily_exposure(500)
    assert result["approved"] is True
    assert result["remaining"] == 9500.0


def test_daily_exposure_blocks_over_limit(tmp_path):
    records = [_make_trade(amount_usd=500) for _ in range(20)]
    ledger = _write_ledger(tmp_path, records)
    with patch.object(gordon, "LEDGER_FILE", ledger):
        result = gordon.check_daily_exposure(500)
    assert result["approved"] is False
    assert "daily_exposure" in result.get("blocked_by", "")


def test_daily_exposure_blocks_single_trade_too_large(tmp_path):
    with patch.object(gordon, "LEDGER_FILE", tmp_path / "trades.jsonl"):
        result = gordon.check_daily_exposure(3000)
    assert result["approved"] is False
    assert "single_trade" in result.get("blocked_by", "")


def test_daily_exposure_custom_limit(tmp_path):
    records = [_make_trade(amount_usd=500) for _ in range(3)]
    ledger = _write_ledger(tmp_path, records)
    with patch.object(gordon, "LEDGER_FILE", ledger):
        result = gordon.check_daily_exposure(500, limits={"max_daily_exposure_usd": 1500, "max_single_trade_usd": 2500})
    assert result["approved"] is False


# === Kill Switch ===


def test_kill_switch_inactive(tmp_path):
    with patch.object(gordon, "KILL_SWITCH_FILE", tmp_path / "KILL_SWITCH"):
        assert gordon.is_kill_switch_active() is False


def test_kill_switch_activate_deactivate(tmp_path):
    ks = tmp_path / "KILL_SWITCH"
    audit = tmp_path / "gordon_audit.jsonl"
    with patch.object(gordon, "KILL_SWITCH_FILE", ks), patch.object(gordon, "GORDON_AUDIT_FILE", audit):
        gordon.activate_kill_switch("test")
        assert ks.exists()
        assert gordon.is_kill_switch_active() is True
        gordon.deactivate_kill_switch()
        assert not ks.exists()
        assert gordon.is_kill_switch_active() is False


# === Run All Checks ===


def test_run_all_checks_approves_clean_state(tmp_path):
    latest = _write_batman_latest(tmp_path, age_seconds=100)
    with (
        patch.object(gordon, "LEDGER_FILE", tmp_path / "trades.jsonl"),
        patch.object(gordon, "KILL_SWITCH_FILE", tmp_path / "KILL_SWITCH"),
        patch.object(gordon, "GORDON_AUDIT_FILE", tmp_path / "audit.jsonl"),
        patch.object(gordon, "BATMAN_LATEST", latest),
    ):
        result = gordon.run_all_checks(edge_net=0.5, amount_usd=500)
    assert result["approved"] is True
    assert result["blocked_by"] is None
    assert len(result["checks"]) == 4


def test_run_all_checks_blocks_kill_switch(tmp_path):
    ks = tmp_path / "KILL_SWITCH"
    ks.write_text("test")
    with (
        patch.object(gordon, "KILL_SWITCH_FILE", ks),
        patch.object(gordon, "GORDON_AUDIT_FILE", tmp_path / "audit.jsonl"),
    ):
        result = gordon.run_all_checks()
    assert result["approved"] is False
    assert result["blocked_by"] == "kill_switch_active"


def test_run_all_checks_collects_multiple_blocks(tmp_path):
    """If multiple checks fail, all blocked_by reasons are collected."""
    with (
        patch.object(gordon, "LEDGER_FILE", tmp_path / "trades.jsonl"),
        patch.object(gordon, "KILL_SWITCH_FILE", tmp_path / "KILL_SWITCH"),
        patch.object(gordon, "GORDON_AUDIT_FILE", tmp_path / "audit.jsonl"),
        patch.object(gordon, "BATMAN_LATEST", tmp_path / "nonexistent.json"),
    ):
        result = gordon.run_all_checks(edge_net=5.0, amount_usd=500)
    assert result["approved"] is False
    assert len(result["blocked_by"]) >= 2  # heartbeat + spread anomaly at minimum


def test_run_all_checks_passes_warnings(tmp_path):
    latest = _write_batman_latest(tmp_path, age_seconds=100)
    batman_data = {"spread_flag": "ANOMALOUS", "merchant_count": 10}
    with (
        patch.object(gordon, "LEDGER_FILE", tmp_path / "trades.jsonl"),
        patch.object(gordon, "KILL_SWITCH_FILE", tmp_path / "KILL_SWITCH"),
        patch.object(gordon, "GORDON_AUDIT_FILE", tmp_path / "audit.jsonl"),
        patch.object(gordon, "BATMAN_LATEST", latest),
    ):
        result = gordon.run_all_checks(edge_net=0.5, amount_usd=500, batman_data=batman_data)
    assert result["approved"] is True
    assert "batman_spread_ANOMALOUS" in result["warnings"]
