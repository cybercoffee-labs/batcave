"""
GORDON (SHIELD) — Minimal security and runtime control module.

This module provides the first standalone implementation of Batman Lab's
security/control surface:
- kill switch detection
- runtime guard inspection
- append-only audit logging
- a simple health summary

The module is intentionally self-contained and does not modify engine behavior.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = STORAGE_DIR / "logs"

KILL_SWITCH_FILE = STORAGE_DIR / "kill_switch.flag"
DEFAULT_LOCK_FILE = STORAGE_DIR / "engine.lock"
AUDIT_LOG_FILE = LOGS_DIR / "gordon_audit.jsonl"


def _utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def is_kill_switch_active() -> bool:
    """
    Return whether the kill switch flag file is present.

    The engine should be considered blocked whenever
    `storage/kill_switch.flag` exists.
    """
    return KILL_SWITCH_FILE.exists()


def check_runtime_guard(lock_file_path: str | None = None) -> dict:
    """
    Inspect the engine lock file and summarize runtime guard state.

    Args:
        lock_file_path: Optional override for the lock file path. Defaults to
            `storage/engine.lock`.

    Returns:
        Dict containing:
        - active: Whether the runtime guard should be considered active
        - path: Resolved lock file path as a string
        - pid: PID if readable, else None
        - status: Human-readable status string
    """
    lock_path = Path(lock_file_path) if lock_file_path else DEFAULT_LOCK_FILE
    result = {
        "active": False,
        "path": str(lock_path),
        "pid": None,
        "status": "not_found",
    }

    if not lock_path.exists():
        return result

    try:
        raw_pid = lock_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        result["status"] = f"unreadable: {exc.__class__.__name__}"
        return result

    if not raw_pid:
        result["status"] = "empty_lock_file"
        return result

    try:
        pid = int(raw_pid)
    except ValueError:
        result["status"] = "invalid_pid"
        return result

    result["pid"] = pid

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        result["status"] = "stale_lock"
        return result
    except PermissionError:
        result["active"] = True
        result["status"] = "active_pid_permission_denied"
        return result
    except OSError as exc:
        result["status"] = f"pid_check_failed: {exc.__class__.__name__}"
        return result

    result["active"] = True
    result["status"] = "active"
    return result


def log_gordon_event(event_type: str, details: dict | None = None) -> None:
    """
    Append a GORDON event record to the audit log.

    Args:
        event_type: Event category or name.
        details: Optional event payload. If omitted, an empty dict is stored.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": _utc_timestamp(),
        "event_type": event_type,
        "details": details or {},
    }

    with AUDIT_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def get_system_health() -> dict:
    """
    Return a minimal system health summary for GORDON.

    The summary is read-only and does not alter runtime behavior.
    """
    return {
        "kill_switch_active": is_kill_switch_active(),
        "runtime_guard": check_runtime_guard(),
        "audit_log_path": str(AUDIT_LOG_FILE),
        "timestamp": _utc_timestamp(),
    }


def check(result: dict | None = None, exposure: dict | None = None) -> dict:
    """
    GORDON security gate for Batman signal production.

    Called after ALFRED validation, before HARVEY ingestion.

    Checks:
        1. Kill switch       — hard BLOCK if flag file exists
        2. DQ score gate     — hard BLOCK if dq_score < 0.60
        3. Runtime guard     — ALERT if stale engine lock detected
        4. Regime anomaly    — ALERT if DATA_DEGRADED or PANIC

    Args:
        result:   Engine result dict produced by _build_engine_result +
                  _enrich_runtime_metadata. May be None in tests.
        exposure: HARVEY daily exposure by fiat, e.g. {"MXN": 800.0, "ARS": 0.0}.
                  Passed for logging and downstream context. Does not block.

    Returns:
        {
            "status":     "OK" | "BLOCKED" | "ALERT",
            "checks":     [{"check": str, "passed": bool, ...}, ...],
            "blocked_by": [str, ...],   # non-empty only when BLOCKED
            "warnings":   [str, ...],   # non-empty only when ALERT
            "exposure":   {str: float}, # harvey daily exposure by fiat
            "timestamp":  str,
        }
    """
    checks: list = []
    blocked_by: list = []
    warnings: list = []

    # 1. Kill switch — hard block
    if is_kill_switch_active():
        checks.append({"check": "kill_switch", "passed": False, "reason": "kill_switch_active"})
        blocked_by.append("kill_switch_active")
    else:
        checks.append({"check": "kill_switch", "passed": True})

    # 2. DQ score gate — block if data is too degraded to emit reliable signals
    dq_score = None
    if result:
        dq = result.get("data_quality") or {}
        dq_score = dq.get("dq_score")

    if dq_score is not None and dq_score < 0.60:
        checks.append(
            {
                "check": "dq_gate",
                "passed": False,
                "dq_score": dq_score,
                "reason": "dq_score_below_threshold",
            }
        )
        blocked_by.append(f"dq_score_{dq_score:.2f}_below_0.60")
    else:
        checks.append({"check": "dq_gate", "passed": True, "dq_score": dq_score})

    # 3. Runtime guard — alert on stale lock (previous run may have crashed)
    guard = check_runtime_guard()
    if guard["status"] == "stale_lock":
        checks.append(
            {
                "check": "runtime_guard",
                "passed": True,
                "status": guard["status"],
                "warning": "stale_engine_lock",
            }
        )
        warnings.append("stale_engine_lock")
    else:
        checks.append({"check": "runtime_guard", "passed": True, "status": guard["status"]})

    # 4. Regime anomaly — alert on degraded or panic market conditions
    regime_label = None
    if result:
        regime = (result.get("stress") or {}).get("regime") or {}
        regime_label = regime.get("label")

    if regime_label == "PANIC":
        checks.append({"check": "regime", "passed": False, "regime": regime_label})
        blocked_by.append("regime_panic")
    elif regime_label == "DATA_DEGRADED":
        checks.append(
            {
                "check": "regime",
                "passed": True,
                "regime": regime_label,
                "warning": "regime_DATA_DEGRADED",
            }
        )
        warnings.append("regime_DATA_DEGRADED")
    else:
        checks.append({"check": "regime", "passed": True, "regime": regime_label})

    # Determine final status and log
    if blocked_by:
        status = "BLOCKED"
        log_gordon_event("gordon_check_blocked", {"blocked_by": blocked_by})
    elif warnings:
        status = "ALERT"
        log_gordon_event("gordon_check_alert", {"warnings": warnings})
    else:
        status = "OK"
        log_gordon_event("gordon_check_ok", {})

    return {
        "status": status,
        "checks": checks,
        "blocked_by": blocked_by,
        "warnings": warnings,
        "exposure": exposure or {},
        "timestamp": _utc_timestamp(),
    }


__all__ = [
    "AUDIT_LOG_FILE",
    "DEFAULT_LOCK_FILE",
    "KILL_SWITCH_FILE",
    "check",
    "check_runtime_guard",
    "get_system_health",
    "is_kill_switch_active",
    "log_gordon_event",
]
