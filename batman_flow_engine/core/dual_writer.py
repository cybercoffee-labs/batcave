"""
Batman Lab — Dual Writer
Writes opportunities to BOTH .jsonl (legacy) AND PostgreSQL (new).
Drop-in replacement for _append_to_log in all scanners.

Return contract (unchanged since 2026-04-20):
  log_opportunity / log_scanner_run / log_engine_run all return a dict:
    {"jsonl_ok": bool, "pg_ok": bool | None}
  - jsonl_ok: True iff the legacy-disk write succeeded (only applies to
              log_opportunity; always True for log_scanner_run /
              log_engine_run which have no JSONL channel).
  - pg_ok:    True iff PostgreSQL wrote successfully.
              False iff PG was believed available but the write failed.
              None if PG was skipped because it is not currently available.
  Callers MUST inspect these fields — do not rely on truthiness.

PG availability is NOT managed here (2026-04-21 unification). It lives in
database.postgres so dual_writer, HARVEY, the engine risk-scores block,
and future tools all observe a single consistent state. See
`database/postgres.py::pg_available / mark_pg_unavailable`.

Usage in scanners:
  from core.dual_writer import log_opportunity, log_scanner_run

  # Instead of _append_to_log(opp):
  log_opportunity(opp)

  # At end of scanner:
  log_scanner_run("C", "P2P LATAM", duration, found, viable)
"""

import json
import logging
from pathlib import Path
from typing import Optional, TypedDict

logger = logging.getLogger("batman.writer")

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"


class PersistResult(TypedDict):
    jsonl_ok: bool
    pg_ok: Optional[bool]


def log_opportunity(opp: dict, log_to_file: bool = True) -> PersistResult:
    """Write opportunity to JSONL + PostgreSQL. See module docstring for contract."""
    jsonl_ok = False
    pg_ok: Optional[bool] = None

    # 1. Always write to JSONL (legacy, reliable).
    if log_to_file:
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(opp, default=str) + "\n")
            jsonl_ok = True
        except Exception as e:
            logger.error("JSONL write failed: %s", e, exc_info=True)
    else:
        jsonl_ok = True  # caller opted out — treat as ok

    # 2. Also write to PostgreSQL, gated on the shared availability state.
    from database.postgres import mark_pg_unavailable, pg_available, save_opportunity

    if pg_available():
        try:
            if save_opportunity(opp):
                pg_ok = True
            else:
                pg_ok = False
                logger.error(
                    "PostgreSQL save_opportunity returned False for opp=%s (JSONL still saved)",
                    opp.get("opp_id", "unknown"),
                )
                mark_pg_unavailable("save_opportunity returned False")
        except Exception as e:
            pg_ok = False
            logger.error("PostgreSQL write failed (JSONL still saved): %s", e, exc_info=True)
            mark_pg_unavailable(f"save_opportunity raised {type(e).__name__}", exc=e)

    return {"jsonl_ok": jsonl_ok, "pg_ok": pg_ok}


def log_scanner_run(
    scanner_type: str,
    scanner_name: str,
    duration_sec: float,
    opps_found: int,
    viable_found: int,
    errors: int = 0,
    status: str = "ok",
    error_msg: str = None,
) -> PersistResult:
    """Log scanner execution to PostgreSQL. See module docstring for contract."""
    from database.postgres import log_scanner_run as pg_log
    from database.postgres import mark_pg_unavailable, pg_available

    pg_ok: Optional[bool] = None
    if pg_available():
        try:
            if pg_log(
                scanner_type,
                scanner_name,
                duration_sec,
                opps_found,
                viable_found,
                errors,
                status,
                error_msg,
            ):
                pg_ok = True
            else:
                pg_ok = False
                logger.error(
                    "PostgreSQL log_scanner_run returned False for scanner=%s type=%s",
                    scanner_name,
                    scanner_type,
                )
                mark_pg_unavailable("log_scanner_run returned False")
        except Exception as e:
            pg_ok = False
            logger.error("Scanner run log failed: %s", e, exc_info=True)
            mark_pg_unavailable(f"log_scanner_run raised {type(e).__name__}", exc=e)
    return {"jsonl_ok": True, "pg_ok": pg_ok}


def log_engine_run(result: dict) -> PersistResult:
    """Log engine run to PostgreSQL. See module docstring for contract."""
    from database.postgres import mark_pg_unavailable, pg_available, save_engine_run_pg

    pg_ok: Optional[bool] = None
    if pg_available():
        try:
            if save_engine_run_pg(result):
                pg_ok = True
            else:
                pg_ok = False
                logger.error(
                    "PostgreSQL save_engine_run_pg returned False for run ts=%s",
                    result.get("ts", "unknown"),
                )
                mark_pg_unavailable("save_engine_run_pg returned False")
        except Exception as e:
            pg_ok = False
            logger.error("Engine run log failed: %s", e, exc_info=True)
            mark_pg_unavailable(f"save_engine_run_pg raised {type(e).__name__}", exc=e)
    return {"jsonl_ok": True, "pg_ok": pg_ok}
