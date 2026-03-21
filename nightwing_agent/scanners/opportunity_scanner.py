#!/usr/bin/env python3
"""
Local opportunity scanner for Nightwing laboratory monitoring.

Role:
- Scans recent execution rows for opportunity-oriented conditions without
  touching trading execution.

Data source:
- Reads only from `storage/logs/executions.jsonl`.
- Uses the dashboard's normalized view so invalid lines, newest-first ordering,
  and legacy amount handling stay consistent.

Event conditions:
- `decision == "OPPORTUNITY"`
- `edge_net > --edge-threshold`
- `viable_opportunity`, defined here as both conditions being true

Run:
    python scanners/opportunity_scanner.py --rows 100 --edge-threshold 0.10
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
SCANNER_EVENTS_FILE = BASE_DIR / "storage" / "logs" / "scanner_events.jsonl"


def load_scanner_records(path: Path = EXECUTIONS_FILE, latest_n: int = 100) -> list[dict[str, Any]]:
    """Load the latest normalized execution rows for scanner evaluation."""
    records = [normalize_record(record) for record in load_records(path)]
    if latest_n > 0:
        return records[:latest_n]
    return records


def _base_event(record: dict[str, Any], event_type: str) -> dict[str, Any]:
    """Build a stable event payload from one normalized execution row."""
    return {
        "scanner": "opportunity_scanner",
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


def collect_opportunity_events(
    records: list[dict[str, Any]],
    edge_threshold: float = 0.0,
) -> dict[str, list[dict[str, Any]]]:
    """Group opportunity events from normalized execution rows."""
    grouped = {
        "opportunity_decision": [],
        "edge_threshold": [],
        "viable_opportunity": [],
    }

    for record in records:
        is_opportunity = record.get("decision") == "OPPORTUNITY"
        edge_net = record.get("edge_net")
        edge_above_threshold = isinstance(edge_net, (int, float)) and edge_net > edge_threshold

        if is_opportunity:
            grouped["opportunity_decision"].append(_base_event(record, "opportunity_decision"))
        if edge_above_threshold:
            grouped["edge_threshold"].append(_base_event(record, "edge_threshold"))
        if is_opportunity and edge_above_threshold:
            grouped["viable_opportunity"].append(_base_event(record, "viable_opportunity"))

    return grouped


def append_events(events_path: Path, grouped_events: dict[str, list[dict[str, Any]]]) -> int:
    """Append grouped scanner events to a JSONL file and return the number written."""
    events = [event for group in grouped_events.values() for event in group]
    if not events:
        return 0

    with events_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True))
            handle.write("\n")
    return len(events)


def _format_event(event: dict[str, Any]) -> str:
    """Render one event as a compact terminal line."""
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
    edge_threshold: float,
) -> str:
    """Render the grouped opportunity scanner output for terminal use."""
    labels = [
        ("opportunity_decision", 'decision == "OPPORTUNITY"'),
        ("edge_threshold", f"edge_net > {edge_threshold:g}"),
        ("viable_opportunity", "viable opportunities"),
    ]

    total_events = sum(len(events) for events in grouped_events.values())
    lines = [f"Opportunity scanner from latest {rows_scanned} record(s)", f"Total events: {total_events}"]

    for key, label in labels:
        events = grouped_events[key]
        lines.append("")
        lines.append(f"{label}: {len(events)}")
        for event in events:
            lines.append(_format_event(event))

    return "\n".join(lines)


def main() -> None:
    """Run the opportunity scanner CLI."""
    parser = argparse.ArgumentParser(description="Local opportunity scanner for Nightwing logs")
    parser.add_argument("--rows", type=int, default=100, help="Latest N rows to scan")
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=0.0,
        help="Only flag edge_net values above this threshold",
    )
    parser.add_argument(
        "--events-path",
        type=Path,
        default=SCANNER_EVENTS_FILE,
        help="JSONL file to append scanner events to",
    )
    args = parser.parse_args()

    records = load_scanner_records(latest_n=max(1, args.rows))
    grouped_events = collect_opportunity_events(records, edge_threshold=args.edge_threshold)
    appended = append_events(args.events_path, grouped_events)
    print(render_summary(grouped_events, rows_scanned=len(records), edge_threshold=args.edge_threshold))
    print(f"\nAppended events: {appended}")


if __name__ == "__main__":
    main()
