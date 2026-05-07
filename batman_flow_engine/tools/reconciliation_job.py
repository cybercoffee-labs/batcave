#!/usr/bin/env python3
"""
Batman Lab — Reconciliation Job (audit Section L.5)

Compare three sources of truth that should agree on the count of
opportunities for any given UTC day:

  1. JSONL    — storage/logs/opportunities.jsonl (append-only)
  2. SQLite   — storage/batman.db, table 'signals' (HARVEY)
  3. Postgres — opportunities table (cloud DB, optional)

A discrepancy means HARVEY's ingest dropped rows, dual_writer's PG path
silently lost rows, or the JSONL parse encountered malformed lines we
quietly skipped. The job emits a structured report and exits non-zero
on divergence so cron / CI can alert.

Day boundary uses UTC. The job operates on a single date (default:
today UTC) so a long-running engine doesn't see drift due to TZ
mismatches between the writers and the reader.

Public API:
    reconcile_opportunities(date_iso=None) -> dict
    main() -> int  (CLI entrypoint)

Report shape:
    {
        "timestamp": ISO-8601 of when the job ran,
        "date": "YYYY-MM-DD" (UTC),
        "jsonl_count": int,
        "sqlite_count": int,
        "pg_count": int | None,
        "discrepancies": list[str],
        "status": "CONSISTENT" | "DIVERGED" | "ERROR",
        "error": str (only on ERROR),
        "details": {
            "jsonl_path": str,
            "sqlite_path": str,
            "pg_used_cycle_id": bool,
        },
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Make project imports resolvable regardless of cwd.
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger("batman.reconciliation")

OPPORTUNITIES_JSONL = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
SQLITE_DB = BASE_DIR / "storage" / "batman.db"


def _today_utc_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _parse_ts_to_utc_date(value: Any) -> str | None:
    """Best-effort conversion of an opportunity row's timestamp into a UTC
    date string. Accepts both ISO-8601 datetimes and dates."""
    if value is None:
        return None
    s = str(value)
    try:
        # datetime.fromisoformat in 3.11+ accepts both dates and datetimes,
        # with or without explicit timezone.
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).date().isoformat()


def _count_jsonl_for_day(date_iso: str, path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSONL row at line %d", line_no)
                    continue
                if not isinstance(record, dict):
                    continue
                row_date = _parse_ts_to_utc_date(record.get("ts"))
                if row_date == date_iso:
                    count += 1
    except Exception as exc:
        logger.error("JSONL count failed: %s", exc, exc_info=True)
        return 0
    return count


def _count_sqlite_for_day(date_iso: str, db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "signals" not in tables:
                return 0
            (count,) = conn.execute(
                """
                SELECT COUNT(*) FROM signals
                WHERE substr(timestamp, 1, 10) = ?
                """,
                (date_iso,),
            ).fetchone()
            return int(count or 0)
    except Exception as exc:
        logger.error("SQLite count failed: %s", exc, exc_info=True)
        return 0


def _count_pg_for_day(date_iso: str) -> int | None:
    """Return the PG count for *date_iso* or None if PG is unavailable."""
    try:
        from database.postgres import get_cursor, pg_available
    except Exception as exc:
        logger.error("Cannot import database.postgres: %s", exc, exc_info=True)
        return None
    if not pg_available():
        logger.info("Reconciliation: PG unavailable, PG count skipped")
        return None
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM opportunities WHERE DATE(ts AT TIME ZONE 'UTC') = %s",
                (date_iso,),
            )
            (count,) = cur.fetchone()
            return int(count or 0)
    except Exception as exc:
        logger.error("PG count failed: %s", exc, exc_info=True)
        return None


def reconcile_opportunities(
    date_iso: str | None = None,
    jsonl_path: Path | None = None,
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    """Build a reconciliation report for *date_iso* (defaults to today UTC).

    *jsonl_path* / *sqlite_path* override the default storage locations
    (used by tests).
    """
    target_date = date_iso or _today_utc_iso()
    jsonl = jsonl_path if jsonl_path is not None else OPPORTUNITIES_JSONL
    sqlite_p = sqlite_path if sqlite_path is not None else SQLITE_DB

    report: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "date": target_date,
        "jsonl_count": 0,
        "sqlite_count": 0,
        "pg_count": None,
        "discrepancies": [],
        "status": "UNKNOWN",
        "details": {
            "jsonl_path": str(jsonl),
            "sqlite_path": str(sqlite_p),
            "pg_used_cycle_id": False,
        },
    }

    try:
        report["jsonl_count"] = _count_jsonl_for_day(target_date, jsonl)
        report["sqlite_count"] = _count_sqlite_for_day(target_date, sqlite_p)
        report["pg_count"] = _count_pg_for_day(target_date)
    except Exception as exc:
        logger.error("Reconciliation cycle failed: %s", exc, exc_info=True)
        report["status"] = "ERROR"
        report["error"] = str(exc)
        return report

    discrepancies: list[str] = []
    if report["jsonl_count"] != report["sqlite_count"]:
        discrepancies.append(f"JSONL ({report['jsonl_count']}) != SQLite signals ({report['sqlite_count']})")
    if report["pg_count"] is not None and report["pg_count"] != report["jsonl_count"]:
        discrepancies.append(f"JSONL ({report['jsonl_count']}) != PG opportunities ({report['pg_count']})")
    if report["pg_count"] is not None and report["pg_count"] != report["sqlite_count"]:
        discrepancies.append(f"SQLite signals ({report['sqlite_count']}) != PG opportunities ({report['pg_count']})")

    report["discrepancies"] = discrepancies
    report["status"] = "DIVERGED" if discrepancies else "CONSISTENT"

    if discrepancies:
        logger.error(
            "Reconciliation FAILED for %s: jsonl=%d sqlite=%d pg=%s — %s",
            target_date,
            report["jsonl_count"],
            report["sqlite_count"],
            report["pg_count"],
            "; ".join(discrepancies),
        )
    else:
        logger.info(
            "✓ Reconciliation OK for %s: jsonl=%d sqlite=%d pg=%s",
            target_date,
            report["jsonl_count"],
            report["sqlite_count"],
            report["pg_count"],
        )
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI: prints the report as JSON, exits non-zero on divergence/error."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Reconcile JSONL ↔ SQLite ↔ PG opportunity counts.")
    parser.add_argument(
        "--date",
        help="UTC date in YYYY-MM-DD (default: today UTC)",
        default=None,
    )
    args = parser.parse_args(argv)

    report = reconcile_opportunities(date_iso=args.date)
    print(json.dumps(report, indent=2, default=str))
    if report["status"] in ("DIVERGED", "ERROR"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
