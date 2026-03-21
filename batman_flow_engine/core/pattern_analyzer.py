"""
Pattern Analyzer — Historical analysis of opportunities

Produces JSON data for the dashboard:
- Best hours by scanner
- Best days of week
- Edge distribution
- Trends over time
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
PATTERNS_FILE = BASE_DIR / "storage" / "patterns.json"


def analyze_patterns(hours_back: int = 168) -> Dict[str, Any]:
    """Analyze patterns from last N hours (default 7 days)."""
    if not OPPS_FILE.exists():
        return {"error": "No data file"}

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()

    opps = []
    for line in OPPS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("ts", "") > cutoff:
                opps.append(r)
        except Exception:
            continue

    if not opps:
        return {"error": "No recent data", "cutoff": cutoff}

    # Parse timestamps
    for o in opps:
        try:
            ts = datetime.fromisoformat(o["ts"].replace("Z", "+00:00"))
            o["_hour"] = ts.hour
            o["_dow"] = ts.strftime("%A")
            o["_date"] = ts.strftime("%Y-%m-%d")
        except Exception:
            o["_hour"] = 0
            o["_dow"] = "Unknown"
            o["_date"] = "Unknown"

    # Best hours
    hours_data = defaultdict(lambda: {"count": 0, "viable": 0, "edges": []})
    for o in opps:
        h = o["_hour"]
        hours_data[h]["count"] += 1
        if o.get("viable"):
            hours_data[h]["viable"] += 1
        if o.get("edge_net") is not None:
            hours_data[h]["edges"].append(o["edge_net"])

    best_hours = {}
    for h, d in sorted(hours_data.items()):
        avg_edge = sum(d["edges"]) / len(d["edges"]) if d["edges"] else 0
        best_hours[h] = {
            "count": d["count"],
            "viable": d["viable"],
            "avg_edge": round(avg_edge, 4),
        }

    # Best days
    days_data = defaultdict(lambda: {"count": 0, "viable": 0, "edges": []})
    for o in opps:
        d = o["_dow"]
        days_data[d]["count"] += 1
        if o.get("viable"):
            days_data[d]["viable"] += 1
        if o.get("edge_net") is not None:
            days_data[d]["edges"].append(o["edge_net"])

    best_days = {}
    for d, data in days_data.items():
        avg_edge = sum(data["edges"]) / len(data["edges"]) if data["edges"] else 0
        best_days[d] = {
            "count": data["count"],
            "viable": data["viable"],
            "avg_edge": round(avg_edge, 4),
        }

    # By scanner
    scanner_data = defaultdict(lambda: {"count": 0, "viable": 0, "edges": []})
    for o in opps:
        t = o.get("type", "?")
        scanner_data[t]["count"] += 1
        if o.get("viable"):
            scanner_data[t]["viable"] += 1
        if o.get("edge_net") is not None:
            scanner_data[t]["edges"].append(o["edge_net"])

    scanners = {}
    for t, d in scanner_data.items():
        avg_edge = sum(d["edges"]) / len(d["edges"]) if d["edges"] else 0
        best_edge = max(d["edges"]) if d["edges"] else 0
        scanners[t] = {
            "count": d["count"],
            "viable": d["viable"],
            "avg_edge": round(avg_edge, 4),
            "best_edge": round(best_edge, 4),
            "viable_pct": round(d["viable"] / d["count"] * 100, 1) if d["count"] > 0 else 0,
        }

    # Daily trend
    daily_data = defaultdict(lambda: {"count": 0, "viable": 0, "edges": []})
    for o in opps:
        d = o["_date"]
        daily_data[d]["count"] += 1
        if o.get("viable"):
            daily_data[d]["viable"] += 1
        if o.get("edge_net") is not None:
            daily_data[d]["edges"].append(o["edge_net"])

    daily_trend = {}
    for d, data in sorted(daily_data.items()):
        avg_edge = sum(data["edges"]) / len(data["edges"]) if data["edges"] else 0
        daily_trend[d] = {
            "count": data["count"],
            "viable": data["viable"],
            "avg_edge": round(avg_edge, 4),
        }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_hours": hours_back,
        "total_opportunities": len(opps),
        "total_viable": sum(1 for o in opps if o.get("viable")),
        "best_hours": best_hours,
        "best_days": best_days,
        "scanners": scanners,
        "daily_trend": daily_trend,
    }

    # Save
    PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PATTERNS_FILE.write_text(json.dumps(result, indent=2))
    print(f"[pattern_analyzer] Patterns saved to {PATTERNS_FILE}")

    return result


if __name__ == "__main__":
    print("=" * 70)
    print("Pattern Analyzer")
    print("=" * 70)
    result = analyze_patterns()
    if "error" not in result:
        print(f"Total: {result['total_opportunities']} opportunities, {result['total_viable']} viable")
        print("\nBest hours (UTC):")
        for h, d in sorted(result["best_hours"].items(), key=lambda x: x[1]["avg_edge"], reverse=True)[:5]:
            print(f"  {h}:00 — avg edge {d['avg_edge']:+.3f}%, {d['viable']} viable of {d['count']}")
    else:
        print(f"Error: {result['error']}")
