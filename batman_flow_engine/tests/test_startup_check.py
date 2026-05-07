"""Tests for core/startup_check.py (audit Section C #8 — startup health check)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest


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


# ─────────────────────── check_pg_reachable ───────────────────────


def test_check_pg_reachable_returns_true_when_probe_ok():
    from core.startup_check import check_pg_reachable

    with patch("database.postgres.check_connection", return_value={"status": "ok"}):
        assert check_pg_reachable() is True


def test_check_pg_reachable_returns_false_when_probe_fails():
    from core.startup_check import check_pg_reachable

    with patch("database.postgres.check_connection", return_value={"status": "error", "error": "down"}):
        assert check_pg_reachable() is False


def test_check_pg_reachable_returns_false_when_probe_raises(caplog):
    from core.startup_check import check_pg_reachable

    with patch("database.postgres.check_connection", side_effect=ConnectionError("nope")):
        assert check_pg_reachable() is False


# ─────────────────────── check_schema_parity ───────────────────────


def _fake_cursor(column_map: dict[str, list[str]]):
    """Build a context manager mimicking database.postgres.get_cursor()."""

    class _Cur:
        def __init__(self, cols_by_table):
            self._cols_by_table = cols_by_table
            self._buffer: list[tuple[str]] = []

        def execute(self, sql, params):
            table = params[0]
            self._buffer = [(c,) for c in self._cols_by_table.get(table, [])]

        def fetchall(self):
            return list(self._buffer)

    @contextmanager
    def _cm():
        yield _Cur(column_map)

    return _cm


def test_check_schema_parity_passes_when_all_columns_present():
    from core.startup_check import (
        EXPECTED_ENGINE_RUN_COLUMNS,
        EXPECTED_OPPORTUNITY_COLUMNS,
        EXPECTED_TRADE_COLUMNS,
        check_schema_parity,
    )

    fake_columns = {
        "opportunities": list(EXPECTED_OPPORTUNITY_COLUMNS) + ["extra_col"],
        "engine_runs": list(EXPECTED_ENGINE_RUN_COLUMNS),
        "trades": list(EXPECTED_TRADE_COLUMNS),
    }
    with (
        patch("database.postgres.pg_available", return_value=True),
        patch("core.startup_check.get_cursor", new=_fake_cursor(fake_columns), create=True),
        patch("database.postgres.get_cursor", new=_fake_cursor(fake_columns)),
    ):
        assert check_schema_parity() is True


def test_check_schema_parity_fails_when_pg_unreachable():
    from core.startup_check import check_schema_parity

    with patch("database.postgres.pg_available", return_value=False):
        assert check_schema_parity() is False


def test_check_schema_parity_fails_when_table_missing():
    from core.startup_check import check_schema_parity

    fake_columns = {"opportunities": [], "engine_runs": [], "trades": []}
    with (
        patch("database.postgres.pg_available", return_value=True),
        patch("database.postgres.get_cursor", new=_fake_cursor(fake_columns)),
    ):
        assert check_schema_parity() is False


def test_check_schema_parity_fails_when_column_missing():
    from core.startup_check import (
        EXPECTED_OPPORTUNITY_COLUMNS,
        check_schema_parity,
    )

    # Drop opp_id from opportunities; opportunities should now fail.
    opps_cols = [c for c in EXPECTED_OPPORTUNITY_COLUMNS if c != "opp_id"]
    fake_columns = {
        "opportunities": opps_cols,
        "engine_runs": ["id", "ts", "duration_sec"],
        "trades": ["id", "trade_id", "ts", "asset", "side", "price", "quantity"],
    }
    with (
        patch("database.postgres.pg_available", return_value=True),
        patch("database.postgres.get_cursor", new=_fake_cursor(fake_columns)),
    ):
        assert check_schema_parity() is False


# ─────────────────────── check_alfred_ready ───────────────────────


def test_check_alfred_ready_returns_true_on_dict():
    from core.startup_check import check_alfred_ready

    fake_report = {"records_checked": 5, "dq_score": 0.95}
    with patch("core.alfred.run_quality_check", return_value=fake_report):
        assert check_alfred_ready() is True


def test_check_alfred_ready_returns_false_on_non_dict():
    from core.startup_check import check_alfred_ready

    with patch("core.alfred.run_quality_check", return_value=None):
        assert check_alfred_ready() is False


def test_check_alfred_ready_returns_false_on_exception():
    from core.startup_check import check_alfred_ready

    with patch("core.alfred.run_quality_check", side_effect=RuntimeError("alfred broken")):
        assert check_alfred_ready() is False


# ─────────────────────── run_all_checks ───────────────────────


def test_run_all_checks_returns_true_when_everything_passes():
    from core.startup_check import run_all_checks

    with (
        patch("core.startup_check.check_pg_reachable", return_value=True),
        patch("core.startup_check.check_schema_parity", return_value=True),
        patch("core.startup_check.check_alfred_ready", return_value=True),
    ):
        assert run_all_checks() is True


def test_run_all_checks_returns_false_when_any_fails():
    from core.startup_check import run_all_checks

    with (
        patch("core.startup_check.check_pg_reachable", return_value=True),
        patch("core.startup_check.check_schema_parity", return_value=False),
        patch("core.startup_check.check_alfred_ready", return_value=True),
    ):
        assert run_all_checks() is False


def test_run_all_checks_runs_every_check_even_when_one_raises():
    """A check raising should not short-circuit the others."""
    from core.startup_check import run_all_checks

    pg = patch("core.startup_check.check_pg_reachable", return_value=True)
    schema = patch(
        "core.startup_check.check_schema_parity",
        side_effect=RuntimeError("kaboom"),
    )
    alfred_called = {"hit": False}

    def _alfred():
        alfred_called["hit"] = True
        return True

    alfred = patch("core.startup_check.check_alfred_ready", new=_alfred)
    with pg, schema, alfred:
        assert run_all_checks() is False
    assert alfred_called["hit"] is True


def test_main_returns_zero_on_pass():
    from core.startup_check import main

    with patch("core.startup_check.run_all_checks", return_value=True):
        assert main() == 0


def test_main_returns_one_on_fail():
    from core.startup_check import main

    with patch("core.startup_check.run_all_checks", return_value=False):
        assert main() == 1
