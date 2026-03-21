#!/usr/bin/env python3
"""
Local operational dashboard for Nightwing execution monitoring.

Role in the monitoring stack:
- `dashboard.py` is the browser-based local read-only view for recent execution
  records.
- It sits alongside `alerts.py`, which provides terminal-oriented summaries for
  the same log source.

Interaction with `executions.jsonl`:
- Reads only from `storage/logs/executions.jsonl`.
- Loads newline-delimited JSON objects, skips invalid JSON and non-object rows,
  and keeps newest-first ordering for supervision.

Legacy handling:
- Older rows that predate the refactor may not include
  `evaluated_amount_usd` or `executed_amount_usd`.
- Those rows are marked as `record_version=legacy`, and legacy executed amount
  falls back to `amount_usd` for `SIMULATED_TRADE` rows.

Derived indicators:
- `edge_sign` is derived from `edge_net` as `positive`, `zero`, `negative`, or
  `unknown`.
- `batman.freshness` is bucketed from `batman.age_seconds` as `fresh`,
  `aging`, `stale`, or `unknown`.
- `execution_state` is derived from the display action as `no_execution`,
  `logged_only`, `simulated_trade`, or `blocked`.

Run:
    python dashboard.py --host 127.0.0.1 --port 8787 --rows 100

Then open:
    http://127.0.0.1:8787
"""

from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
EXECUTIONS_FILE = BASE_DIR / "storage" / "logs" / "executions.jsonl"


def load_records(path: Path = EXECUTIONS_FILE) -> list[dict[str, Any]]:
    """Load execution log rows newest-first, skipping invalid or non-object lines."""
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)

    records.reverse()
    return records


def _legacy_executed_amount(record: dict[str, Any]) -> Any:
    if "executed_amount_usd" in record:
        return record.get("executed_amount_usd")
    if record.get("action") == "SIMULATED_TRADE":
        return record.get("amount_usd")
    return 0


def _display_action(record: dict[str, Any]) -> Any:
    action = record.get("action")
    if action not in (None, ""):
        return action

    decision = record.get("decision")
    if decision == "PASS":
        return "NO_ACTION"
    if decision == "BLOCKED_COMPLIANCE":
        return "BLOCKED"
    return action


def _record_version(record: dict[str, Any]) -> str:
    if "evaluated_amount_usd" in record and "executed_amount_usd" in record:
        return "current"
    return "legacy"


def _batman_freshness(age_seconds: Any) -> str:
    if not isinstance(age_seconds, (int, float)):
        return "unknown"
    if age_seconds < 60:
        return "fresh"
    if age_seconds < 300:
        return "aging"
    return "stale"


def _edge_sign(edge_net: Any) -> str:
    if not isinstance(edge_net, (int, float)):
        return "unknown"
    if edge_net > 0:
        return "positive"
    if edge_net < 0:
        return "negative"
    return "zero"


def _batman_opp_id(batman: dict[str, Any], batman_data: dict[str, Any]) -> Any:
    opp_id = batman.get("opp_id")
    if opp_id not in (None, ""):
        return opp_id
    return batman_data.get("opp_id")


