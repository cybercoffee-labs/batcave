"""
Batman Lab — Startup Health Check (audit Section C #8)

Fail-fast validation that runs BEFORE the first engine cycle. If any check
fails, the run loop refuses to start. This prevents two whole classes of
silent corruption:

  1. PostgreSQL is unreachable but the engine quietly falls back to SQLite,
     leaving HARVEY's dual-write divergent for hours before anyone notices.
  2. PostgreSQL schema has drifted (missing columns) but writes succeed
     against half-correct rows, polluting reconciliation.

We ALSO probe ALFRED so a corrupt opportunities.jsonl or missing storage
directory aborts before scanners run rather than crashing mid-cycle.

Public API:
    run_all_checks() -> bool
    check_pg_reachable() -> bool
    check_schema_parity() -> bool
    check_alfred_ready() -> bool

CLI:
    python -m core.startup_check
        Exit 0 on green, exit 1 on any failure.
"""

from __future__ import annotations

import logging
import sys
from typing import Dict, Iterable

logger = logging.getLogger("batman.startup_check")

# Columns each consumer relies on. Keep this list narrow — the goal is to
# detect drift, not to be exhaustive. Adding optional analytics columns to
# the DB should NOT break startup.
EXPECTED_OPPORTUNITY_COLUMNS = {
    "id",
    "opp_id",
    "ts",
    "cycle_id",  # audit Section C #9
    "scanner_type",
    "scanner_id",
    "asset",
    "edge_net",
    "viable",
}

EXPECTED_ENGINE_RUN_COLUMNS = {
    "id",
    "ts",
    "cycle_id",  # audit Section C #9
    "duration_sec",
}

EXPECTED_TRADE_COLUMNS = {
    "id",
    "trade_id",
    "ts",
    "asset",
    "side",
    "price",
    "quantity",
}


def _fetch_pg_columns(table_name: str) -> set[str] | None:
    """Return the set of column names for a PG table, or None on error."""
    try:
        from database.postgres import get_cursor

        with get_cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table_name,),
            )
            rows = cur.fetchall()
            return {row[0] for row in rows}
    except Exception as exc:
        logger.error("Cannot inspect PG table '%s': %s", table_name, exc, exc_info=True)
        return None


def check_pg_reachable() -> bool:
    """
    Verify PostgreSQL is reachable RIGHT NOW.

    Forces a probe (does not trust the cached pg_available state). On a
    cold process the cache is None anyway, but this also catches the case
    where mark_pg_unavailable was set somewhere else and the run loop
    re-imports the module.
    """
    try:
        from database.postgres import pg_probe

        ok = pg_probe()
        if ok:
            logger.info("✓ PostgreSQL reachable")
            return True
        logger.error("✗ PostgreSQL not reachable. Check BATMAN_DB_HOST/PORT and that the server is running.")
        return False
    except Exception as exc:
        logger.error("✗ PG reachability probe raised: %s", exc, exc_info=True)
        return False


def _missing_columns(actual: set[str], expected: set[str]) -> set[str]:
    return expected - actual


def check_schema_parity() -> bool:
    """
    Verify the three canonical PG tables (opportunities, engine_runs, trades)
    contain the columns the engine will write to. Drift is fatal; the engine
    refuses to start rather than silently writing nulls.
    """
    # If PG isn't reachable, we cannot meaningfully check schema. Surface
    # the real failure (pg_reachable) instead of a false-positive schema error.
    try:
        from database.postgres import pg_available

        if not pg_available():
            logger.error("✗ Schema parity skipped: PG not reachable")
            return False
    except Exception as exc:
        logger.error("✗ Schema parity: cannot import pg_available: %s", exc, exc_info=True)
        return False

    checks: Iterable[tuple[str, set[str]]] = (
        ("opportunities", EXPECTED_OPPORTUNITY_COLUMNS),
        ("engine_runs", EXPECTED_ENGINE_RUN_COLUMNS),
        ("trades", EXPECTED_TRADE_COLUMNS),
    )

    all_ok = True
    for table_name, expected in checks:
        actual = _fetch_pg_columns(table_name)
        if actual is None:
            logger.error("✗ Schema parity: cannot read columns for '%s'", table_name)
            all_ok = False
            continue
        if not actual:
            logger.error("✗ Schema parity: table '%s' does not exist", table_name)
            all_ok = False
            continue
        missing = _missing_columns(actual, expected)
        if missing:
            logger.error(
                "✗ Schema parity: table '%s' missing columns: %s",
                table_name,
                sorted(missing),
            )
            all_ok = False
        else:
            logger.info("✓ Schema parity: %s (%d cols, all expected present)", table_name, len(actual))
    return all_ok


def check_alfred_ready() -> bool:
    """
    Verify ALFRED can run. We don't enforce a minimum dq_score here — that's
    a per-cycle gate. We only check that ALFRED's machinery is wired up and
    can be invoked without raising.
    """
    try:
        from core.alfred import run_quality_check

        result = run_quality_check(n_records=10)
        if not isinstance(result, dict):
            logger.error("✗ ALFRED returned unexpected type: %s", type(result).__name__)
            return False
        logger.info(
            "✓ ALFRED ready (records inspected=%s, dq_score=%s)",
            result.get("records_checked", "?"),
            result.get("dq_score", "?"),
        )
        return True
    except Exception as exc:
        logger.error("✗ ALFRED probe failed: %s", exc, exc_info=True)
        return False


def run_all_checks() -> bool:
    """
    Run every startup check. Returns True only if ALL pass.

    Order matters: PG reachable first (cheapest, most informative on
    failure). Schema parity depends on PG. ALFRED is independent.
    """
    checks = (
        ("PostgreSQL reachable", check_pg_reachable),
        ("Schema parity", check_schema_parity),
        ("ALFRED ready", check_alfred_ready),
    )

    results: Dict[str, bool] = {}
    for name, fn in checks:
        try:
            results[name] = fn()
        except Exception as exc:
            logger.error("Unexpected error in startup check '%s': %s", name, exc, exc_info=True)
            results[name] = False

    if all(results.values()):
        logger.info("=" * 70)
        logger.info("✓ ALL STARTUP CHECKS PASSED")
        logger.info("=" * 70)
        return True

    failed = [name for name, ok in results.items() if not ok]
    logger.error("=" * 70)
    logger.error("✗ STARTUP CHECKS FAILED: %s", ", ".join(failed))
    logger.error("=" * 70)
    return False


def main() -> int:
    """CLI entry point: exit 0 on green, exit 1 on any failure."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return 0 if run_all_checks() else 1


if __name__ == "__main__":
    sys.exit(main())
