#!/usr/bin/env python3
"""
Multi-Strategy CLI Dashboard for Batman Flow Engine.

Displays aggregated statistics for all scanner types (A-H) from the last 24 hours.

Usage:
    python tools/multi_strategy_dashboard.py           # Human-readable output
    python tools/multi_strategy_dashboard.py --json   # JSON output
"""

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
OPPORTUNITIES_LOG = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

# Scanner type descriptions
SCANNER_TYPES = {
    "A": "Cross-Exchange",
    "B": "Spot vs Futures Basis",
    "C": "P2P Premium",
    "D": "Multi-Exchange",
    "E": "Funding Rate",
    "F": "Cross-Currency P2P",
    "G": "Merchant Spread",
    "H": "Stablecoin Depeg",
}


def read_opportunities_last_24h() -> list[dict[str, Any]]:
    """Read opportunities from the last 24 hours."""
    if not OPPORTUNITIES_LOG.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_str = cutoff.isoformat()

    opportunities = []
    with OPPORTUNITIES_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                ts = record.get("ts", "")
                # Simple ISO timestamp comparison
                if ts >= cutoff_str:
                    opportunities.append(record)
            except json.JSONDecodeError:
                continue

    return opportunities


def extract_edge(record: dict[str, Any]) -> float | None:
    """Extract edge value from opportunity record."""
    edge_fields = (
        "edge_net",
        "p2p_premium",
        "basis_pct",
        "spread_pct",
        "merchant_spread_pct",
        "funding_rate",
        "annualized_pct",
        "cross_premium_spread",
        "deviation_pct",
    )
    for field in edge_fields:
        value = record.get(field)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def group_by_scanner_type(opportunities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group opportunities by scanner type."""
    groups: dict[str, list[dict[str, Any]]] = {t: [] for t in SCANNER_TYPES.keys()}
    groups["UNKNOWN"] = []

    for opp in opportunities:
        opp_type = opp.get("type", "UNKNOWN")
        if opp_type in groups:
            groups[opp_type].append(opp)
        else:
            groups["UNKNOWN"].append(opp)

    return groups


def compute_stats(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute statistics for a list of opportunities."""
    if not opportunities:
        return {
            "count": 0,
            "avg_edge": None,
            "best_edge": None,
            "best_opp_id": None,
        }

    edges = []
    best_edge = None
    best_opp_id = None

    for opp in opportunities:
        edge = extract_edge(opp)
        if edge is not None:
            edges.append(edge)
            if best_edge is None or abs(edge) > abs(best_edge):
                best_edge = edge
                best_opp_id = opp.get("opp_id")

    return {
        "count": len(opportunities),
        "avg_edge": round(sum(edges) / len(edges), 4) if edges else None,
        "best_edge": round(best_edge, 4) if best_edge is not None else None,
        "best_opp_id": best_opp_id,
    }


def find_best_opportunity(opportunities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the opportunity with the highest edge_net."""
    best_opp = None
    best_edge = None

    for opp in opportunities:
        edge = extract_edge(opp)
        if edge is not None:
            if best_edge is None or edge > best_edge:
                best_edge = edge
                best_opp = opp

    return best_opp


def build_report(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the full dashboard report."""
    groups = group_by_scanner_type(opportunities)

    scanner_stats = {}
    for scanner_type, opps in groups.items():
        if scanner_type == "UNKNOWN" and not opps:
            continue
        stats = compute_stats(opps)
        scanner_stats[scanner_type] = {
            "name": SCANNER_TYPES.get(scanner_type, "Unknown"),
            **stats,
        }

    best_opp = find_best_opportunity(opportunities)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "period": "last_24h",
        "total_opportunities": len(opportunities),
        "scanner_stats": scanner_stats,
        "best_opportunity": {
            "opp_id": best_opp.get("opp_id") if best_opp else None,
            "type": best_opp.get("type") if best_opp else None,
            "edge": extract_edge(best_opp) if best_opp else None,
            "asset": best_opp.get("asset") or best_opp.get("market") if best_opp else None,
            "venue": best_opp.get("venue") or best_opp.get("exchange") if best_opp else None,
        }
        if best_opp
        else None,
    }


def print_human_readable(report: dict[str, Any]) -> None:
    """Print report in human-readable format."""
    print("=" * 60)
    print("       BATMAN MULTI-STRATEGY DASHBOARD")
    print("=" * 60)
    print(f"Generated: {report['timestamp']}")
    print("Period: Last 24 hours")
    print(f"Total Opportunities: {report['total_opportunities']}")
    print()

    print("-" * 60)
    print(f"{'Type':<6} {'Scanner':<22} {'Count':>6} {'Avg Edge':>10} {'Best Edge':>10}")
    print("-" * 60)

    for scanner_type in sorted(report["scanner_stats"].keys()):
        if scanner_type == "UNKNOWN":
            continue
        stats = report["scanner_stats"][scanner_type]
        name = stats["name"][:20]
        count = stats["count"]
        avg_edge = f"{stats['avg_edge']:.2f}%" if stats["avg_edge"] is not None else "-"
        best_edge = f"{stats['best_edge']:.2f}%" if stats["best_edge"] is not None else "-"
        print(f"{scanner_type:<6} {name:<22} {count:>6} {avg_edge:>10} {best_edge:>10}")

    # Print UNKNOWN if any
    if "UNKNOWN" in report["scanner_stats"]:
        stats = report["scanner_stats"]["UNKNOWN"]
        if stats["count"] > 0:
            print(f"{'?':<6} {'Unknown':<22} {stats['count']:>6} {'-':>10} {'-':>10}")

    print("-" * 60)
    print()

    best = report.get("best_opportunity")
    if best and best.get("opp_id"):
        print("BEST OPPORTUNITY NOW")
        print("-" * 60)
        print(f"  ID:     {best['opp_id']}")
        print(f"  Type:   {best['type']} ({SCANNER_TYPES.get(best['type'], 'Unknown')})")
        print(f"  Edge:   {best['edge']:.2f}%")
        print(f"  Asset:  {best['asset']}")
        print(f"  Venue:  {best['venue']}")
    else:
        print("BEST OPPORTUNITY NOW: None found")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Multi-Strategy CLI Dashboard for Batman Flow Engine")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    args = parser.parse_args()

    opportunities = read_opportunities_last_24h()
    report = build_report(opportunities)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_human_readable(report)


if __name__ == "__main__":
    main()
