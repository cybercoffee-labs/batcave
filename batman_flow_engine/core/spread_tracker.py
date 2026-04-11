"""
Spread Lifetime Tracker

Tracks how long arbitrage opportunities last:
- When did it first appear?
- When did it peak?
- When did it close?
- Average lifetime per scanner type

Reads from opportunities.jsonl and builds a SQLite database of spread lifetimes.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

BASE_DIR = Path(__file__).resolve().parent.parent
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
DB_FILE = BASE_DIR / "storage" / "spread_lifetimes.db"


def init_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spread_lifetimes (
            opp_id TEXT PRIMARY KEY,
            scanner_type TEXT,
            asset TEXT,
            fiat TEXT,
            first_seen TEXT,
            last_seen TEXT,
            peak_time TEXT,
            peak_edge REAL,
            duration_min REAL,
            avg_edge REAL,
            observations INTEGER DEFAULT 1,
            closed INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scanner_type ON spread_lifetimes(scanner_type)
    """)
    conn.commit()
    return conn


def build_lifetimes():
    """Process opportunities.jsonl and build lifetime database."""
    if not OPPS_FILE.exists():
        print("No opportunities file found.")
        return

    conn = init_db()

    # Group opportunities by a composite key (type + asset + venue)
    groups: Dict[str, List[dict]] = {}

    for line in OPPS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            # Create grouping key
            key = f"{r.get('type', '?')}|{r.get('asset', r.get('fiat', '?'))}|{r.get('venue', r.get('buy_platform', r.get('fiat', '?')))}"
            groups.setdefault(key, []).append(r)
        except Exception:
            continue

    print(f"[spread_tracker] Processing {len(groups)} unique opportunity streams...")

    for key, opps in groups.items():
        opps.sort(key=lambda x: x.get("ts", ""))

        # Find sessions (gaps > 60 min = new session)
        sessions = []
        current_session = [opps[0]]

        for i in range(1, len(opps)):
            try:
                prev_ts = datetime.fromisoformat(opps[i - 1]["ts"].replace("Z", "+00:00"))
                curr_ts = datetime.fromisoformat(opps[i]["ts"].replace("Z", "+00:00"))
                gap_min = (curr_ts - prev_ts).total_seconds() / 60

                if gap_min > 60:
                    sessions.append(current_session)
                    current_session = [opps[i]]
                else:
                    current_session.append(opps[i])
            except Exception:
                current_session.append(opps[i])

        sessions.append(current_session)

        for session in sessions:
            if not session:
                continue

            first = session[0]
            last = session[-1]
            edges = [o.get("edge_net", 0) for o in session if o.get("edge_net") is not None]

            if not edges:
                continue

            peak_edge = max(edges)
            peak_idx = edges.index(peak_edge)
            peak_opp = session[min(peak_idx, len(session) - 1)]

            try:
                first_ts = datetime.fromisoformat(first["ts"].replace("Z", "+00:00"))
                last_ts = datetime.fromisoformat(last["ts"].replace("Z", "+00:00"))
                duration = (last_ts - first_ts).total_seconds() / 60
            except Exception:
                duration = 0

            opp_id = first.get("opp_id", key)

            conn.execute(
                """
                INSERT OR REPLACE INTO spread_lifetimes
                (opp_id, scanner_type, asset, fiat, first_seen, last_seen,
                 peak_time, peak_edge, duration_min, avg_edge, observations, closed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    opp_id,
                    first.get("type", "?"),
                    first.get("asset", "?"),
                    first.get("fiat", first.get("market", "?")),
                    first.get("ts", ""),
                    last.get("ts", ""),
                    peak_opp.get("ts", ""),
                    peak_edge,
                    round(duration, 1),
                    round(sum(edges) / len(edges), 4),
                    len(session),
                    1 if duration > 0 else 0,
                ),
            )

    conn.commit()

    # Print summary
    cursor = conn.execute("""
        SELECT scanner_type,
               COUNT(*) as sessions,
               AVG(duration_min) as avg_duration,
               AVG(peak_edge) as avg_peak,
               MAX(peak_edge) as best_peak
        FROM spread_lifetimes
        GROUP BY scanner_type
    """)

    print(f"\n{'Scanner':<8} {'Sessions':<10} {'Avg Duration':<15} {'Avg Peak Edge':<15} {'Best Peak'}")
    print("-" * 65)
    for row in cursor:
        print(f"{row[0]:<8} {row[1]:<10} {row[2]:.1f} min{'':<8} {row[3]:+.3f}%{'':<8} {row[4]:+.3f}%")

    conn.close()
    print(f"\n[spread_tracker] Database saved to {DB_FILE}")


def get_lifetime_stats() -> Dict[str, Any]:
    """Get lifetime statistics for the dashboard."""
    if not DB_FILE.exists():
        return {}

    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.execute("""
        SELECT scanner_type,
               COUNT(*) as sessions,
               AVG(duration_min) as avg_duration,
               AVG(peak_edge) as avg_peak,
               MAX(peak_edge) as best_peak,
               AVG(observations) as avg_obs
        FROM spread_lifetimes
        GROUP BY scanner_type
    """)

    stats = {}
    for row in cursor:
        stats[row[0]] = {
            "sessions": row[1],
            "avg_duration_min": round(row[2], 1),
            "avg_peak_edge": round(row[3], 4),
            "best_peak_edge": round(row[4], 4),
            "avg_observations": round(row[5], 1),
        }

    conn.close()
    return stats


if __name__ == "__main__":
    print("=" * 70)
    print("Spread Lifetime Tracker")
    print("=" * 70)
    build_lifetimes()
