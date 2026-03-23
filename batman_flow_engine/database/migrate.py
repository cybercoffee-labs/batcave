#!/usr/bin/env python3
"""
Batman Lab — Migration: JSONL + JSON Reports → PostgreSQL
Fixed: handles missing trade_id, NaN in JSON, per-row error handling

Usage:
  python database/migrate.py --dry-run
  python database/migrate.py
"""

import json
import sys
import os
import re
import math
import uuid
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
OPPS_OLD_FILE = BASE_DIR / "storage" / "logs" / "opportunities_old.jsonl"
REPORTS_DIR = BASE_DIR / "storage" / "reports"
NW_TRADES_FILE = Path(BASE_DIR).parent / "nightwing_agent" / "storage" / "ledger" / "trades.jsonl"


def _clean_for_json(obj):
    """Recursively replace NaN/Infinity with None for PostgreSQL JSONB compatibility."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_for_json(v) for v in obj]
    return obj


def _safe_json_dumps(obj):
    """JSON dumps that handles NaN/Infinity."""
    cleaned = _clean_for_json(obj)
    return json.dumps(cleaned, default=str)


def migrate_opportunities(conn):
    files = [f for f in [OPPS_FILE, OPPS_OLD_FILE] if f.exists()]
    if not files:
        print("  ⚪ No opportunity files found")
        return 0

    total, dupes, errors = 0, 0, 0
    for fpath in files:
        print(f"  Reading {fpath.name}...")
        for line in fpath.read_text().strip().split("\n"):
            if not line.strip():
                continue
            try:
                opp = json.loads(line)
                opp_id = opp.get("opp_id")
                if not opp_id:
                    errors += 1
                    continue

                standard_keys = {
                    "opp_id", "ts", "type", "scanner_id", "asset", "market", "venue",
                    "buy_price", "sell_price", "spot_price", "gross_spread_pct",
                    "total_friction_pct", "edge_net", "viable", "depth_estimate", "observe_only"
                }
                metadata = {k: v for k, v in opp.items() if k not in standard_keys}

                cur = conn.cursor()
                try:
                    cur.execute("""
                        INSERT INTO opportunities
                            (opp_id, ts, scanner_type, scanner_id, asset, market, venue,
                             buy_price, sell_price, spot_price, gross_spread_pct,
                             total_friction_pct, edge_net, viable, depth_estimate,
                             observe_only, metadata)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (opp_id) DO NOTHING
                    """, (
                        opp_id, opp.get("ts", datetime.now(timezone.utc).isoformat()),
                        opp.get("type", "?"), opp.get("scanner_id", "unknown"),
                        opp.get("asset", "USDT"), opp.get("market"), opp.get("venue"),
                        opp.get("buy_price"), opp.get("sell_price"), opp.get("spot_price"),
                        opp.get("gross_spread_pct"), opp.get("total_friction_pct"),
                        opp.get("edge_net"), opp.get("viable", False),
                        opp.get("depth_estimate"), opp.get("observe_only", True),
                        _safe_json_dumps(metadata),
                    ))
                    conn.commit()
                    if cur.rowcount == 0:
                        dupes += 1
                    else:
                        total += 1
                except Exception as e:
                    conn.rollback()
                    errors += 1
                    if errors < 3:
                        print(f"    Opp error: {e}")
                finally:
                    cur.close()

            except json.JSONDecodeError:
                errors += 1

    print(f"  ✅ Opportunities: {total} inserted, {dupes} dupes, {errors} errors")
    return total


def migrate_trades(conn):
    """Migrate Nightwing trades — handles missing trade_id and different field names."""
    if not NW_TRADES_FILE.exists():
        print("  ⚪ No Nightwing trades file found")
        return 0

    total, errors = 0, 0
    print(f"  Reading trades.jsonl...")
    for line in NW_TRADES_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            trade = json.loads(line)

            # Generate trade_id if missing (Nightwing uses timestamp+cycle)
            trade_id = trade.get("trade_id")
            if not trade_id:
                cycle = trade.get("cycle", 0)
                ts = trade.get("timestamp", "")
                trade_id = f"T-NW-{cycle}-{uuid.uuid4().hex[:8].upper()}"

            # Map Nightwing fields to standard trade fields
            ts = trade.get("timestamp", trade.get("ts", datetime.now(timezone.utc).isoformat()))
            agent = "nightwing"
            opp_id = trade.get("opp_id")
            asset = "USDT"
            market = trade.get("fiat", "MXN")
            side = "BUY"  # Nightwing P2P trades are buy USDT
            price = trade.get("p2p_buy_price", trade.get("price", 0)) or 0
            quantity = trade.get("amount_usd", trade.get("quantity", 0)) or 0
            fee = 0
            pnl = None
            edge = trade.get("edge_net")
            if edge and quantity:
                pnl = round(float(edge) / 100 * float(quantity), 4)
            status = trade.get("mode", "PAPER").lower()

            # Everything else goes to metadata
            standard_keys = {
                "trade_id", "timestamp", "ts", "opp_id", "fiat", "amount_usd",
                "p2p_buy_price", "price", "quantity", "edge_net", "mode"
            }
            metadata = {k: v for k, v in trade.items() if k not in standard_keys}

            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO trades
                        (trade_id, agent, ts, opp_id, asset, market,
                         side, price, quantity, fee, pnl, status, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (trade_id) DO NOTHING
                """, (
                    trade_id, agent, ts, opp_id, asset, market,
                    side, price, quantity, fee, pnl, status,
                    _safe_json_dumps(metadata),
                ))
                conn.commit()
                total += 1
            except Exception as e:
                conn.rollback()
                errors += 1
                if errors < 3:
                    print(f"    Trade error: {e}")
            finally:
                cur.close()

        except json.JSONDecodeError:
            errors += 1

    print(f"  ✅ Trades: {total} inserted, {errors} errors")
    return total


