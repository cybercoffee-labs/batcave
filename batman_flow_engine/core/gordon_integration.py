"""
GORDON integration scaffolding for the canonical engine runtime.

This module is intentionally non-invasive. It documents and exposes helper
functions for future integration into `engine.run_engine()` without modifying
runtime behavior today.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.gordon import (
    check_runtime_guard,
    is_kill_switch_active,
    log_gordon_event,
)


def _utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def pre_run_security_check() -> dict:
    """
    Evaluate pre-run GORDON controls for future engine integration.

    Returns a summary describing whether the kill switch is active, whether the
    runtime guard reports an active lock, and whether the engine would be ready
    to proceed if these controls were enforced.
    """
    kill_switch = is_kill_switch_active()
    runtime_guard = check_runtime_guard()
    ready = not kill_switch and not runtime_guard.get("active", False)
    return {
        "kill_switch": kill_switch,
        "runtime_guard": runtime_guard,
        "ready": ready,
        "timestamp": _utc_timestamp(),
    }


def record_engine_start() -> None:
    """Record a future engine start event in the GORDON audit log."""
    log_gordon_event("engine_start")


def record_engine_stop() -> None:
    """Record a future engine stop event in the GORDON audit log."""
    log_gordon_event("engine_stop")


def record_engine_error(error_message: str) -> None:
    """Record a future engine error event in the GORDON audit log."""
    log_gordon_event("engine_error", {"message": error_message})


def recommended_integration_points() -> dict:
    """
    Describe where GORDON should be inserted into `engine.run_engine()` later.

    The output is documentation-friendly and does not perform any integration.
    """
    return {
        "canonical_runtime": "engine.run_engine()",
        "pre_run": {
            "location": "At the beginning of engine.run_engine(), before checking or writing the engine lock file.",
            "purpose": "Block execution when the kill switch is active and surface runtime guard state before work begins.",
            "recommended_calls": [
                "pre_run_security_check()",
            ],
        },
        "on_start": {
            "location": "Immediately after a run is accepted and runtime metadata is established.",
            "purpose": "Record a durable audit event for engine startup.",
            "recommended_calls": [
                "record_engine_start()",
            ],
        },
        "on_error": {
            "location": "Inside the main exception handling path for run_engine().",
            "purpose": "Capture runtime failures in the GORDON audit log.",
            "recommended_calls": [
                "record_engine_error(str(exc))",
            ],
        },
        "on_stop": {
            "location": "In the final shutdown/finally path before lock cleanup completes.",
            "purpose": "Record a clean stop event regardless of success or failure.",
            "recommended_calls": [
                "record_engine_stop()",
            ],
        },
        "note": "This module is scaffolding only and does not change current engine behavior.",
    }


__all__ = [
    "pre_run_security_check",
    "record_engine_error",
    "record_engine_start",
    "record_engine_stop",
    "recommended_integration_points",
]
