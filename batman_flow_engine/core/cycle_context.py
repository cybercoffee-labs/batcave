"""
Batman Lab — Cycle Correlation ID Context (audit Section C #9)

A single short opaque ID identifies one engine cycle end-to-end. The same
ID rides every opportunity emitted by every scanner during that cycle, lands
in the JSONL row, the HARVEY signals table, and the PostgreSQL opportunities
table. Reconciliation against the engine_runs row is then a direct join on
cycle_id, not a fragile timestamp-bracket query.

Threading model
---------------
Engine cycles are sequential within a process — `run_engine()` is called
serially by `tools/run_loop.py`. Within a cycle, scanners run inside the
engine's ThreadPoolExecutor; we want every worker thread to see the same
cycle_id, so the context is module-level (process-global), not thread-local.
``set_current_cycle_id`` is called by ``run_engine`` at cycle start;
``clear_current_cycle_id`` is called in the same function's ``finally``.

Public API:
    set_current_cycle_id(cycle_id) -> None
    get_current_cycle_id() -> str | None
    clear_current_cycle_id() -> None
    new_cycle_id() -> str
    stamp_cycle_id(opp) -> dict
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("batman.cycle_context")

# 12 hex chars = ~48 bits of entropy. Plenty for collision avoidance over
# decades of 1-cycle-every-20-minutes operation, while staying short enough
# to grep for in logs.
_CYCLE_ID_LEN = 12

_current_cycle_id: str | None = None


def new_cycle_id() -> str:
    """Generate a fresh cycle correlation id (12 hex chars)."""
    return uuid.uuid4().hex[:_CYCLE_ID_LEN]


def set_current_cycle_id(cycle_id: str) -> None:
    """Store the active cycle id for downstream stamping."""
    global _current_cycle_id
    if not cycle_id:
        raise ValueError("cycle_id must be a non-empty string")
    _current_cycle_id = cycle_id


def get_current_cycle_id() -> str | None:
    """Return the active cycle id, or None if no cycle is in flight."""
    return _current_cycle_id


def clear_current_cycle_id() -> None:
    """Clear the active cycle id. Call in run_engine's finally block."""
    global _current_cycle_id
    _current_cycle_id = None


def stamp_cycle_id(opp: dict[str, Any]) -> dict[str, Any]:
    """
    Add ``cycle_id`` to *opp* if missing. Mutates and returns the dict.

    Behaviour:
      - If opp already has a non-empty ``cycle_id``, leave it alone.
      - Else, if a cycle context is active, stamp it.
      - Else, log a debug line (NOT error — some scanners run from CLI for
        ad-hoc diagnostics where there is no engine cycle) and leave the
        opp untouched.

    Returns the same dict so callers can write ``stamp_cycle_id(opp)`` in a
    single line before logging.
    """
    if not isinstance(opp, dict):
        return opp
    existing = opp.get("cycle_id")
    if existing:
        return opp
    cycle_id = _current_cycle_id
    if cycle_id is None:
        logger.debug(
            "stamp_cycle_id: no active cycle context; opp=%s left unstamped",
            opp.get("opp_id", "unknown"),
        )
        return opp
    opp["cycle_id"] = cycle_id
    return opp
