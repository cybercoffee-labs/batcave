"""
Tests for GORDON check() — Batman-side security gate.
Covers kill switch, DQ gate, runtime guard, regime anomaly, and engine integration.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


import core.gordon as gordon_mod
from core.gordon import check


# ─────────────────────────── helpers ───────────────────────────


def _result(dq_score=1.0, regime_label="NORMAL"):
    return {
        "data_quality": {"dq_score": dq_score, "status": "ok"},
        "stress": {"regime": {"label": regime_label, "triggers": []}},
    }


def _patched_check(result=None, *, kill_switch=False, guard_status="not_found"):
    """Run check() with filesystem side-effects isolated."""
    with (
        patch.object(gordon_mod, "is_kill_switch_active", return_value=kill_switch),
        patch.object(
            gordon_mod,
            "check_runtime_guard",
            return_value={"active": False, "status": guard_status, "pid": None, "path": ""},
        ),
        patch.object(gordon_mod, "log_gordon_event"),
    ):
        return check(result)


# ─────────────────────────── status OK ───────────────────────────


def test_check_returns_ok_when_no_issues():
    r = _patched_check(_result())
    assert r["status"] == "OK"


def test_check_ok_no_blocked_by():
    r = _patched_check(_result())
    assert r["blocked_by"] == []


def test_check_ok_no_warnings():
    r = _patched_check(_result())
    assert r["warnings"] == []


def test_check_contains_4_checks():
    r = _patched_check(_result())
    assert len(r["checks"]) == 4


def test_check_returns_timestamp():
    r = _patched_check(_result())
    assert "timestamp" in r and r["timestamp"]


def test_check_ok_with_normal_regime():
    r = _patched_check(_result(regime_label="NORMAL"))
    assert r["status"] == "OK"


# ─────────────────────────── kill switch ───────────────────────────


def test_check_blocked_by_kill_switch():
    r = _patched_check(_result(), kill_switch=True)
    assert r["status"] == "BLOCKED"
    assert "kill_switch_active" in r["blocked_by"]


def test_check_kill_switch_check_entry_failed():
    r = _patched_check(_result(), kill_switch=True)
    ks = next(c for c in r["checks"] if c["check"] == "kill_switch")
    assert ks["passed"] is False


# ─────────────────────────── DQ gate ───────────────────────────


def test_check_blocked_by_low_dq_score():
    r = _patched_check(_result(dq_score=0.50))
    assert r["status"] == "BLOCKED"
    assert any("dq_score" in b for b in r["blocked_by"])


def test_check_blocked_by_zero_dq_score():
    r = _patched_check(_result(dq_score=0.0))
    assert r["status"] == "BLOCKED"


def test_check_ok_at_dq_boundary():
    # exactly 0.60 must NOT block (condition is < 0.60)
    r = _patched_check(_result(dq_score=0.60))
    assert r["status"] == "OK"


def test_check_ok_when_dq_score_missing():
    # No data_quality key — dq_score is None, gate is skipped
    r = _patched_check({"stress": {"regime": {"label": "NORMAL"}}})
    assert r["status"] == "OK"


def test_check_ok_when_result_is_none():
    r = _patched_check(None)
    assert r["status"] == "OK"


# ─────────────────────────── runtime guard ───────────────────────────


def test_check_blocked_on_stale_lock():
    r = _patched_check(_result(), guard_status="stale_lock")
    assert r["status"] == "BLOCKED"
    assert "stale_engine_lock" in r["blocked_by"]


# ─────────────────────────── regime anomaly ───────────────────────────


def test_check_blocked_on_panic_regime():
    r = _patched_check(_result(regime_label="PANIC"))
    assert r["status"] == "BLOCKED"
    assert "regime_panic" in r["blocked_by"]


def test_check_alert_on_data_degraded_regime():
    r = _patched_check(_result(regime_label="DATA_DEGRADED"))
    assert r["status"] == "ALERT"
    assert "regime_DATA_DEGRADED" in r["warnings"]


# ─────────────────────────── combined ───────────────────────────


def test_check_blocked_takes_priority_over_alert():
    # kill switch (BLOCKED) + PANIC regime (BLOCKED) → must be BLOCKED
    r = _patched_check(_result(regime_label="PANIC"), kill_switch=True)
    assert r["status"] == "BLOCKED"


def test_check_blocked_logs_gordon_event():
    with (
        patch.object(gordon_mod, "is_kill_switch_active", return_value=True),
        patch.object(
            gordon_mod,
            "check_runtime_guard",
            return_value={"active": False, "status": "not_found", "pid": None, "path": ""},
        ),
        patch.object(gordon_mod, "log_gordon_event") as mock_log,
    ):
        check(_result())
    logged_types = [call.args[0] for call in mock_log.call_args_list]
    assert "gordon_check_blocked" in logged_types


# ─────────────────────────── engine integration ───────────────────────────


def test_engine_run_skips_ingest_when_gordon_blocked(tmp_path):
    """
    When GORDON returns BLOCKED, run_engine() must NOT call ingest_opportunities.
    """
    import engine as eng_mod

    fake_result = {**_result(dq_score=0.0), "errors": [], "meta": {}}

    with (
        patch.object(eng_mod, "_build_engine_result", return_value=fake_result),
        patch.object(eng_mod, "_enrich_runtime_metadata"),
        patch.object(eng_mod, "_persist_run"),
        patch.object(eng_mod, "ingest_opportunities") as mock_ingest,
        patch.object(eng_mod, "LOCK_FILE", tmp_path / "engine.lock"),
        patch.object(gordon_mod, "is_kill_switch_active", return_value=True),
        patch.object(
            gordon_mod,
            "check_runtime_guard",
            return_value={"active": False, "status": "not_found", "pid": None, "path": ""},
        ),
        patch.object(gordon_mod, "log_gordon_event"),
        patch.object(gordon_mod, "AUDIT_LOG_FILE", tmp_path / "gordon_audit.jsonl"),
    ):
        eng_mod.run_engine(MagicMock(equities=[], crypto=[]))

    mock_ingest.assert_not_called()


def test_engine_run_calls_ingest_when_gordon_ok(tmp_path):
    """When GORDON returns OK, ingest_opportunities must be called normally."""
    import engine as eng_mod

    fake_result = {**_result(dq_score=1.0), "errors": [], "meta": {}}

    with (
        patch.object(eng_mod, "_build_engine_result", return_value=fake_result),
        patch.object(eng_mod, "_enrich_runtime_metadata"),
        patch.object(eng_mod, "_persist_run"),
        patch.object(eng_mod, "ingest_opportunities") as mock_ingest,
        patch.object(eng_mod, "LOCK_FILE", tmp_path / "engine.lock"),
        patch.object(gordon_mod, "is_kill_switch_active", return_value=False),
        patch.object(
            gordon_mod,
            "check_runtime_guard",
            return_value={"active": False, "status": "not_found", "pid": None, "path": ""},
        ),
        patch.object(gordon_mod, "log_gordon_event"),
        patch.object(gordon_mod, "AUDIT_LOG_FILE", tmp_path / "gordon_audit.jsonl"),
    ):
        eng_mod.run_engine(MagicMock(equities=[], crypto=[]))

    mock_ingest.assert_called_once()
