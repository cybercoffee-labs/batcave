#!/usr/bin/env python3
"""
Local terminal alert summary for Nightwing execution monitoring.

Role in the monitoring stack:
- `alerts.py` is the lightweight terminal companion to `dashboard.py`.
- It is intended for quick supervision when you do not want to keep the browser
  dashboard open.

Interaction with `executions.jsonl`:
- Reads only from `storage/logs/executions.jsonl`.
- Reuses the dashboard's log loading and normalization path so newest-first
  ordering, invalid-line skipping, and legacy handling stay consistent.

Legacy handling:
- Legacy rows are normalized the same way as the dashboard.
- In particular, `executed_amount_usd` safely falls back for older
  `SIMULATED_TRADE` records, so executed-amount alerts still work on older
  data.

Derived indicators and alert conditions:
- Uses normalized fields such as `batman.status`, `edge_net`,
  `executed_amount_usd`, and `batman.opp_id`.
- Reports grouped findings for:
  `decision == "OPPORTUNITY"`,
  `batman.status == "stale"`,
  `edge_net > --edge-threshold`,
  `executed_amount_usd > 0`,
  and optionally `lucius.approved == false`.

Run:
    python alerts.py --rows 100 --edge-threshold 0.10
    python alerts.py --rows 50 --skip-lucius-unapproved
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from dashboard import EXECUTIONS_FILE, _fmt, load_records, normalize_record


def _lucius_approved(record: dict[str, Any]) -> Any:
    """Extract `lucius.approved` without assuming the nested structure exists."""
    lucius = record.get("lucius")
    if not isinstance(lucius, dict):
        return None
    return lucius.get("approved")


def load_alert_records(path: Path = EXECUTIONS_FILE, latest_n: int = 100) -> list[dict[str, Any]]:
    """Load and normalize the latest execution rows for alert evaluation."""
    records = load_records(path)
    if latest_n > 0:
        records = records[:latest_n]

    alert_records: list[dict[str, Any]] = []
    for record in records:
        normalized = normalize_record(record)
        normalized["lucius.approved"] = _lucius_approved(record)
        alert_records.append(normalized)
    return alert_records


def collect_alerts(
    records: list[dict[str, Any]],
    edge_threshold: float = 0.0,
    include_lucius_unapproved: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """Group normalized records by simple operational alert conditions."""
    grouped = {
        "opportunity": [],
        "batman_stale": [],
        "edge_positive": [],
        "executed_amount": [],
        "lucius_unapproved": [],
    }

    for record in records:
        if record.get("decision") == "OPPORTUNITY":
            grouped["opportunity"].append(record)
        if record.get("batman.status") == "stale":
            grouped["batman_stale"].append(record)

        edge_net = record.get("edge_net")
        if isinstance(edge_net, (int, float)) and edge_net > edge_threshold:
            grouped["edge_positive"].append(record)

        executed_amount_usd = record.get("executed_amount_usd")
        if isinstance(executed_amount_usd, (int, float)) and executed_amount_usd > 0:
            grouped["executed_amount"].append(record)

        if include_lucius_unapproved and record.get("lucius.approved") is False:
            grouped["lucius_unapproved"].append(record)

    return grouped


def _format_record_line(record: dict[str, Any]) -> str:
    """Format one alert row for compact human-readable terminal output."""
    return (
        f"- ts={_fmt(record.get('ts'))} "
        f"cycle={_fmt(record.get('cycle'))} "
        f"mode={_fmt(record.get('mode'))} "
        f"decision={_fmt(record.get('decision'))} "
        f"edge_net={_fmt(record.get('edge_net'))} "
        f"batman.status={_fmt(record.get('batman.status'))} "
        f"opp_id={_fmt(record.get('batman.opp_id'))}"
    )


def render_alert_report(
    alerts: dict[str, list[dict[str, Any]]],
    rows_scanned: int,
    edge_threshold: float,
) -> str:
    """Render grouped alert findings for terminal use."""
    labels = [
        ("opportunity", "OPPORTUNITY decisions"),
        ("batman_stale", "Batman stale"),
        ("edge_positive", f"edge_net > {edge_threshold:g}"),
        ("executed_amount", "executed_amount_usd > 0"),
        ("lucius_unapproved", "lucius.approved == false"),
    ]

    lines = [f"Nightwing alerts from latest {rows_scanned} record(s)"]
    total_matches = sum(len(records) for records in alerts.values())
    lines.append(f"Total alert matches: {total_matches}")

    for key, label in labels:
        records = alerts[key]
        lines.append("")
        lines.append(f"{label}: {len(records)}")
        for record in records:
            lines.append(_format_record_line(record))

    return "\n".join(lines)


def main() -> None:
    """Run the local alert summary CLI."""
    parser = argparse.ArgumentParser(description="Minimal local alert summary for Nightwing execution logs")
    parser.add_argument("--rows", type=int, default=100, help="Latest N rows to scan")
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=0.0,
        help="Only alert for edge_net values above this threshold",
    )
    parser.add_argument(
        "--skip-lucius-unapproved",
        action="store_true",
        help="Skip lucius.approved == false alerts",
    )
    args = parser.parse_args()

    latest_n = max(1, args.rows)
    records = load_alert_records(latest_n=latest_n)
    alerts = collect_alerts(
        records,
        edge_threshold=args.edge_threshold,
        include_lucius_unapproved=not args.skip_lucius_unapproved,
    )
    print(render_alert_report(alerts, rows_scanned=len(records), edge_threshold=args.edge_threshold))


if __name__ == "__main__":
    main()
