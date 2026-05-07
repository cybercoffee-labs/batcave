"""Tests for tools/reconciliation_job.py (audit Section L.5)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _force_pg_unavailable(monkeypatch):
    """Reconciliation tests run against tmp JSONL + SQLite, not real PG.

    Force pg_available() to return False so the tests are deterministic
    on developer machines that happen to have a local PG running.
    """
    import database.postgres as pg

    with pg._pg_state_lock:
        pg._pg_available = False
        pg._pg_last_check_ts = None
    monkeypatch.setattr("database.postgres.pg_available", lambda: False)
    yield
    with pg._pg_state_lock:
        pg._pg_available = None
        pg._pg_last_check_ts = None


def _seed_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _seed_sqlite_signals(db_path, records):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY,
                opp_id TEXT UNIQUE,
                timestamp TEXT,
                cycle_id TEXT,
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
        for r in records:
            conn.execute(
                "INSERT INTO signals(opp_id, timestamp, scanner_id) VALUES (?, ?, ?)",
                (r["opp_id"], r["ts"], r.get("scanner_id", "S")),
            )
        conn.commit()
    finally:
        conn.close()


# ─────────────────────── happy paths ───────────────────────


def test_reconcile_returns_consistent_when_counts_match(tmp_path):
    """Two opps for today → JSONL=2, SQLite=2, PG unavailable. CONSISTENT."""
    from tools.reconciliation_job import reconcile_opportunities

    today = datetime.now(timezone.utc).date().isoformat()
    records = [
        {"opp_id": "OPP-A-1", "ts": f"{today}T10:00:00+00:00"},
        {"opp_id": "OPP-A-2", "ts": f"{today}T11:00:00+00:00"},
    ]

    jsonl = tmp_path / "opps.jsonl"
    db_path = tmp_path / "batman.db"
    _seed_jsonl(jsonl, records)
    _seed_sqlite_signals(db_path, records)

    report = reconcile_opportunities(jsonl_path=jsonl, sqlite_path=db_path)
    assert report["status"] == "CONSISTENT"
    assert report["jsonl_count"] == 2
    assert report["sqlite_count"] == 2
    assert report["pg_count"] is None  # PG unavailable in tests
    assert report["discrepancies"] == []


def test_reconcile_filters_by_target_date(tmp_path):
    from tools.reconciliation_job import reconcile_opportunities

    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (
        (datetime.now(timezone.utc).replace(hour=12) - __import__("datetime").timedelta(days=1)).date().isoformat()
    )
    records = [
        {"opp_id": "OPP-A-1", "ts": f"{today}T10:00:00+00:00"},
        {"opp_id": "OPP-A-2", "ts": f"{yesterday}T10:00:00+00:00"},
    ]
    jsonl = tmp_path / "opps.jsonl"
    db = tmp_path / "batman.db"
    _seed_jsonl(jsonl, records)
    _seed_sqlite_signals(db, records)

    # Only today's row should count.
    report = reconcile_opportunities(date_iso=today, jsonl_path=jsonl, sqlite_path=db)
    assert report["jsonl_count"] == 1
    assert report["sqlite_count"] == 1


def test_reconcile_explicit_date(tmp_path):
    from tools.reconciliation_job import reconcile_opportunities

    target = "2026-04-01"
    records = [{"opp_id": "OPP-X", "ts": f"{target}T10:00:00+00:00"}]
    jsonl = tmp_path / "opps.jsonl"
    db = tmp_path / "batman.db"
    _seed_jsonl(jsonl, records)
    _seed_sqlite_signals(db, records)

    report = reconcile_opportunities(date_iso=target, jsonl_path=jsonl, sqlite_path=db)
    assert report["date"] == target
    assert report["jsonl_count"] == 1
    assert report["sqlite_count"] == 1


# ─────────────────────── divergence ───────────────────────


def test_reconcile_diverges_when_jsonl_has_more_than_sqlite(tmp_path):
    from tools.reconciliation_job import reconcile_opportunities

    today = datetime.now(timezone.utc).date().isoformat()
    jsonl_records = [{"opp_id": f"OPP-A-{i}", "ts": f"{today}T10:00:00+00:00"} for i in range(3)]
    sqlite_records = [{"opp_id": "OPP-A-0", "ts": f"{today}T10:00:00+00:00"}]

    jsonl = tmp_path / "opps.jsonl"
    db = tmp_path / "batman.db"
    _seed_jsonl(jsonl, jsonl_records)
    _seed_sqlite_signals(db, sqlite_records)

    report = reconcile_opportunities(jsonl_path=jsonl, sqlite_path=db)
    assert report["status"] == "DIVERGED"
    assert report["jsonl_count"] == 3
    assert report["sqlite_count"] == 1
    assert any("JSONL" in d and "SQLite" in d for d in report["discrepancies"])


# ─────────────────────── resilience ───────────────────────


def test_reconcile_handles_missing_jsonl(tmp_path):
    from tools.reconciliation_job import reconcile_opportunities

    db = tmp_path / "batman.db"
    _seed_sqlite_signals(db, [])
    report = reconcile_opportunities(jsonl_path=tmp_path / "missing.jsonl", sqlite_path=db)
    assert report["jsonl_count"] == 0
    assert report["sqlite_count"] == 0
    assert report["status"] == "CONSISTENT"


def test_reconcile_handles_missing_sqlite(tmp_path):
    from tools.reconciliation_job import reconcile_opportunities

    jsonl = tmp_path / "opps.jsonl"
    _seed_jsonl(jsonl, [])
    report = reconcile_opportunities(jsonl_path=jsonl, sqlite_path=tmp_path / "missing.db")
    assert report["sqlite_count"] == 0


def test_reconcile_handles_missing_signals_table(tmp_path):
    """SQLite DB exists but the signals table is missing. Treat as 0 rows."""
    from tools.reconciliation_job import reconcile_opportunities

    db = tmp_path / "batman.db"
    sqlite3.connect(db).close()  # creates empty db file
    jsonl = tmp_path / "opps.jsonl"
    _seed_jsonl(jsonl, [])

    report = reconcile_opportunities(jsonl_path=jsonl, sqlite_path=db)
    assert report["sqlite_count"] == 0
    assert report["status"] == "CONSISTENT"


def test_reconcile_skips_malformed_jsonl_rows(tmp_path):
    """Malformed JSONL rows are skipped, not counted, not crashing."""
    from tools.reconciliation_job import reconcile_opportunities

    today = datetime.now(timezone.utc).date().isoformat()
    jsonl = tmp_path / "opps.jsonl"
    jsonl.write_text(
        json.dumps({"opp_id": "OK", "ts": f"{today}T10:00:00+00:00"})
        + "\n"
        + "this is not json\n"
        + json.dumps({"opp_id": "OK2", "ts": f"{today}T11:00:00+00:00"})
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "batman.db"
    _seed_sqlite_signals(
        db,
        [
            {"opp_id": "OK", "ts": f"{today}T10:00:00+00:00"},
            {"opp_id": "OK2", "ts": f"{today}T11:00:00+00:00"},
        ],
    )

    report = reconcile_opportunities(jsonl_path=jsonl, sqlite_path=db)
    assert report["jsonl_count"] == 2
    assert report["status"] == "CONSISTENT"


def test_reconcile_handles_records_without_ts(tmp_path):
    from tools.reconciliation_job import reconcile_opportunities

    today = datetime.now(timezone.utc).date().isoformat()
    jsonl = tmp_path / "opps.jsonl"
    _seed_jsonl(
        jsonl,
        [
            {"opp_id": "VALID", "ts": f"{today}T10:00:00+00:00"},
            {"opp_id": "NO-TS"},  # filtered out — no ts
        ],
    )
    db = tmp_path / "batman.db"
    _seed_sqlite_signals(db, [{"opp_id": "VALID", "ts": f"{today}T10:00:00+00:00"}])

    report = reconcile_opportunities(jsonl_path=jsonl, sqlite_path=db)
    assert report["jsonl_count"] == 1


def test_main_returns_one_on_divergence(tmp_path, monkeypatch, capsys):
    """The CLI exits non-zero when DIVERGED — cron / CI catch this."""
    from tools import reconciliation_job

    today = datetime.now(timezone.utc).date().isoformat()
    jsonl = tmp_path / "opps.jsonl"
    _seed_jsonl(jsonl, [{"opp_id": f"OPP-{i}", "ts": f"{today}T10:00:00+00:00"} for i in range(3)])
    db = tmp_path / "batman.db"
    _seed_sqlite_signals(db, [])

    monkeypatch.setattr(reconciliation_job, "OPPORTUNITIES_JSONL", jsonl)
    monkeypatch.setattr(reconciliation_job, "SQLITE_DB", db)

    rc = reconciliation_job.main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert "DIVERGED" in out


def test_main_returns_zero_on_consistent(tmp_path, monkeypatch):
    from tools import reconciliation_job

    today = datetime.now(timezone.utc).date().isoformat()
    jsonl = tmp_path / "opps.jsonl"
    _seed_jsonl(jsonl, [{"opp_id": "X", "ts": f"{today}T10:00:00+00:00"}])
    db = tmp_path / "batman.db"
    _seed_sqlite_signals(db, [{"opp_id": "X", "ts": f"{today}T10:00:00+00:00"}])

    monkeypatch.setattr(reconciliation_job, "OPPORTUNITIES_JSONL", jsonl)
    monkeypatch.setattr(reconciliation_job, "SQLITE_DB", db)

    rc = reconciliation_job.main([])
    assert rc == 0