def _execution_state(action: Any) -> str:
    if action == "SIMULATED_TRADE":
        return "simulated_trade"
    if action == "BLOCKED":
        return "blocked"
    if action in (None, "", "NO_ACTION"):
        return "no_execution"
    return "logged_only"


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Map one raw execution row into stable display fields used by the dashboard."""
    lucius = record.get("lucius")
    if not isinstance(lucius, dict):
        lucius = {}

    batman = record.get("batman")
    if not isinstance(batman, dict):
        batman = {}

    batman_data = batman.get("data")
    if not isinstance(batman_data, dict):
        batman_data = {}

    action = _display_action(record)
    batman_age_seconds = batman.get("age_seconds")
    batman_status = batman.get("status", "missing")

    return {
        "cycle": record.get("cycle"),
        "ts": record.get("ts"),
        "mode": record.get("mode"),
        "decision": record.get("decision"),
        "action": action,
        "execution_state": _execution_state(action),
        "edge_net": record.get("edge_net"),
        "edge_sign": _edge_sign(record.get("edge_net")),
        "evaluated_amount_usd": record.get("evaluated_amount_usd", record.get("amount_usd")),
        "executed_amount_usd": _legacy_executed_amount(record),
        "record_version": _record_version(record),
        "lucius.daily_exposure_usd": lucius.get("daily_exposure_usd"),
        "batman.status": batman_status,
        "batman.age_seconds": batman_age_seconds,
        "batman.freshness": _batman_freshness(batman_age_seconds),
        "batman.opp_id": _batman_opp_id(batman, batman_data),
    }


def apply_filters(
    records: list[dict[str, Any]],
    mode: str = "",
    decision: str = "",
    batman_status: str = "",
    edge_sign: str = "",
    legacy_only: bool = False,
    stale_only: bool = False,
    latest_n: int = 100,
) -> list[dict[str, Any]]:
    """Apply the dashboard's read-only operator filters to normalized records."""
    filtered = records
    if mode:
        filtered = [record for record in filtered if record.get("mode") == mode]
    if decision:
        filtered = [record for record in filtered if record.get("decision") == decision]
    if batman_status:
        filtered = [record for record in filtered if record.get("batman.status") == batman_status]
    if edge_sign:
        filtered = [record for record in filtered if record.get("edge_sign") == edge_sign]
    if legacy_only:
        filtered = [record for record in filtered if record.get("record_version") == "legacy"]
    if stale_only:
        filtered = [record for record in filtered if record.get("batman.status") == "stale"]
    if latest_n > 0:
        filtered = filtered[:latest_n]
    return filtered


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute filtered supervision metrics without changing any trading behavior."""
    latest = records[0] if records else {}
    edge_values = [record.get("edge_net") for record in records if isinstance(record.get("edge_net"), (int, float))]
    return {
        "total_records": len(records),
        "count_pass": sum(1 for record in records if record.get("decision") == "PASS"),
        "count_opportunity": sum(1 for record in records if record.get("decision") == "OPPORTUNITY"),
        "count_blocked_compliance": sum(1 for record in records if record.get("decision") == "BLOCKED_COMPLIANCE"),
        "count_legacy": sum(1 for record in records if record.get("record_version") == "legacy"),
        "count_batman_stale": sum(1 for record in records if record.get("batman.status") == "stale"),
        "count_edge_positive": sum(1 for record in records if record.get("edge_sign") == "positive"),
        "count_edge_negative": sum(1 for record in records if record.get("edge_sign") == "negative"),
        "avg_edge_net": sum(edge_values) / len(edge_values) if edge_values else None,
        "max_edge_net": max(edge_values) if edge_values else None,
        "min_edge_net": min(edge_values) if edge_values else None,
        "latest_daily_exposure_usd": latest.get("lucius.daily_exposure_usd"),
        "latest_batman_age_seconds": latest.get("batman.age_seconds"),
    }


def _collect_values(records: list[dict[str, Any]], key: str) -> list[str]:
    values = []
    seen = set()
    for record in records:
        value = record.get(key)
        if value in (None, ""):
            continue
        if value in seen:
            continue
        seen.add(value)
        values.append(str(value))
    return values


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _option_html(current: str, value: str) -> str:
    selected = " selected" if current == value else ""
    label = html.escape(value) if value else "All"
    return f'<option value="{html.escape(value)}"{selected}>{label}</option>'


def render_html(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    mode: str,
    decision: str,
    batman_status: str,
    edge_sign: str,
    legacy_only: bool,
    stale_only: bool,
    latest_n: int,
    mode_options: list[str],
    decision_options: list[str],
    batman_status_options: list[str],
    edge_sign_options: list[str],
) -> str:
    """Render the local HTML dashboard for the current filtered dataset."""
    columns = [
        "cycle",
        "ts",
        "mode",
        "decision",
        "action",
        "execution_state",
        "edge_net",
        "edge_sign",
        "evaluated_amount_usd",
        "executed_amount_usd",
        "record_version",
        "lucius.daily_exposure_usd",
        "batman.status",
        "batman.age_seconds",
        "batman.freshness",
        "batman.opp_id",
    ]

    summary_rows = [
        ("total records", summary.get("total_records")),
        ("count of PASS", summary.get("count_pass")),
        ("count of OPPORTUNITY", summary.get("count_opportunity")),
        ("count of BLOCKED_COMPLIANCE", summary.get("count_blocked_compliance")),
        ("count of legacy rows", summary.get("count_legacy")),
        ("count of stale Batman rows", summary.get("count_batman_stale")),
        ("count of positive edge rows", summary.get("count_edge_positive")),
        ("count of negative edge rows", summary.get("count_edge_negative")),
        ("average edge_net", summary.get("avg_edge_net")),
        ("max edge_net", summary.get("max_edge_net")),
        ("min edge_net", summary.get("min_edge_net")),
        ("latest daily_exposure_usd", summary.get("latest_daily_exposure_usd")),
        ("latest Batman age_seconds", summary.get("latest_batman_age_seconds")),
    ]

    table_rows = []
    for record in records:
        rendered_cells = []
        for column in columns:
            value = _fmt(record.get(column))
            cell_class = ""
            if column == "batman.status":
                status = str(record.get(column) or "")
                if status == "ok":
                    cell_class = ' class="status-ok"'
                elif status == "stale":
                    cell_class = ' class="status-stale"'
            elif column == "record_version" and record.get(column) == "legacy":
                cell_class = ' class="record-legacy"'
            rendered_cells.append(f"<td{cell_class}>{html.escape(value)}</td>")
        cells = "".join(rendered_cells)
        table_rows.append(f"<tr>{cells}</tr>")

    if not table_rows:
        table_rows.append(f'<tr><td colspan="{len(columns)}">No records matched the filters.</td></tr>')

    mode_select = [_option_html(mode, "")]
    mode_select.extend(_option_html(mode, value) for value in mode_options)

    decision_select = [_option_html(decision, "")]
    decision_select.extend(_option_html(decision, value) for value in decision_options)

    batman_status_select = [_option_html(batman_status, "")]
    batman_status_select.extend(_option_html(batman_status, value) for value in batman_status_options)

    edge_sign_select = [_option_html(edge_sign, "")]
    edge_sign_select.extend(_option_html(edge_sign, value) for value in edge_sign_options)

    summary_html = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(_fmt(value))}</td></tr>" for label, value in summary_rows
    )
    header_html = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    legacy_checked = " checked" if legacy_only else ""
    stale_checked = " checked" if stale_only else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Nightwing Dashboard</title>
    <style>
    body {{ font-family: sans-serif; margin: 16px; color: #111; }}
    form, table {{ margin-top: 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #999; padding: 6px; text-align: left; vertical-align: top; }}
    th {{ background: #eee; }}
    input, select, button {{ padding: 4px 6px; }}
    .meta {{ color: #444; }}
    .note {{ margin-top: 12px; padding: 8px 10px; background: #f7f7f7; border-left: 4px solid #999; }}
    .status-ok {{ background: #e6f4ea; color: #1d5f2c; font-weight: 600; }}
    .status-stale {{ background: #fdecea; color: #8a1c1c; font-weight: 600; }}
    .record-legacy {{ background: #fff4d6; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>Nightwing Dashboard</h1>
  <p class="meta">Source: {html.escape(str(EXECUTIONS_FILE))}</p>
  <p class="note">Older rows marked as legacy may use pre-refactor exposure semantics. Review evaluated and executed amounts with that context.</p>

  <form method="get">
    <label for="mode">mode</label>
    <select id="mode" name="mode">{"".join(mode_select)}</select>
    <label for="decision">decision</label>
    <select id="decision" name="decision">{"".join(decision_select)}</select>
    <label for="batman_status">batman.status</label>
    <select id="batman_status" name="batman_status">{"".join(batman_status_select)}</select>
    <label for="edge_sign">edge_sign</label>
    <select id="edge_sign" name="edge_sign">{"".join(edge_sign_select)}</select>
    <label for="rows">latest N rows</label>
    <input id="rows" name="rows" type="number" min="1" value="{html.escape(str(latest_n))}">
    <label><input type="checkbox" name="legacy_only" value="1"{legacy_checked}> legacy only</label>
    <label><input type="checkbox" name="stale_only" value="1"{stale_checked}> stale only</label>
    <button type="submit">Apply</button>
  </form>

  <table>
    <thead>
      <tr><th>metric</th><th>value</th></tr>
    </thead>
    <tbody>
      {summary_html}
    </tbody>
  </table>

  <table>
    <thead>
      <tr>{header_html}</tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        """Serve the filtered dashboard page from the local execution log."""
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        mode = query.get("mode", [""])[0]
        decision = query.get("decision", [""])[0]
        batman_status = query.get("batman_status", [""])[0]
        edge_sign = query.get("edge_sign", [""])[0]
        legacy_only = query.get("legacy_only", [""])[0] == "1"
        stale_only = query.get("stale_only", [""])[0] == "1"
        rows_raw = query.get("rows", ["100"])[0]
        try:
            latest_n = max(1, int(rows_raw))
        except ValueError:
            latest_n = 100

        normalized = [normalize_record(record) for record in load_records()]
        mode_options = _collect_values(normalized, "mode")
        decision_options = _collect_values(normalized, "decision")
        batman_status_options = _collect_values(normalized, "batman.status")
        edge_sign_options = _collect_values(normalized, "edge_sign")
        filtered = apply_filters(
            normalized,
            mode=mode,
            decision=decision,
            batman_status=batman_status,
            edge_sign=edge_sign,
            legacy_only=legacy_only,
            stale_only=stale_only,
            latest_n=latest_n,
        )
        summary = build_summary(filtered)
        content = render_html(
            filtered,
            summary,
            mode,
            decision,
            batman_status,
            edge_sign,
            legacy_only,
            stale_only,
            latest_n,
            mode_options,
            decision_options,
            batman_status_options,
            edge_sign_options,
        )
        body = content.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    """Run the local read-only dashboard HTTP server."""
    parser = argparse.ArgumentParser(description="Minimal local dashboard for Nightwing execution logs")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--rows", type=int, default=100, help="Default latest N rows")
    args = parser.parse_args()

    class ConfiguredDashboardHandler(DashboardHandler):
        def do_GET(self) -> None:
            if "rows=" not in self.path:
                separator = "&" if "?" in self.path else "?"
                self.path = f"{self.path}{separator}rows={args.rows}"
            super().do_GET()

    server = ThreadingHTTPServer((args.host, args.port), ConfiguredDashboardHandler)
    print(f"Nightwing dashboard listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
