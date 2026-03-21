"""
Standalone read-only research metrics over HARVEY signal storage.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.economic_graph import _load_signal_records_from_db
from core.economic_graph import build_graph


DEFAULT_DB_PATH = BASE_DIR / "storage" / "batman.db"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _market(record: dict[str, Any]) -> str:
    market = record.get("market")
    if isinstance(market, str) and market.strip():
        return market.strip().upper()
    venue = record.get("venue")
    if isinstance(venue, str) and venue.strip():
        return venue.strip().upper()
    return "UNKNOWN"


def _edge_net(record: dict[str, Any]) -> float | None:
    for key in ("edge_net", "basis_pct", "spread_pct", "p2p_premium", "edge"):
        value = _safe_float(record.get(key))
        if value is not None:
            return value
    return None


def _depth(record: dict[str, Any]) -> float | None:
    return _safe_float(record.get("depth_estimate"))


def _viable(record: dict[str, Any]) -> bool | None:
    if isinstance(record.get("viable"), bool):
        return bool(record["viable"])
    edge_net = _edge_net(record)
    if edge_net is None:
        return None
    return edge_net > 0


def _build_research_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    graph = build_graph(records=records)

    edges = [_edge_net(record) for record in records]
    depth_values = [_depth(record) for record in records if _depth(record) is not None]
    positive_edges = [value for value in edges if value is not None and value > 0]
    negative_edges = [value for value in edges if value is not None and value < 0]

    per_market: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"signals": 0, "edge_values": [], "depth_values": [], "viable_total": 0, "viable_known": 0}
    )
    persistent: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"signals": 0, "viable_total": 0, "viable_known": 0, "edge_values": []}
    )

    for record in records:
        market = _market(record)
        asset = str(record.get("asset") or "UNKNOWN").upper()
        scanner_id = str(record.get("scanner_id") or "UNKNOWN")
        edge_net = _edge_net(record)
        depth = _depth(record)
        viable = _viable(record)

        bucket = per_market[market]
        bucket["signals"] += 1
        if edge_net is not None:
            bucket["edge_values"].append(edge_net)
        if depth is not None:
            bucket["depth_values"].append(depth)
        if viable is not None:
            bucket["viable_known"] += 1
            bucket["viable_total"] += int(viable)

        key = (market, asset, scanner_id)
        persistent_bucket = persistent[key]
        persistent_bucket["signals"] += 1
        if edge_net is not None:
            persistent_bucket["edge_values"].append(edge_net)
        if viable is not None:
            persistent_bucket["viable_known"] += 1
            persistent_bucket["viable_total"] += int(viable)

    structural_edge = []
    for market, payload in per_market.items():
        edge_values = payload["edge_values"]
        depth_vals = payload["depth_values"]
        viable_pct = None
        if payload["viable_known"]:
            viable_pct = round((payload["viable_total"] / payload["viable_known"]) * 100, 2)
        structural_edge.append(
            {
                "market": market,
                "signals": payload["signals"],
                "average_edge_net": round(sum(edge_values) / len(edge_values), 6) if edge_values else None,
                "average_depth_estimate": round(sum(depth_vals) / len(depth_vals), 2) if depth_vals else None,
                "viable_signal_percentage": viable_pct,
            }
        )
    structural_edge.sort(
        key=lambda item: (
            -(item["average_edge_net"] or float("-inf")),
            -(item["average_depth_estimate"] or float("-inf")),
            item["market"],
        )
    )

    persistent_rows = []
    for (market, asset, scanner_id), payload in persistent.items():
        if payload["signals"] < 2:
            continue
        viable_pct = None
        if payload["viable_known"]:
            viable_pct = round((payload["viable_total"] / payload["viable_known"]) * 100, 2)
        persistent_rows.append(
            {
                "market": market,
                "asset": asset,
                "scanner_id": scanner_id,
                "signals": payload["signals"],
                "average_edge_net": round(sum(payload["edge_values"]) / len(payload["edge_values"]), 6)
                if payload["edge_values"]
                else None,
                "viable_signal_percentage": viable_pct,
            }
        )
    persistent_rows.sort(
        key=lambda item: (-item["signals"], -(item["viable_signal_percentage"] or -1), item["market"], item["asset"])
    )

    liquidity_distribution = [
        {
            "market": row["label"],
            "weighted_degree": row["weighted_degree"],
            "inbound_flow": row["inbound_flow"],
            "edges": row["edge_count"],
        }
        for row in graph["centrality"]["liquidity_hubs"][:10]
    ]

    return {
        "summary": {
            "signals_total": len(records),
            "graph_nodes": graph["summary"]["nodes_total"],
            "graph_edges": graph["summary"]["edges_total"],
            "positive_edge_count": len(positive_edges),
            "negative_edge_count": len(negative_edges),
            "average_depth_estimate": round(sum(depth_values) / len(depth_values), 2) if depth_values else None,
        },
        "edge_distribution": {
            "positive_count": len(positive_edges),
            "negative_count": len(negative_edges),
            "flat_count": sum(1 for value in edges if value == 0),
            "average_positive_edge": round(sum(positive_edges) / len(positive_edges), 6) if positive_edges else None,
            "average_negative_edge": round(sum(negative_edges) / len(negative_edges), 6) if negative_edges else None,
        },
        "liquidity_distribution": liquidity_distribution,
        "persistent_opportunities": persistent_rows[:10],
        "markets_by_structural_edge": structural_edge[:10],
        "graph_summary": graph["summary"],
    }


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "BATCAVE Research Metrics",
        "",
        f"Signals: {payload['summary']['signals_total']}",
        f"Graph nodes/edges: {payload['summary']['graph_nodes']}/{payload['summary']['graph_edges']}",
        f"Positive edges: {payload['edge_distribution']['positive_count']}",
        f"Negative edges: {payload['edge_distribution']['negative_count']}",
        "",
        "Markets by structural edge:",
    ]
    for row in payload["markets_by_structural_edge"][:5]:
        lines.append(
            f"  - {row['market']}: avg_edge={row['average_edge_net']} "
            f"avg_depth={row['average_depth_estimate']} viable={row['viable_signal_percentage']}"
        )

    lines.append("")
    lines.append("Liquidity distribution:")
    for row in payload["liquidity_distribution"][:5]:
        lines.append(f"  - {row['market']}: weighted_degree={row['weighted_degree']} inbound={row['inbound_flow']}")

    lines.append("")
    lines.append("Persistent opportunities:")
    for row in payload["persistent_opportunities"][:5]:
        lines.append(
            f"  - {row['market']}/{row['asset']} via {row['scanner_id']}: "
            f"signals={row['signals']} viable={row['viable_signal_percentage']}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="BATCAVE read-only research metrics")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="override HARVEY SQLite path")
    args = parser.parse_args()

    records = _load_signal_records_from_db(args.db)
    payload = _build_research_payload(records)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(render_report(payload))


if __name__ == "__main__":
    main()
