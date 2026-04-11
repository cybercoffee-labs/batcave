"""
BATCAVE observatory CLI and localhost dashboard.

Default mode prints a human-readable terminal report.
Use `--json` for machine-readable output.
Use `--serve` to expose a local read-only dashboard on 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.observatory import build_architecture_status


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _format_num(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_dashboard_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": snapshot["generated_at"],
        "summary": snapshot["summary"],
        "harvey": snapshot["harvey"],
        "temporal": snapshot["temporal"],
        "system_health": snapshot["system_health"],
        "architecture": snapshot["architecture"],
        "market_flow_summary": snapshot["market_flow_summary"],
        "economic_graph": snapshot["economic_graph"],
        "graph_summary": snapshot["graph_summary"],
        "top_markets_by_flow": snapshot["top_markets_by_flow"],
        "central_nodes": snapshot["central_nodes"],
    }


def render_terminal_status(snapshot: dict[str, Any]) -> str:
    summary = snapshot["summary"]
    flow = snapshot["market_flow_summary"]
    system = snapshot["system_health"]
    architecture = snapshot["architecture"]
    harvey = snapshot["harvey"]
    temporal = snapshot["temporal"]
    economic_graph = snapshot["economic_graph"]

    lines = [
        "BATCAVE Economic Flow Observatory",
        f"Generated: {snapshot['generated_at']}",
        "",
        "Summary",
        f"  Signals: {summary['signals_total']}",
        f"  Scanners: {summary['scanners_total']}",
        f"  Markets: {summary['markets_total']}",
        f"  Viable: {_format_pct(summary['viable_signal_percentage'])}",
        f"  Stale signals: {summary['stale_signals']}",
        f"  Kill switch: {summary['kill_switch_active']}",
        f"  Graph nodes/edges: {summary['graph_nodes']}/{summary['graph_edges']}",
        "",
        "Market Flow",
        f"  Avg edge_net: {_format_num(flow['average_edge_net'])}",
        f"  Avg depth_estimate: {_format_num(flow['average_depth_estimate'])}",
        "  Top markets:",
    ]
    for row in flow["top_markets_by_signal_count"]:
        lines.append(
            "    - "
            f"{row['market']}: signals={row['signals']} "
            f"avg_edge={_format_num(row['average_edge_net'])} "
            f"avg_depth={_format_num(row['average_depth_estimate'])} "
            f"viable={_format_pct(row['viable_signal_percentage'])}"
        )

    lines.append("  Top scanners:")
    for row in flow["top_scanners_by_signal_count"]:
        lines.append(f"    - {row['scanner_id']}: {row['signals']}")

    lines.extend(
        [
            "",
            "System Health",
            f"  Last Batman run: {system['last_batman_run_timestamp']}",
            f"  Last signal: {system['last_signal_timestamp']}",
            f"  Signal age (min): {_format_num(system['signal_age_minutes'])}",
            f"  Nightwing last execution: {system['nightwing_last_execution']['timestamp'] or system['nightwing_last_execution']['status']}",
            f"  Dataset growth 24h: {system['dataset_growth']['signals_last_24h']} vs {system['dataset_growth']['signals_previous_24h']} "
            f"(delta {system['dataset_growth']['delta_signals']}, pct {system['dataset_growth']['delta_percentage'] if system['dataset_growth']['delta_percentage'] is not None else 'n/a'})",
            "",
            "HARVEY Per Scanner",
        ]
    )

    for scanner, payload in harvey["signals_per_scanner"].items():
        lines.append(
            f"  - {scanner}: signals={payload['signals']} "
            f"avg_edge_net={_format_num(payload['average_edge_net'])} "
            f"avg_depth={_format_num(payload['average_depth_estimate'])} "
            f"viable={_format_pct(payload['viable_signal_percentage'])}"
        )

    lines.extend(
        [
            "",
            "Temporal",
            "  Signals per hour:",
        ]
    )
    for row in temporal["signals_per_hour"][-6:]:
        lines.append(f"    - {row['bucket']}: {row['count']}")

    lines.extend(
        [
            "",
            "Economic Graph",
            f"  Signals considered: {economic_graph['graph_summary']['signals_considered']}",
            "  Top markets by flow:",
        ]
    )
    for row in snapshot["top_markets_by_flow"]:
        lines.append(
            f"    - {row['label']}: weighted_degree={_format_num(row['weighted_degree'])} edges={row['edge_count']}"
        )

    lines.extend(
        [
            "  Central nodes:",
        ]
    )
    for row in snapshot["central_nodes"]:
        lines.append(f"    - {row['label']} ({row['type']}): weighted_degree={_format_num(row['weighted_degree'])}")

    lines.extend(
        [
            "",
            "Architecture",
            f"  Active personas: {', '.join(architecture['active_personas']) or 'none'}",
            f"  Scaffold modules: {', '.join(architecture['scaffold_modules']) or 'none'}",
            f"  Missing modules: {', '.join(architecture['missing_modules']) or 'none'}",
            f"  Partial personas: {', '.join(architecture['partial_personas']) or 'none'}",
        ]
    )

    return "\n".join(lines)


def _html_dashboard(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(build_dashboard_payload(snapshot))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BATCAVE Observatory</title>
  <style>
    :root {{
      --bg: #f3f0e8;
      --panel: #fffdf7;
      --ink: #101418;
      --muted: #5a6773;
      --border: #d8d2c3;
      --accent: #1f4d3a;
      --warn: #9c2f2f;
      --ok: #246b45;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      background: linear-gradient(180deg, #e7e0d0 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1, h2 {{ margin: 0 0 12px; }}
    p {{ color: var(--muted); margin: 0 0 16px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      box-shadow: 0 8px 20px rgba(16, 20, 24, 0.04);
    }}
    .metric {{
      font-size: 1.8rem;
      line-height: 1;
      margin-top: 8px;
    }}
    .ok {{ color: var(--ok); }}
    .warn {{ color: var(--warn); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }}
    th, td {{
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .row {{
      display: grid;
      grid-template-columns: 1.3fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .mono {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.88rem; }}
    @media (max-width: 860px) {{
      .row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>BATCAVE Economic Flow Observatory</h1>
    <p>Read-only local telemetry view over existing BATMAN, HARVEY, and GORDON artifacts.</p>

    <div class="grid" id="summary"></div>

    <div class="row">
      <section class="panel">
        <h2>Market Flow Table</h2>
        <table id="markets"></table>
      </section>
      <section class="panel">
        <h2>System Health</h2>
        <table id="health"></table>
      </section>
    </div>

    <div class="row">
      <section class="panel">
        <h2>Scanner Activity</h2>
        <table id="scanners"></table>
      </section>
      <section class="panel">
        <h2>Temporal Activity</h2>
        <table id="temporal"></table>
      </section>
    </div>

    <div class="row">
      <section class="panel">
        <h2>Dataset Growth</h2>
        <table id="growth"></table>
      </section>
      <section class="panel">
        <h2>Persona / Module Status</h2>
        <table id="personas"></table>
      </section>
    </div>

    <div class="row">
      <section class="panel">
        <h2>Top Markets By Flow</h2>
        <table id="market-flow"></table>
      </section>
      <section class="panel">
        <h2>Top Nodes By Flow Score</h2>
        <table id="nodes"></table>
      </section>
    </div>
  </div>
  <script>
    const data = {payload};
    const fmt = (v) => v === null || v === undefined ? "n/a" : v;
    const pct = (v) => v === null || v === undefined ? "n/a" : `${{Number(v).toFixed(2)}}%`;
    const rows = (entries) => entries.map(([k, v]) => `<tr><th>${{k}}</th><td class="mono">${{v}}</td></tr>`).join("");

    document.getElementById("summary").innerHTML = [
      ["Signals", data.summary.signals_total],
      ["Viable %", pct(data.summary.viable_signal_percentage)],
      ["Stale", data.summary.stale_signals ? '<span class="warn">STALE</span>' : '<span class="ok">FRESH</span>'],
      ["Dataset Δ24h", data.system_health.dataset_growth.delta_signals],
      ["Graph Edges", data.summary.graph_edges],
      ["Active Personas", data.architecture.summary.active],
      ["Scaffold Modules", data.architecture.summary.scaffold],
    ].map(([label, value]) => `<div class="panel"><div>${{label}}</div><div class="metric">${{value}}</div></div>`).join("");

    document.getElementById("markets").innerHTML =
      `<tr><th>Market</th><th>Signals</th><th>Avg edge</th><th>Avg depth</th><th>Viable %</th></tr>` +
      data.market_flow_summary.top_markets_by_signal_count.map((row) =>
        `<tr><td>${{row.market}}</td><td>${{row.signals}}</td><td>${{fmt(row.average_edge_net)}}</td><td>${{fmt(row.average_depth_estimate)}}</td><td>${{pct(row.viable_signal_percentage)}}</td></tr>`
      ).join("");

    document.getElementById("health").innerHTML =
      `<tr><th>Metric</th><th>Value</th></tr>` +
      rows([
        ["Last Batman run", fmt(data.system_health.last_batman_run_timestamp)],
        ["Last signal", fmt(data.system_health.last_signal_timestamp)],
        ["Signal age (min)", fmt(data.system_health.signal_age_minutes)],
        ["Nightwing", fmt(data.system_health.nightwing_last_execution.timestamp || data.system_health.nightwing_last_execution.status)],
        ["Kill switch", String(data.system_health.gordon.kill_switch_active)],
      ]);

    document.getElementById("scanners").innerHTML =
      `<tr><th>Scanner</th><th>Signals</th><th>Avg edge_net</th><th>Avg depth</th><th>Viable %</th></tr>` +
      Object.entries(data.harvey.signals_per_scanner).map(([scanner, payload]) =>
        `<tr><td>${{scanner}}</td><td>${{payload.signals}}</td><td>${{fmt(payload.average_edge_net)}}</td><td>${{fmt(payload.average_depth_estimate)}}</td><td>${{pct(payload.viable_signal_percentage)}}</td></tr>`
      ).join("");

    document.getElementById("temporal").innerHTML =
      `<tr><th>Bucket</th><th>Count</th></tr>` +
      data.temporal.signals_per_hour.slice(-10).map((row) =>
        `<tr><td>${{row.bucket}}</td><td>${{row.count}}</td></tr>`
      ).join("");

    document.getElementById("growth").innerHTML =
      `<tr><th>Metric</th><th>Value</th></tr>` +
      rows([
        ["Signals last 24h", data.system_health.dataset_growth.signals_last_24h],
        ["Signals previous 24h", data.system_health.dataset_growth.signals_previous_24h],
        ["Delta signals", data.system_health.dataset_growth.delta_signals],
        ["Delta %", fmt(data.system_health.dataset_growth.delta_percentage)],
        ["Recent daily average", fmt(data.system_health.dataset_growth.recent_daily_average)],
      ]);

    document.getElementById("personas").innerHTML =
      `<tr><th>Persona</th><th>Repo state</th><th>Status</th></tr>` +
      data.architecture.personas.map((row) =>
        `<tr><td>${{row.title}}</td><td>${{row.repo_state}}</td><td>${{row.status}}</td></tr>`
      ).join("");

    document.getElementById("market-flow").innerHTML =
      `<tr><th>Market</th><th>Weighted degree</th><th>Inbound</th><th>Edges</th></tr>` +
      data.top_markets_by_flow.map((row) =>
        `<tr><td>${{row.label}}</td><td>${{fmt(row.weighted_degree)}}</td><td>${{fmt(row.inbound_flow)}}</td><td>${{row.edge_count}}</td></tr>`
      ).join("");

    document.getElementById("nodes").innerHTML =
      `<tr><th>Node</th><th>Type</th><th>Weighted degree</th><th>Edges</th></tr>` +
      data.central_nodes.map((row) =>
        `<tr><td>${{row.label}}</td><td>${{row.type}}</td><td>${{fmt(row.weighted_degree)}}</td><td>${{row.edge_count}}</td></tr>`
      ).join("");
  </script>
</body>
</html>"""


class ObservatoryHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        snapshot = build_architecture_status()
        dashboard_payload = build_dashboard_payload(snapshot)
        if self.path == "/api/status":
            body = json.dumps(snapshot, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/dashboard":
            body = json.dumps(dashboard_payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path not in ("/", "/index.html"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        body = _html_dashboard(snapshot).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _serve_dashboard(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), ObservatoryHandler)
    print(f"BATCAVE observatory dashboard available at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="BATCAVE observatory status")
    parser.add_argument("--json", action="store_true", help="print the raw status snapshot as JSON")
    parser.add_argument("--serve", action="store_true", help="serve the localhost read-only dashboard")
    parser.add_argument("--port", type=int, default=8765, help="dashboard port when using --serve")
    args = parser.parse_args()

    if args.serve:
        _serve_dashboard(args.port)
        return

    snapshot = build_architecture_status()
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return
    print(render_terminal_status(snapshot))


if __name__ == "__main__":
    main()
