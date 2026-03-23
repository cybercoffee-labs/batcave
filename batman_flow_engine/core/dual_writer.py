"""
Batman Lab — Dual Writer
Writes opportunities to BOTH .jsonl (legacy) AND PostgreSQL (new).
Drop-in replacement for _append_to_log in all scanners.

Usage in scanners:
  from core.dual_writer import log_opportunity, log_scanner_run
  
  # Instead of _append_to_log(opp):
  log_opportunity(opp)
  
  # At end of scanner:
  log_scanner_run("C", "P2P LATAM", duration, found, viable)
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("batman.writer")

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

_pg_available = None


def _check_pg():
    """Check if PostgreSQL is available (cached)."""
    global _pg_available
    if _pg_available is None:
        try:
            from database.postgres import check_connection
            result = check_connection()
            _pg_available = result.get("status") == "ok"
            if _pg_available:
                logger.info("PostgreSQL available — dual writing enabled")
            else:
                logger.info("PostgreSQL unavailable — JSONL only")
        except Exception:
            _pg_available = False
    return _pg_available


def log_opportunity(opp: dict, log_to_file: bool = True) -> bool:
    """Write opportunity to JSONL + PostgreSQL."""
    success = False

    # 1. Always write to JSONL (legacy, reliable)
    if log_to_file:
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(opp, default=str) + "\n")
            success = True
        except Exception as e:
            logger.error("JSONL write failed: %s", e)

    # 2. Also write to PostgreSQL if available
    if _check_pg():
        try:
            from database.postgres import save_opportunity
            save_opportunity(opp)
        except Exception as e:
            logger.warning("PostgreSQL write failed (JSONL still saved): %s", e)

    return success


def log_scanner_run(scanner_type: str, scanner_name: str, duration_sec: float,
                    opps_found: int, viable_found: int, errors: int = 0,
                    status: str = "ok", error_msg: str = None) -> bool:
    """Log scanner execution to PostgreSQL."""
    if _check_pg():
        try:
            from database.postgres import log_scanner_run as pg_log
            return pg_log(scanner_type, scanner_name, duration_sec,
                          opps_found, viable_found, errors, status, error_msg)
        except Exception as e:
            logger.warning("Scanner run log failed: %s", e)
    return False


def log_engine_run(result: dict) -> bool:
    """Log engine run to PostgreSQL."""
    if _check_pg():
        try:
            from database.postgres import save_engine_run_pg
            return save_engine_run_pg(result)
        except Exception as e:
            logger.warning("Engine run log failed: %s", e)
    return False
