"""
Tests for commander_decision() — COMMANDER gate in engine.py.

Covers:
  - viable=True when all three gates pass
  - viable=False when any gate fails (alfred_dq, gordon_ok, harvey_init)
  - blocked_by content for each failure
  - combined multi-gate failures
  - run_engine integration: ingest called only when viable
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


import engine as eng_mod
from engine import commander_decision, _harvey_is_initialized


# ─────────────────────────── helpers ───────────────────────────


def _result(dq_score=1.0, gordon_status="OK"):
    return {
        "data_quality": {"dq_score": dq_score, "status": "ok"},
        "gordon": {"status": gordon_status, "blocked_by": [], "warnings": []},
        "stress": {"regime": {"label": "NORMAL", "triggers": []}},
    }


def _decide(dq_score=1.0, gordon_status="OK", harvey_init=True):
    with patch.object(eng_mod, "_harvey_is_initialized", return_value=harvey_init):
        return commander_decision(_result(dq_score=dq_score, gordon_status=gordon_status))


# ─────────────────────────── viable=True ───────────────────────────


def test_viable_when_all_gates_pass():
    r = _decide()
    assert r["viable"] is True


def test_viable_has_empty_blocked_by():
    r = _decide()
    assert r["blocked_by"] == []


def test_viable_has_three_gates():
    r = _decide()
    assert len(r["gates"]) == 3


def test_viable_all_gates_passed_true():
    r = _decide()
    assert all(g["passed"] for g in r["gates"])


def test_viable_returns_timestamp():
    r = _decide()
    assert "timestamp" in r and r["timestamp"]


def test_viable_at_dq_boundary():
    # exactly 0.80 must pass (condition is < 0.80)
    r = _decide(dq_score=0.80)
    assert r["viable"] is True


# ─────────────────────────── Gate 1: alfred_dq ───────────────────────────


def test_blocked_when_dq_below_threshold():
    r = _decide(dq_score=0.79)
    assert r["viable"] is False
    assert any("alfred_dq" in b for b in r["blocked_by"])


def test_blocked_when_dq_zero():
    r = _decide(dq_score=0.0)
    assert r["viable"] is False


def test_blocked_when_dq_missing():
    result = {
        "data_quality": {},
        "gordon": {"status": "OK"},
    }
    with patch.object(eng_mod, "_harvey_is_initialized", return_value=True):
        r = commander_decision(result)
    assert r["viable"] is False
    assert "alfred_dq_score_missing" in r["blocked_by"]


def test_alfred_gate_entry_when_blocked():
    r = _decide(dq_score=0.60)
    gate = next(g for g in r["gates"] if g["gate"] == "alfred_dq")
    assert gate["passed"] is False
    assert gate["dq_score"] == 0.60


# ─────────────────────────── Gate 2: gordon_ok ───────────────────────────


def test_blocked_when_gordon_alert():
    r = _decide(gordon_status="ALERT")
    assert r["viable"] is False
    assert "gordon_status_ALERT" in r["blocked_by"]


def test_blocked_when_gordon_blocked():
    r = _decide(gordon_status="BLOCKED")
    assert r["viable"] is False
    assert "gordon_status_BLOCKED" in r["blocked_by"]


def test_blocked_when_gordon_none():
    result = {"data_quality": {"dq_score": 1.0}, "gordon": None}
    with patch.object(eng_mod, "_harvey_is_initialized", return_value=True):
        r = commander_decision(result)
    assert r["viable"] is False
    assert any("gordon_status" in b for b in r["blocked_by"])


def test_gordon_gate_entry_when_blocked():
    r = _decide(gordon_status="ALERT")
    gate = next(g for g in r["gates"] if g["gate"] == "gordon_ok")
    assert gate["passed"] is False
    assert gate["gordon_status"] == "ALERT"


# ─────────────────────────── Gate 3: harvey_init ───────────────────────────


def test_blocked_when_harvey_not_initialized():
    r = _decide(harvey_init=False)
    assert r["viable"] is False
    assert "harvey_db_not_initialized" in r["blocked_by"]


def test_harvey_gate_entry_when_blocked():
    r = _decide(harvey_init=False)
    gate = next(g for g in r["gates"] if g["gate"] == "harvey_init")
    assert gate["passed"] is False


def test_harvey_gate_passed_when_initialized():
    r = _decide()
    gate = next(g for g in r["gates"] if g["gate"] == "harvey_init")
    assert gate["passed"] is True


# ─────────────────────────── combined failures ───────────────────────────


def test_all_three_gates_fail():
    r = _decide(dq_score=0.5, gordon_status="ALERT", harvey_init=False)
    assert r["viable"] is False
    assert len(r["blocked_by"]) == 3


def test_two_gates_fail_dq_and_harvey():
    r = _decide(dq_score=0.5, gordon_status="OK", harvey_init=False)
    assert r["viable"] is False
    assert len(r["blocked_by"]) == 2


# ─────────────────────────── _harvey_is_initialized unit ───────────────────────────


def test_harvey_not_initialized_when_db_missing(tmp_path):
    with patch.object(eng_mod, "HARVEY_DB_PATH", tmp_path / "nonexistent.db"):
        assert _harvey_is_initialized() is False


def test_harvey_not_initialized_when_table_missing(tmp_path):
    import sqlite3

    db = tmp_path / "batman.db"
    sqlite3.connect(db).close()  # empty DB, no tables
    with patch.object(eng_mod, "HARVEY_DB_PATH", db):
        assert _harvey_is_initialized() is False


def test_harvey_initialized_when_signals_table_exists(tmp_path):
    import sqlite3

    db = tmp_path / "batman.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY)")
    with patch.object(eng_mod, "HARVEY_DB_PATH", db):
        assert _harvey_is_initialized() is True


# ─────────────────────────── run_engine integration ───────────────────────────


def _base_result():
    return {
        "data_quality": {"dq_score": 1.0, "status": "ok"},
        "gordon": {"status": "OK", "blocked_by": [], "warnings": []},
        "stress": {"regime": {"label": "NORMAL", "triggers": []}},
        "errors": [],
        "meta": {},
    }


def test_ingest_called_when_commander_viable(tmp_path):
    import core.gordon as gordon_mod

    with (
        patch.object(eng_mod, "_build_engine_result", return_value=_base_result()),
        patch.object(eng_mod, "_enrich_runtime_metadata"),
        patch.object(eng_mod, "_persist_run"),
        patch.object(eng_mod, "_harvey_is_initialized", return_value=True),
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


def test_ingest_skipped_when_commander_blocked_by_dq(tmp_path):
    import core.gordon as gordon_mod

    fake = {**_base_result(), "data_quality": {"dq_score": 0.70, "status": "partial"}}

    with (
        patch.object(eng_mod, "_build_engine_result", return_value=fake),
        patch.object(eng_mod, "_enrich_runtime_metadata"),
        patch.object(eng_mod, "_persist_run"),
        patch.object(eng_mod, "_harvey_is_initialized", return_value=True),
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
        result = eng_mod.run_engine(MagicMock(equities=[], crypto=[]))

    mock_ingest.assert_not_called()
    assert result["commander"]["viable"] is False


def test_commander_result_stored_in_engine_output(tmp_path):
    import core.gordon as gordon_mod

    with (
        patch.object(eng_mod, "_build_engine_result", return_value=_base_result()),
        patch.object(eng_mod, "_enrich_runtime_metadata"),
        patch.object(eng_mod, "_persist_run"),
        patch.object(eng_mod, "_harvey_is_initialized", return_value=True),
        patch.object(eng_mod, "ingest_opportunities"),
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
        result = eng_mod.run_engine(MagicMock(equities=[], crypto=[]))

    assert "commander" in result
    assert "viable" in result["commander"]
    assert "gates" in result["commander"]
