#!/usr/bin/env python3
"""
Daily Summary Script

Reads storage/logs/opportunities.jsonl for today and prints a table showing:
- Count of opportunities per scanner type (A, B, C)
- Average spread per scanner type
- Max spread per scanner type
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"


def main():
    if not LOG_FILE.exists():
        print(f"Log file not found: {LOG_FILE}")
        return

    # Get today's date in UTC
    today = datetime.now(timezone.utc).date()

    # Parse opportunities for today
    opportunities_by_type = defaultdict(list)
    edge_nets_by_type = defaultdict(list)

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                opp = json.loads(line)
                ts_str = opp.get("ts")
                if not ts_str:
                    continue

                # Parse timestamp
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.date() != today:
                    continue

                opp_type = opp.get("type")
                if opp_type not in ["A", "B", "C"]:
                    continue

                # Extract spread - different field names for different scanners
                spread = None
                if opp_type == "A":
                    spread = opp.get("spread_pct")
                elif opp_type == "B":
                    spread = opp.get("basis_pct")
                elif opp_type == "C":
                    # For P2P, use merchant_spread
                    spread = opp.get("merchant_spread")
                    if spread is not None:
                        spread = spread * 100  # Convert to percentage
                    # Also extract edge_net for P2P
                    edge_net = opp.get("edge_net")
                    if edge_net is not None:
                        edge_nets_by_type[opp_type].append(edge_net)

                if spread is not None:
                    opportunities_by_type[opp_type].append(spread)

            except (json.JSONDecodeError, ValueError):
                continue

    # Print summary table
    print("=" * 85)
    print(f"DAILY SUMMARY — {today.isoformat()}")
    print("=" * 85)
    print(f"{'SCANNER':<10} {'COUNT':>8} {'AVG_SPREAD%':>15} {'MAX_SPREAD%':>15} {'AVG_EDGE_NET%':>15}")
    print("-" * 85)

    for scanner_type in ["A", "B", "C"]:
        spreads = opportunities_by_type.get(scanner_type, [])
        edge_nets = edge_nets_by_type.get(scanner_type, [])
        count = len(spreads)

        if count == 0:
            avg_spread = 0.0
            max_spread = 0.0
        else:
            avg_spread = sum(spreads) / count
            max_spread = max(spreads)

        # Calculate average edge_net (only for scanner C)
        if edge_nets:
            avg_edge_net = sum(edge_nets) / len(edge_nets)
            edge_net_str = f"{avg_edge_net:>14.4f}%"
        else:
            edge_net_str = f"{'N/A':>15}"

        scanner_name = {"A": "Cross-Exch", "B": "Basis", "C": "P2P LATAM"}.get(scanner_type, scanner_type)

        print(f"{scanner_name:<10} {count:>8} {avg_spread:>14.4f}% {max_spread:>14.4f}% {edge_net_str}")

    print("=" * 85)


if __name__ == "__main__":
    main()
