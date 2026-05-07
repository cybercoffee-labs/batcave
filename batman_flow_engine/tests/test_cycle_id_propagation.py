"""Integration tests for cycle_id propagation (audit Section C #9).

End-to-end: scanner _append_to_log → JSONL → HARVEY ingest → SQLite.
Also covers dual_writer's stamping path and the engine result dict.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_cycle_context():
    from core.cycle_context import clear_current_cycle_id

    clear_current_cycle_id()
    yield
    clear_current_cycle_id()


@pytest.fixture(autouse=True)
def _reset_pg_state():
    """Each test gets a clean PG availability cache."""
    import database.postgres as pg

    with pg._pg_state_lock:
        pg._pg_available = None
        pg._pg_last_check_ts = None
    yield
    with pg._pg_state_lock:
        pg._pg_available = None
        pg._pg_last_check_ts = None


# ─────────────────────── scanner _append_to_log ───────────────────────


def test_scanner_append_to_log_stamps_cycle_id(tmp_path, monkeypatch):
    """Each scanner's _append_to_log must stamp cycle_id from context."""
    from core.cycle_context import set_current_cycle_id

    set_current_cycle_id("abc123def456")

    log_file = tmp_path / "opportunities.jsonl"

    # Patch the LOG_FILE constant in cross_exchange and call _append_to_log directly.
    import core.scanner_cross_exchange as scanner

    monkeypatch.setattr(scanner, "LOG_FILE", log_file)

    opp = {"opp_id": "OPP-A-TEST", "type": "A", "asset": "BTC"}
    assert scanner._append_to_log(opp) is True
    assert opp["cycle_id"] == "abc123def456"

    # Round-trip: read the JSONL line, confirm cycle_id is persisted.
    line = log_file.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["cycle_id"] == "abc123def456"


def test_basis_scanner_stamps_cycle_id(tmp_path, monkeypatch):
    from core.cycle_context import set_current_cycle_id

    set_current_cycle_id("basisid12345")

    log_file = tmp_path / "opps.jsonl"
    import core.scanner_basis as scanner

    monkeypatch.setattr(scanner, "LOG_FILE", log_file)

    opp = {"opp_id": "OPP-B-TEST", "type": "B"}
    assert scanner._append_to_log(opp) is True
    assert opp["cycle_id"] == "basisid12345"


# ─────────────────────── dual_writer ───────────────────────


def test_dual_writer_stamps_cycle_id_on_jsonl(tmp_path, monkeypatch):
    """dual_writer.log_opportunity must stamp cycle_id (defense-in-depth)."""
    from core.cycle_context import set_current_cycle_id

    set_current_cycle_id("dwid12345abc")

    log_file = tmp_path / "opps.jsonl"
    import core.dual_writer as dw

    monkeypatch.setattr(dw, "LOG_FILE", log_file)

    # Force PG off to keep this test pure.
    with patch("database.postgres.pg_available", return_value=False):
        opp = {"opp_id": "OPP-DW-TEST", "type": "C"}
        result = dw.log_opportunity(opp)
        assert result["jsonl_ok"] is True
        assert result["pg_ok"] is None  # PG skipped

    line = log_file.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["cycle_id"] == "dwid12345abc"


# ─────────────────────── HARVEY signals ───────────────────────


def test_harvey_persists_cycle_id_to_signals_table(tmp_path, monkeypatch):
    """HARVEY ingest must write cycle_id into signals table."""
    import core.harvey as harvey

    # Redirect HARVEY's DB and JSONL paths into the tmp dir.
    db_path = tmp_path / "batman.db"
    log_path = tmp_path / "opps.jsonl"
    monkeypatch.setattr(harvey, "DB_PATH", db_path)
    monkeypatch.setattr(harvey, "OPPORTUNITIES_LOG", log_path)

    # Seed JSONL with one opportunity carrying a cycle_id.
    opp = {
        "opp_id": "OPP-HARV-TEST",
        "ts": "2026-05-04T10:00:00+00:00",
        "cycle_id": "harveyid1234",
        "scanner_id": "A-CROSS",
        "type": "A",
        "asset": "BTC",
        "venue": "binance_vs_okx",
        "edge_net": 0.42,
        "observe_only": True,
    }
    log_path.write_text(json.dumps(opp) + "\n", encoding="utf-8")

    # Force PG off so HARVEY's ingest_opportunities only writes SQLite.
    with patch("database.postgres.pg_available", return_value=False):
        result = harvey.ingest_opportunities()

    assert result["scanned"] == 1
    assert result["inserted"] == 1

    # Verify the cycle_id round-trip in SQLite.
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        assert "cycle_id" in cols, "Schema migration did not add cycle_id column"
        row = conn.execute("SELECT opp_id, cycle_id FROM signals").fetchone()
        assert row == ("OPP-HARV-TEST", "harveyid1234")
    finally:
        conn.close()


def test_harvey_handles_legacy_signals_table_without_cycle_id(tmp_path, monkeypatch):
    """If a pre-existing batman.db lacks cycle_id, HARVEY should ALTER TABLE."""
    import core.harvey as harvey

    db_path = tmp_path / "batman.db"
    log_path = tmp_path / "opps.jsonl"
    monkeypatch.setattr(harvey, "DB_PATH", db_path)
    monkeypatch.setattr(harvey, "OPPORTUNITIES_LOG", log_path)

    # Pre-create an old-style signals table (no cycle_id column).
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY,
                opp_id TEXT UNIQUE,
                timestamp TEXT,
                scanner_id TEXT,
                type TEXT,
                asset TEXT,
                venue TEXT,
                edge REAL,
                observe_only INTEGER,
                raw_json TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Empty JSONL (we only care about migration here).
    log_path.write_text("", encoding="utf-8")

    with patch("database.postgres.pg_available", return_value=False):
        harvey.ingest_opportunities()

    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        assert "cycle_id" in cols
    finally:
        conn.close()


# ─────────────────────── engine context propagation ───────────────────────


def test_current_cycle_opportunities_stamps_cycle_id_on_unstamped_dicts():
    """Opportunities returned by scanners that didn't stamp themselves get
    stamped centrally in engine._current_cycle_opportunities."""
    from core.cycle_context import set_current_cycle_id
    from engine import _current_cycle_opportunities

    set_current_cycle_id("centralid123")

    # A scanner that returned a list of dicts (e.g. dex / cross-exchange shape).
    raw = [
        {"opp_id": "OPP-X-1", "type": "X"},
        {"opp_id": "OPP-X-2", "type": "X", "cycle_id": "preset_id_99"},
    ]
    opps = _current_cycle_opportunities([raw])
    assert opps[0]["cycle_id"] == "centralid123"
    # Pre-existing cycle_id is preserved (idempotent stamp).
    assert opps[1]["cycle_id"] == "preset_id_99"
