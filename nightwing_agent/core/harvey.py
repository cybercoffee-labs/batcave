"""
HARVEY DENT (LEDGER) — Trade Execution Ledger for Nightwing

Batman's HARVEY stores SIGNALS (opportunities detected) in SQLite.
Nightwing's HARVEY stores EXECUTIONS (what the agent did with each opportunity).
They are different by design.

Storage: storage/ledger/trades.jsonl (append-only JSONL)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("nightwing.harvey")

BASE_DIR = Path(__file__).resolve().parent.parent
LEDGER_FILE = BASE_DIR / "storage" / "ledger" / "trades.jsonl"


def record_trade(result: Dict[str, Any]) -> None:
    """Append one trade record to the ledger from agent cycle result."""
    batman = result.get("batman", {})
    if isinstance(batman, dict) and batman.get("status") in ("ok", "stale"):
        batman_data = batman if batman.get("status") == "ok" else batman.get("data", {})
    else:
        batman_data = {}

    record = {
        "timestamp": result.get("ts"),
        "cycle": result.get("cycle"),
        "mode": result.get("mode"),
        "fiat": result.get("fiat"),
        "amount_usd": result.get("amount_usd"),
        "decision": result.get("decision"),
        "action": result.get("action"),
        "status": result.get("status"),
        "edge_net": result.get("edge_net"),
        "viable": batman_data.get("viable"),
        "total_friction_pct": batman_data.get("total_friction_pct"),
        "spot_price": batman_data.get("spot_price"),
        "p2p_buy_price": batman_data.get("p2p_buy_price"),
        "p2p_sell_price": batman_data.get("p2p_sell_price"),
        "depth_estimate": batman_data.get("depth_estimate"),
        "opp_id": batman_data.get("opp_id"),
        "duration_ms": result.get("duration_ms"),
    }

    try:
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"Failed to write trade record: {e}")


def _read_ledger(path: Optional[Path] = None) -> list:
    """Read all valid records from the ledger JSONL."""
    ledger = path or LEDGER_FILE
    if not ledger.exists():
        return []

    records = []
    for line in ledger.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Skipping corrupt JSONL line in ledger")
            continue
    return records


def get_daily_summary(path: Optional[Path] = None) -> Dict[str, Any]:
    """Get summary of today's trades."""
    records = _read_ledger(path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_records = [r for r in records if (r.get("timestamp") or "")[:10] == today]
    return _summarize(today_records)


def get_session_summary(since_ts: str, path: Optional[Path] = None) -> Dict[str, Any]:
    """Get summary of trades since a given timestamp."""
    records = _read_ledger(path)
    filtered = [r for r in records if (r.get("timestamp") or "") >= since_ts]
    return _summarize(filtered)


def _summarize(records: list) -> Dict[str, Any]:
    """Build summary dict from a list of trade records."""
    if not records:
        return {
            "total_cycles": 0,
            "opportunities": 0,
            "passes": 0,
            "blocked": 0,
            "avg_edge_net": 0.0,
            "best_edge": 0.0,
            "worst_edge": 0.0,
            "viable_count": 0,
            "viable_pct": 0.0,
        }

    edges = [r.get("edge_net") for r in records if r.get("edge_net") is not None]
    viable_records = [r for r in records if r.get("viable") is True]

    return {
        "total_cycles": len(records),
        "opportunities": sum(1 for r in records if r.get("decision") == "OPPORTUNITY"),
        "passes": sum(1 for r in records if r.get("decision") == "PASS"),
        "blocked": sum(1 for r in records if "BLOCKED" in (r.get("decision") or "")),
        "avg_edge_net": round(sum(edges) / len(edges), 4) if edges else 0.0,
        "best_edge": round(max(edges), 4) if edges else 0.0,
        "worst_edge": round(min(edges), 4) if edges else 0.0,
        "viable_count": len(viable_records),
        "viable_pct": round(len(viable_records) / len(records) * 100, 2) if records else 0.0,
    }


def print_summary(path: Optional[Path] = None) -> None:
    """Print formatted daily summary to stdout."""
    s = get_daily_summary(path)
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   HARVEY — DAILY LEDGER                      ║
╠══════════════════════════════════════════════════════════════╣
║  Total cycles:    {s['total_cycles']:<10}                             ║
║  Opportunities:   {s['opportunities']:<10}                             ║
║  Passes:          {s['passes']:<10}                             ║
║  Blocked:         {s['blocked']:<10}                             ║
║  Avg edge_net:    {s['avg_edge_net']:+.4f}%                            ║
║  Best edge:       {s['best_edge']:+.4f}%                            ║
║  Worst edge:      {s['worst_edge']:+.4f}%                            ║
║  Viable count:    {s['viable_count']:<10}                             ║
║  Viable %:        {s['viable_pct']:.2f}%                              ║
╚══════════════════════════════════════════════════════════════╝
""")