def migrate_engine_reports(conn):
    if not REPORTS_DIR.exists():
        print("  ⚪ No reports directory found")
        return 0

    report_files = sorted(REPORTS_DIR.glob("*.json"))
    if not report_files:
        print("  ⚪ No report files found")
        return 0

    total, errors = 0, 0
    print(f"  Reading {len(report_files)} report files...")
    for fpath in report_files:
        try:
            raw = fpath.read_text()
            result = json.loads(raw)
            meta = result.get("meta", {})
            stress = result.get("stress", {})
            regime = stress.get("regime", {}) if isinstance(stress, dict) else {}

            # Clean NaN/Infinity from the full report before JSONB insertion
            clean_report = _safe_json_dumps(result)

            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO engine_runs
                        (ts, duration_sec, equities_total, equities_ok,
                         crypto_total, crypto_ok, regime, corr_stress, errors, full_report)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    result.get("timestamp", fpath.stem.replace("_", "T", 1)),
                    meta.get("duration_sec"), meta.get("equities_total"), meta.get("equities_ok"),
                    meta.get("crypto_total"), meta.get("crypto_ok"),
                    regime.get("label") if isinstance(regime, dict) else None,
                    stress.get("corr_stress") if isinstance(stress, dict) and not (isinstance(stress.get("corr_stress"), float) and math.isnan(stress.get("corr_stress"))) else None,
                    meta.get("errors", 0),
                    clean_report,
                ))
                conn.commit()
                total += 1
            except Exception as e:
                conn.rollback()
                errors += 1
                if errors < 3:
                    print(f"    Report error ({fpath.name}): {e}")
            finally:
                cur.close()

        except json.JSONDecodeError:
            errors += 1

    print(f"  ✅ Engine reports: {total} inserted, {errors} errors")
    return total


def run_migration(dry_run=False):
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║       🦇 BATMAN LAB — PostgreSQL Migration v2                    ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    if dry_run:
        print("  ⚠️  DRY RUN — counting records only\n")
        for fpath in [OPPS_FILE, OPPS_OLD_FILE]:
            if fpath.exists():
                lines = [l for l in fpath.read_text().strip().split("\n") if l.strip()]
                print(f"  📄 {fpath.name}: {len(lines)} records")
        if NW_TRADES_FILE.exists():
            lines = [l for l in NW_TRADES_FILE.read_text().strip().split("\n") if l.strip()]
            print(f"  📄 trades.jsonl: {len(lines)} records")
        if REPORTS_DIR.exists():
            print(f"  📄 reports/: {len(list(REPORTS_DIR.glob('*.json')))} files")
        print(f"\n  Run without --dry-run to execute.")
        return

    import psycopg2
    db_config = {
        "host": os.environ.get("BATMAN_DB_HOST", "localhost"),
        "port": int(os.environ.get("BATMAN_DB_PORT", 5432)),
        "dbname": os.environ.get("BATMAN_DB_NAME", "batman_lab"),
        "user": os.environ.get("BATMAN_DB_USER", os.environ.get("USER", "batman")),
        "password": os.environ.get("BATMAN_DB_PASSWORD", ""),
    }

    print(f"  Connecting to {db_config['dbname']}@{db_config['host']}...")
    conn = psycopg2.connect(**db_config)
    conn.autocommit = False

    try:
        print("\n📦 Step 1/3: Opportunities...")
        opps = migrate_opportunities(conn)
        print("\n📦 Step 2/3: Trades...")
        trades = migrate_trades(conn)
        print("\n📦 Step 3/3: Engine reports...")
        reports = migrate_engine_reports(conn)

        # Final verify
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM opportunities")
        opps_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades")
        trades_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM engine_runs")
        reports_count = cur.fetchone()[0]
        cur.close()

        print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  ✅ MIGRATION COMPLETE                                          ║
║  Opportunities: {opps_count:>6} rows                                     ║
║  Trades:        {trades_count:>6} rows                                     ║
║  Engine Runs:   {reports_count:>6} rows                                     ║
╚══════════════════════════════════════════════════════════════════╝
        """)

    except Exception as e:
        print(f"\n  ❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration(dry_run="--dry-run" in sys.argv)
