#!/usr/bin/env python3
"""
Local system scanner for Nightwing laboratory monitoring.

Role:
- Scans recent execution rows for operational health conditions without
  modifying Batman or execution flow.

Data source:
- Reads only from `storage/logs/executions.jsonl`.
- Uses the dashboard's normalized view so invalid lines, newest-first ordering,
  and legacy record handling stay consistent.

Event conditions:
- `batman.status == "stale"`
- `batman.age_seconds > --age-threshold`
- `lucius.approved == false`

Run:
    python scanners/system_scanner.py --rows 100 --age-threshold 300
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dashboard import _fmt, load_records, normalize_record

EXECUTIONS_FILE = BASE_DIR / "storage" / "logs" / "executions.jsonl"
SYSTEM_EVENTS_FILE = BASE_DIR / "storage" / "logs" / "system_events.jsonl"


def _lucius_approved(record: dict[str, Any]) -> Any:
    """Extract `lucius.approved` without assuming nested fields exist."""
    lucius = record.get("lucius")
    if not isinstance(lucius, dict):
        return None
    return lucius.get("approved")


def load_scanner_records(path: Path = EXECUTIONS_FILE, latest_n: int = 100) -> list[dict[str, Any]]:
    """Load the latest normalized execution rows for system scanning."""
    records = load_records(path)
    if latest_n > 0:
        records = records[:latest_n]

    normalized_records = []
    for record in records:
        normalized = normalize_record(record)
        normalized["lucius.approved"] = _lucius_approved(record)
        normalized_records.append(normalized)
    return normalized_records


def _base_event(record: dict[str, Any], event_type: str) -> dict[str, Any]:
    """Build a stable system event payload from one normalized row."""
    return {
        "scanner": "system_scanner",
        "event_type": event_type,
        "ts": record.get("ts"),
        "cycle": record.get("cycle"),
        "mode": record.get("mode"),
        "decision": record.get("decision"),
        "edge_net": record.get("edge_net"),
        "batman.status": record.get("batman.status"),
        "opp_id": record.get("batman.opp_id"),
        "record_version": record.get("record_version"),
    }


def collect_system_events(
    records: list[dict[str, Any]],
    age_threshold: float = 300.0,
) -> dict[str, list[dict[str, Any]]]:
    """Group system-health events from normalized execution rows."""
    grouped = {
        "batman_stale": [],
        "batman_age_threshold": [],
        "lucius_unapproved": [],
    }

    for record in records:
        if record.get("batman.status") == "stale":
            grouped["batman_stale"].append(_base_event(record, "batman_stale"))

        age_seconds = record.get("batman.age_seconds")
        if isinstance(age_seconds, (int, float)) and age_seconds > age_threshold:
            grouped["batman_age_threshold"].append(_base_event(record, "batman_age_threshold"))

        if record.get("lucius.approved") is False:
            grouped["lucius_unapproved"].append(_base_event(record, "lucius_unapproved"))

    return grouped


def append_events(events_path: Path, grouped_events: dict[str, list[dict[str, Any]]]) -> int:
    """Append grouped system events to a JSONL file and return the number written."""
    events = [event for group in grouped_events.values() for event in group]
    if not events:
        return 0

    with events_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True))
            handle.write("\n")
    return len(events)


def _format_event(event: dict[str, Any]) -> str:
    """Render one system event as a compact terminal line."""
    return (
        f"- ts={_fmt(event.get('ts'))} "
        f"cycle={_fmt(event.get('cycle'))} "
        f"mode={_fmt(event.get('mode'))} "
        f"decision={_fmt(event.get('decision'))} "
        f"edge_net={_fmt(event.get('edge_net'))} "
        f"batman.status={_fmt(event.get('batman.status'))} "
        f"opp_id={_fmt(event.get('opp_id'))}"
    )


def render_summary(
    grouped_events: dict[str, list[dict[str, Any]]],
    rows_scanned: int,
    age_threshold: float,
) -> str:
    """Render the grouped system scanner output for terminal use."""
    labels = [
        ("batman_stale", 'batman.status == "stale"'),
        ("batman_age_threshold", f"batman.age_seconds > {age_threshold:g}"),
        ("lucius_unapproved", "lucius.approved == false"),
    ]

    total_events = sum(len(events) for events in grouped_events.values())
    lines = [f"System scanner from latest {rows_scanned} record(s)", f"Total events: {total_events}"]

    for key, label in labels:
        events = grouped_events[key]
        lines.append("")
        lines.append(f"{label}: {len(events)}")
        for event in events:
            lines.append(_format_event(event))

    return "\n".join(lines)


def main() -> None:
    """Run the system scanner CLI."""
    parser = argparse.ArgumentParser(description="Local system scanner for Nightwing logs")
    parser.add_argument("--rows", type=int, default=100, help="Latest N rows to scan")
    parser.add_argument(
        "--age-threshold",
        type=float,
        default=300.0,
        help="Only flag Batman ages above this threshold",
    )
    parser.add_argument(
        "--events-path",
        type=Path,
        default=SYSTEM_EVENTS_FILE,
        help="JSONL file to append scanner events to",
    )
    args = parser.parse_args()

    records = load_scanner_records(latest_n=max(1, args.rows))
    grouped_events = collect_system_events(records, age_threshold=args.age_threshold)
    appended = append_events(args.events_path, grouped_events)
    print(render_summary(grouped_events, rows_scanned=len(records), age_threshold=args.age_threshold))
    print(f"\nAppended events: {appended}")


if __name__ == "__main__":
    main()
