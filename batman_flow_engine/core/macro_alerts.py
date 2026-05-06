"""Macro alert formatting and persistence.

A "macro alert" is a MacroEvent that has passed the impact-rules confidence
threshold. Alerts are appended to storage/logs/macro_alerts.jsonl (the
operator dashboard reads from there) and are also returned from the
orchestrator so callers (Streamlit, Telegram bot, future consumers) can
react in-process.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("batman.macro_alerts")

BASE_DIR = Path(__file__).resolve().parent.parent
ALERTS_LOG = BASE_DIR / "storage" / "logs" / "macro_alerts.jsonl"

# Alerts below this confidence are suppressed (the orchestrator still
# persists them at debug level for tuning, but they don't surface to
# the dashboard).
DEFAULT_CONFIDENCE_THRESHOLD = 0.75


def format_alert(event: dict[str, Any], impact: dict[str, Any]) -> dict[str, Any]:
    """Combine a MacroEvent and its impact forecast into a flat alert dict."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_timestamp": event.get("timestamp"),
        "source": event.get("source"),
        "event_type": event.get("event_type"),
        "severity": event.get("severity"),
        "headline": event.get("headline"),
        "currencies_affected": event.get("currencies_affected", []),
        "confidence": impact.get("confidence", 0.0),
        "scanners_affected": list(impact.get("impact_on_scanners", {}).keys()),
        "scanner_details": impact.get("impact_on_scanners", {}),
        "reasoning": impact.get("reasoning", ""),
        "source_url": event.get("source_url"),
    }


def save_alert(alert: dict[str, Any], filepath: Path | None = None) -> bool:
    """Append alert to the alerts JSONL log. Returns True on success.

    *filepath* defaults to the module-level ALERTS_LOG. The default is
    resolved at call time (not at function-definition time) so tests can
    monkeypatch ALERTS_LOG and have it take effect for indirect callers.
    """
    if filepath is None:
        # Read the module-level ALERTS_LOG at call time.
        from core import macro_alerts as _self  # noqa: PLC0415

        filepath = _self.ALERTS_LOG
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with filepath.open("a", encoding="utf-8") as f:
            f.write(json.dumps(alert, default=str) + "\n")
        return True
    except Exception as exc:
        logger.error("Failed to persist macro alert: %s", exc, exc_info=True)
        return False


def load_recent_alerts(filepath: Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Read up to *limit* most recent alerts from the JSONL log.

    Like ``save_alert``, *filepath* defaults to the module-level ALERTS_LOG
    resolved at call time so tests can monkeypatch it.
    """
    if filepath is None:
        from core import macro_alerts as _self  # noqa: PLC0415

        filepath = _self.ALERTS_LOG
    if not filepath.exists():
        return []
    try:
        lines = [ln for ln in filepath.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as exc:
        logger.error("Failed to read macro alerts: %s", exc, exc_info=True)
        return []

    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Skipping malformed alert row: %s", line[:120])
            continue
    out.reverse()  # newest first
    return out
