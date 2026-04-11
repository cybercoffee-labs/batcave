#!/usr/bin/env python3
"""
NIGHTWING LEDGER ANALYZER — Quick analysis of trade performance

Run: python tools/analyze_ledger.py
     python tools/analyze_ledger.py --json
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
LEDGER_FILE = BASE_DIR / "storage" / "ledger" / "trades.jsonl"


def _read_ledger() -> List[Dict[str, Any]]:
    if not LEDGER_FILE.exists():
        return []
    records = []
    for line in LEDGER_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("opp_id"):  # Only real records
                records.append(r)
        except json.JSONDecodeError:
            continue
    return records


def _unique_opportunities(records: List[Dict]) -> List[Dict]:
    """Deduplicate by opp_id — keep first occurrence only."""
    seen = set()
    unique = []
    for r in records:
        opp_id = r.get("opp_id")
        if opp_id and opp_id not in seen:
            seen.add(opp_id)
            unique.append(r)
    return unique


def analyze() -> Dict[str, Any]:
    all_records = _read_ledger()
    unique = _unique_opportunities(all_records)

    if not unique:
        return {"status": "empty", "message": "No real trades in ledger"}

    edges = [r["edge_net"] for r in unique if r.get("edge_net") is not None]
    opportunities = [r for r in unique if r.get("decision") == "OPPORTUNITY"]
    passes = [r for r in unique if r.get("decision") == "PASS"]

    timestamps = []
    for r in unique:
        try:
            timestamps.append(datetime.fromisoformat(r["timestamp"]))
        except (ValueError, KeyError):
            continue

    hours_distribution = defaultdict(int)
    for ts in timestamps:
        hours_distribution[ts.hour] += 1

    edge_by_hour = defaultdict(list)
    for r in unique:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
            if r.get("edge_net") is not None:
                edge_by_hour[ts.hour].append(r["edge_net"])
        except (ValueError, KeyError):
            continue

    avg_edge_by_hour = {
        h: round(sum(edges_list) / len(edges_list), 4) for h, edges_list in sorted(edge_by_hour.items())
    }

    depths = [r["depth_estimate"] for r in unique if isinstance(r.get("depth_estimate"), (int, float))]

    opps_per_day = defaultdict(set)
    for r in unique:
        day = (r.get("timestamp") or "")[:10]
        opps_per_day[day].add(r.get("opp_id"))

    daily_opp_counts = {day: len(opps) for day, opps in sorted(opps_per_day.items())}

    spots = [r["spot_price"] for r in unique if isinstance(r.get("spot_price"), (int, float))]

    total_simulated_pnl = 0.0
    for r in opportunities:
        edge = r.get("edge_net", 0) or 0
        amount = r.get("amount_usd", 0) or 0
        total_simulated_pnl += amount * (edge / 100)

    if timestamps:
        first_ts = min(timestamps).isoformat()
        last_ts = max(timestamps).isoformat()
        duration_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600
    else:
        first_ts = last_ts = "unknown"
        duration_hours = 0

    return {
        "status": "ok",
        "date_range": {"first": first_ts, "last": last_ts, "duration_hours": round(duration_hours, 1)},
        "total_records": len(all_records),
        "unique_opportunities": len(unique),
        "decisions": {
            "opportunities": len(opportunities),
            "passes": len(passes),
            "opportunity_rate": round(len(opportunities) / len(unique) * 100, 1) if unique else 0,
        },
        "edge_stats": {
            "avg": round(sum(edges) / len(edges), 4) if edges else 0,
            "min": round(min(edges), 4) if edges else 0,
            "max": round(max(edges), 4) if edges else 0,
            "std": round((sum((e - sum(edges) / len(edges)) ** 2 for e in edges) / len(edges)) ** 0.5, 4)
            if len(edges) > 1
            else 0,
        },
        "depth_stats": {
            "avg": round(sum(depths) / len(depths), 2) if depths else 0,
            "min": round(min(depths), 2) if depths else 0,
            "max": round(max(depths), 2) if depths else 0,
        },
        "spot_price_range": {
            "min": round(min(spots), 4) if spots else 0,
            "max": round(max(spots), 4) if spots else 0,
        },
        "avg_edge_by_hour_utc": avg_edge_by_hour,
        "unique_opps_per_day": daily_opp_counts,
        "simulated_pnl": {
            "total_usd": round(total_simulated_pnl, 2),
            "total_trades": len(opportunities),
            "avg_per_trade_usd": round(total_simulated_pnl / len(opportunities), 2) if opportunities else 0,
            "total_volume_usd": len(opportunities) * 500,
        },
    }


def print_analysis():
    a = analyze()

    if a.get("status") == "empty":
        print("No real trades in ledger yet.")
        return

    s = a["edge_stats"]
    d = a["depth_stats"]
    dec = a["decisions"]
    pnl = a["simulated_pnl"]

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              NIGHTWING LEDGER ANALYSIS                       ║
╠══════════════════════════════════════════════════════════════╣
║  Period: {a['date_range']['first'][:16]} → {a['date_range']['last'][:16]}
║  Duration: {a['date_range']['duration_hours']} hours
║  Total records: {a['total_records']} | Unique opps: {a['unique_opportunities']}
╠══════════════════════════════════════════════════════════════╣
║  DECISIONS
║  Opportunities: {dec['opportunities']:<6} Passes: {dec['passes']:<6} Rate: {dec['opportunity_rate']}%
╠══════════════════════════════════════════════════════════════╣
║  EDGE (after friction)
║  Avg: {s['avg']:+.4f}%   Min: {s['min']:+.4f}%   Max: {s['max']:+.4f}%
║  Std: {s['std']:.4f}%    Friction: 0.25%
╠══════════════════════════════════════════════════════════════╣
║  DEPTH (USD available per opportunity)
║  Avg: ${d['avg']:,.0f}   Min: ${d['min']:,.0f}   Max: ${d['max']:,.0f}
╠══════════════════════════════════════════════════════════════╣
║  SPOT PRICE MXN/USD
║  Range: {a['spot_price_range']['min']:.4f} — {a['spot_price_range']['max']:.4f}
╠══════════════════════════════════════════════════════════════╣
║  SIMULATED P&L
║  Total: ${pnl['total_usd']:+.2f} USD across {pnl['total_trades']} trades
║  Avg per trade: ${pnl['avg_per_trade_usd']:+.2f} USD
║  Volume: ${pnl['total_volume_usd']:,} USD
╠══════════════════════════════════════════════════════════════╣
║  EDGE BY HOUR (UTC)""")

    for hour, avg in sorted(a["avg_edge_by_hour_utc"].items()):
        bar = "█" * int(avg * 20) if avg > 0 else ""
        print(f"║  {hour:02d}:00  {avg:+.4f}%  {bar}")

    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  UNIQUE OPPORTUNITIES PER DAY")
    for day, count in sorted(a["unique_opps_per_day"].items()):
        print(f"║  {day}: {count} unique opportunities")

    print("╚══════════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(analyze(), indent=2))
    else:
        print_analysis()
