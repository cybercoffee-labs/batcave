"""
Read-only economic graph analytics over HARVEY signal storage.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "storage" / "batman.db"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _load_signal_records_from_db(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return []

    try:
        rows = conn.execute(
            """
            SELECT
                opp_id,
                timestamp,
                scanner_id,
                type,
                asset,
                venue,
                edge,
                observe_only,
                raw_json
            FROM signals
            ORDER BY timestamp ASC, opp_id ASC
            """
        ).fetchall()
    except sqlite3.Error:
        conn.close()
        return []
    conn.close()

    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        payload: dict[str, Any] = {}
        raw_json = record.get("raw_json")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                payload = parsed
        merged = payload.copy()
        merged.update(
            {
                "opp_id": payload.get("opp_id") or record.get("opp_id"),
                "ts": payload.get("ts") or record.get("timestamp"),
                "timestamp": payload.get("timestamp") or record.get("timestamp"),
                "scanner_id": payload.get("scanner_id") or record.get("scanner_id"),
                "type": payload.get("type") or record.get("type"),
                "asset": payload.get("asset") or record.get("asset"),
                "venue": payload.get("venue") or record.get("venue"),
                "edge": payload.get("edge", record.get("edge")),
                "observe_only": payload.get("observe_only", record.get("observe_only")),
            }
        )
        records.append(merged)
    return records


def _normalize_market(record: dict[str, Any]) -> str | None:
    for key in ("market", "quote_currency", "fiat"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    venue = record.get("venue")
    if isinstance(venue, str) and venue.strip():
        return venue.strip().upper()
    return None


def _normalize_asset(record: dict[str, Any]) -> str | None:
    asset = record.get("asset")
    if isinstance(asset, str) and asset.strip():
        return asset.strip().upper()
    symbol = record.get("symbol")
    if isinstance(symbol, str) and symbol.strip():
        return symbol.strip().upper()
    return None


def _normalize_edge_net(record: dict[str, Any]) -> float | None:
    for key in ("edge_net", "basis_pct", "spread_pct", "p2p_premium", "edge"):
        value = _safe_float(record.get(key))
        if value is not None:
            return value
    return None


def _normalize_depth(record: dict[str, Any]) -> float | None:
    for key in ("depth_estimate", "notional_depth", "liquidity_depth"):
        value = _safe_float(record.get(key))
        if value is not None:
            return value
    return None


def _normalize_merchant_count(record: dict[str, Any]) -> int:
    value = record.get("merchant_count")
    try:
        if value is None:
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _normalize_viable(record: dict[str, Any], edge_net: float | None) -> bool | None:
    viable = record.get("viable")
    if isinstance(viable, bool):
        return viable
    if viable in (0, 1):
        return bool(viable)
    if edge_net is None:
        return None
    return edge_net > 0


def _normalize_record(record: dict[str, Any]) -> dict[str, Any] | None:
    asset = _normalize_asset(record)
    market = _normalize_market(record)
    scanner_id = record.get("scanner_id")
    if not isinstance(scanner_id, str) or not scanner_id.strip():
        scanner_id = "UNKNOWN"
    else:
        scanner_id = scanner_id.strip()

    if not asset or not market:
        return None

    edge_net = _normalize_edge_net(record)
    depth_estimate = _normalize_depth(record)
    viable = _normalize_viable(record, edge_net)
    return {
        "opp_id": record.get("opp_id"),
        "timestamp": record.get("ts") or record.get("timestamp"),
        "asset": asset,
        "market": market,
        "scanner_id": scanner_id,
        "venue": record.get("venue"),
        "avg_edge_net": edge_net,
        "avg_depth_estimate": depth_estimate,
        "merchant_count": _normalize_merchant_count(record),
        "viable": viable,
        "observe_only": bool(record.get("observe_only", False)),
    }


def _make_node(node_type: str, value: str) -> dict[str, Any]:
    return {
        "id": f"{node_type}:{value}",
        "label": value,
        "type": node_type,
    }


def compute_flow_scores(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    computed: list[dict[str, Any]] = []
    for edge in edges:
        edge_net = _safe_float(edge.get("avg_edge_net"))
        depth = _safe_float(edge.get("avg_depth_estimate"))
        flow_score = None
        if edge_net is not None and depth is not None:
            flow_score = round((edge_net * depth) / 1000.0, 6)

        updated = dict(edge)
        updated["flow_score"] = flow_score
        computed.append(updated)
    return computed


def build_graph(
    records: list[dict[str, Any]] | None = None,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    source_records = records
    if source_records is None:
        resolved_db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        source_records = _load_signal_records_from_db(resolved_db_path)

    normalized = []
    for record in source_records:
        if not isinstance(record, dict):
            continue
        normalized_record = _normalize_record(record)
        if normalized_record is not None:
            normalized.append(normalized_record)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        grouped[(record["asset"], record["market"], record["scanner_id"])].append(record)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for (asset, market, scanner_id), group in sorted(grouped.items()):
        asset_node = _make_node("currency", asset)
        market_node = _make_node("market", market)
        nodes[asset_node["id"]] = asset_node
        nodes[market_node["id"]] = market_node

        edge_values = [item["avg_edge_net"] for item in group if item["avg_edge_net"] is not None]
        depth_values = [item["avg_depth_estimate"] for item in group if item["avg_depth_estimate"] is not None]
        viable_values = [item["viable"] for item in group if item["viable"] is not None]
        merchant_values = [item["merchant_count"] for item in group if item["merchant_count"] > 0]
        timestamps = [ts for ts in (_parse_timestamp(item["timestamp"]) for item in group) if ts is not None]

        edges.append(
            {
                "source": asset_node["id"],
                "target": market_node["id"],
                "asset": asset,
                "market": market,
                "scanner_id": scanner_id,
                "avg_edge_net": _round(sum(edge_values) / len(edge_values), 6) if edge_values else None,
                "avg_depth_estimate": _round(sum(depth_values) / len(depth_values), 2) if depth_values else None,
                "viable_pct": _round((sum(bool(v) for v in viable_values) / len(viable_values)) * 100, 2)
                if viable_values
                else None,
                "merchant_count": round(sum(merchant_values) / len(merchant_values), 2) if merchant_values else 0.0,
                "signal_count": len(group),
                "latest_timestamp": max(timestamps).isoformat() if timestamps else None,
                "observe_only_count": sum(1 for item in group if item.get("observe_only")),
            }
        )

    scored_edges = compute_flow_scores(edges)
    centrality = compute_centrality({"nodes": list(nodes.values()), "edges": scored_edges})
    top_edges = sorted(
        scored_edges,
        key=lambda item: (
            -abs(item["flow_score"] or 0.0),
            item["asset"],
            item["market"],
            item["scanner_id"],
        ),
    )
    summary = {
        "signals_considered": len(normalized),
        "nodes_total": len(nodes),
        "edges_total": len(scored_edges),
        "currencies_total": sum(1 for node in nodes.values() if node["type"] == "currency"),
        "markets_total": sum(1 for node in nodes.values() if node["type"] == "market"),
        "avg_edge_net": _round(
            sum(edge["avg_edge_net"] for edge in scored_edges if edge["avg_edge_net"] is not None)
            / max(1, sum(1 for edge in scored_edges if edge["avg_edge_net"] is not None)),
            6,
        )
        if any(edge["avg_edge_net"] is not None for edge in scored_edges)
        else None,
        "avg_depth_estimate": _round(
            sum(edge["avg_depth_estimate"] for edge in scored_edges if edge["avg_depth_estimate"] is not None)
            / max(1, sum(1 for edge in scored_edges if edge["avg_depth_estimate"] is not None)),
            2,
        )
        if any(edge["avg_depth_estimate"] is not None for edge in scored_edges)
        else None,
        "viable_pct": _round(
            sum(edge["viable_pct"] for edge in scored_edges if edge["viable_pct"] is not None)
            / max(1, sum(1 for edge in scored_edges if edge["viable_pct"] is not None)),
            2,
        )
        if any(edge["viable_pct"] is not None for edge in scored_edges)
        else None,
        "top_edges_by_flow": top_edges[:5],
        "liquidity_hubs": centrality["liquidity_hubs"][:5],
        "central_nodes": centrality["central_nodes"][:5],
    }

    return {
        "nodes": sorted(nodes.values(), key=lambda item: (item["type"], item["label"])),
        "edges": scored_edges,
        "summary": summary,
        "centrality": centrality,
    }


def compute_centrality(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_map = {node["id"]: node for node in nodes if isinstance(node, dict) and "id" in node}
    inbound: dict[str, float] = defaultdict(float)
    outbound: dict[str, float] = defaultdict(float)
    edge_counts: dict[str, int] = defaultdict(int)

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        weight = abs(_safe_float(edge.get("flow_score")) or 0.0)
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str):
            outbound[source] += weight
            edge_counts[source] += 1
        if isinstance(target, str):
            inbound[target] += weight
            edge_counts[target] += 1

    central_nodes = []
    for node_id, node in node_map.items():
        total_weight = inbound[node_id] + outbound[node_id]
        central_nodes.append(
            {
                "node_id": node_id,
                "label": node["label"],
                "type": node["type"],
                "weighted_degree": round(total_weight, 6),
                "inbound_flow": round(inbound[node_id], 6),
                "outbound_flow": round(outbound[node_id], 6),
                "edge_count": edge_counts[node_id],
            }
        )

    central_nodes.sort(key=lambda item: (-item["weighted_degree"], -item["edge_count"], item["label"], item["type"]))
    liquidity_hubs = [item for item in central_nodes if item["type"] == "market"]
    return {
        "central_nodes": central_nodes,
        "liquidity_hubs": liquidity_hubs,
    }


def export_graph_json(
    graph: dict[str, Any] | None = None,
    *,
    records: list[dict[str, Any]] | None = None,
    db_path: str | Path | None = None,
) -> str:
    if graph is None:
        graph = build_graph(records=records, db_path=db_path)
    return json.dumps(graph, indent=2, sort_keys=True)


__all__ = [
    "build_graph",
    "compute_centrality",
    "compute_flow_scores",
    "export_graph_json",
]
