"""Tests for dual writer module.

As of 2026-04-21 the PG availability state is owned by `database.postgres`.
These tests poke that canonical state directly (not a per-module cache).
"""

from unittest.mock import patch


def test_dual_writer_imports():
    from core.dual_writer import log_engine_run, log_opportunity, log_scanner_run

    assert callable(log_opportunity)
    assert callable(log_scanner_run)
    assert callable(log_engine_run)


def test_log_opportunity_writes_jsonl(tmp_path):
    """Should write to JSONL even if PostgreSQL is unavailable; return structured result."""
    import json
    import time

    from core.dual_writer import log_opportunity
    from database import postgres as pg

    log_file = tmp_path / "test.jsonl"

    # Force PG into "known unavailable, within retry window" so pg_available()
    # returns False without probing.
    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = False
    pg._pg_last_check_ts = time.monotonic()
    try:
        with patch("core.dual_writer.LOG_FILE", log_file):
            opp = {"opp_id": "TEST-001", "type": "C", "edge_net": 0.5, "viable": True}
            result = log_opportunity(opp)
            assert isinstance(result, dict)
            assert result["jsonl_ok"] is True
            assert result["pg_ok"] is None  # PG skipped (unavailable)
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts

    content = log_file.read_text().strip()
    parsed = json.loads(content)
    assert parsed["opp_id"] == "TEST-001"


def test_pg_available_caches_result():
    """PostgreSQL availability is cached within the retry window (no re-probe)."""
    import time

    from database import postgres as pg
    from database.postgres import pg_available

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    try:
        now = time.monotonic()

        pg._pg_available = True
        pg._pg_last_check_ts = now
        assert pg_available() is True

        pg._pg_available = False
        pg._pg_last_check_ts = now  # within retry window → no re-probe
        assert pg_available() is False
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts


def test_log_opportunity_returns_pg_false_when_save_fails():
    """When PG is believed up and save_opportunity returns False, pg_ok must be False."""
    import time

    from core.dual_writer import log_opportunity
    from database import postgres as pg

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    pg._pg_available = True
    pg._pg_last_check_ts = time.monotonic()
    try:
        with patch("database.postgres.save_opportunity", return_value=False):
            opp = {"opp_id": "TEST-FAIL", "type": "C"}
            result = log_opportunity(opp, log_to_file=False)
            assert result["jsonl_ok"] is True  # log_to_file=False is treated as ok
            assert result["pg_ok"] is False
            # Failure must also flip the shared state to unavailable.
            assert pg._pg_available is False
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts


def test_mark_pg_unavailable_triggers_backoff():
    """A write failure must flip _pg_available to False and set a timestamp."""
    from database import postgres as pg
    from database.postgres import mark_pg_unavailable

    previous_available = pg._pg_available
    previous_ts = pg._pg_last_check_ts
    try:
        pg._pg_available = True
        pg._pg_last_check_ts = None
        mark_pg_unavailable("test")
        assert pg._pg_available is False
        assert pg._pg_last_check_ts is not None
    finally:
        pg._pg_available = previous_available
        pg._pg_last_check_ts = previous_ts
