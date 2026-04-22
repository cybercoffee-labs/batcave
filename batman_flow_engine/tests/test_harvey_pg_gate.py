"""
Tests for HARVEY → PostgreSQL sync gating via the shared availability state.

Before the 2026-04-21 unification HARVEY had no availability cache at all and
called save_opportunity unconditionally, creating divergent views of PG state
vs. dual_writer. These tests pin down the new behaviour:

  - If pg_available() is False, save_opportunity must NOT be called.
  - If pg_available() is True, save_opportunity is called per new record.
  - A save failure flips the shared state to unavailable and stops the loop.
"""

import time
from unittest.mock import patch


def _arm_harvey_with_single_record(tmp_path, record_json: str):
    """Write one record to a temp opportunities.jsonl and return patched paths."""
    test_db = tmp_path / "batman.db"
    test_log = tmp_path / "opportunities.jsonl"
    test_log.write_text(record_json + "\n", encoding="utf-8")
    return test_db, test_log


def test_harvey_skips_pg_sync_when_unavailable(tmp_path, caplog):
    """When PG is marked unavailable, HARVEY must not call save_opportunity."""
    import logging

    from core import harvey as h
    from database import postgres as pg

    test_db, test_log = _arm_harvey_with_single_record(
        tmp_path, '{"opp_id": "OPP-HARVEY-SKIP", "type": "C", "ts": "2026-04-21T00:00:00Z"}'
    )

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = False
    pg._pg_last_check_ts = time.monotonic()

    caplog.set_level(logging.INFO, logger="harvey")

    try:
        with (
            patch.object(h, "DB_PATH", test_db),
            patch.object(h, "OPPORTUNITIES_LOG", test_log),
            patch("database.postgres.save_opportunity") as mocked_save,
        ):
            result = h.ingest_opportunities()
            assert result["scanned"] == 1
            assert result["inserted"] == 1  # SQLite insert still happens
            mocked_save.assert_not_called()
            # HARVEY should emit a human-readable "deferred" log line.
            assert any("deferred" in r.getMessage() for r in caplog.records)
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts


def test_harvey_calls_pg_when_available(tmp_path):
    """When PG is available, HARVEY must call save_opportunity for each new record."""
    from core import harvey as h
    from database import postgres as pg

    test_db, test_log = _arm_harvey_with_single_record(
        tmp_path, '{"opp_id": "OPP-HARVEY-OK", "type": "C", "ts": "2026-04-21T00:00:00Z"}'
    )

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = True
    pg._pg_last_check_ts = time.monotonic()

    try:
        with (
            patch.object(h, "DB_PATH", test_db),
            patch.object(h, "OPPORTUNITIES_LOG", test_log),
            patch("database.postgres.save_opportunity", return_value=True) as mocked_save,
        ):
            result = h.ingest_opportunities()
            assert result["inserted"] == 1
            assert mocked_save.call_count == 1
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts


def test_harvey_save_failure_flips_shared_state(tmp_path):
    """A save failure in HARVEY must flip the shared _pg_available to False."""
    from core import harvey as h
    from database import postgres as pg

    test_db, test_log = _arm_harvey_with_single_record(
        tmp_path, '{"opp_id": "OPP-HARVEY-FAIL", "type": "C", "ts": "2026-04-21T00:00:00Z"}'
    )

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = True
    pg._pg_last_check_ts = time.monotonic()

    try:
        with (
            patch.object(h, "DB_PATH", test_db),
            patch.object(h, "OPPORTUNITIES_LOG", test_log),
            patch("database.postgres.save_opportunity", return_value=False),
        ):
            h.ingest_opportunities()
            # After a save returning False, shared state must be unavailable.
            assert pg._pg_available is False
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts
