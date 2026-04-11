#!/usr/bin/env python3
"""
🦇 BATMAN LAB — COMMAND CENTER

The master view of your entire financial operation.
Shows: HODL positions, scanner performance, P&L, portfolio, alerts.

Usage:
  python tools/command_center.py              # Full overview
  python tools/command_center.py --hodl       # HODL positions only
  python tools/command_center.py --scanners   # Scanner performance
  python tools/command_center.py --pnl        # P&L summary
  python tools/command_center.py --alerts     # Active alerts
  python tools/command_center.py --portfolio  # Portfolio allocation
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def _db_query(query, params=None):
    """Execute a PostgreSQL query and return results as list of dicts."""
    try:
        from database.postgres import get_cursor

        with get_cursor() as cur:
            cur.execute(query, params or [])
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
            return []
    except Exception as e:
        print(f"  ❌ DB error: {e}")
        return []


def show_header():
    now = datetime.now()
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          🦇 BATMAN LAB — COMMAND CENTER                          ║
║          {now.strftime('%A %B %d, %Y — %H:%M')}                          ║
║          PostgreSQL: batman_lab | 15 Scanners | 10 Streams       ║
╚══════════════════════════════════════════════════════════════════╝
    """)


def show_system_health():
    """Show Batman engine and database health."""
    print(f"{'═'*66}")
    print("  🏥 SYSTEM HEALTH")
    print(f"{'═'*66}")

    # Database stats
    rows = _db_query("""
        SELECT
            (SELECT COUNT(*) FROM opportunities) as opps,
            (SELECT COUNT(*) FROM trades) as trades,
            (SELECT COUNT(*) FROM engine_runs) as runs,
            (SELECT COUNT(*) FROM alerts WHERE acknowledged = FALSE) as unread_alerts
    """)
    if rows:
        r = rows[0]
        print(f"  📊 Database: {r['opps']} opportunities | {r['trades']} trades | {r['runs']} engine runs")
        if r["unread_alerts"] > 0:
            print(f"  🔔 {r['unread_alerts']} unread alerts!")

    # Latest engine run
    runs = _db_query("SELECT ts, regime, duration_sec, errors FROM engine_runs ORDER BY ts DESC LIMIT 1")
    if runs:
        r = runs[0]
        age_str = str(datetime.now(timezone.utc) - r["ts"]).split(".")[0] if r.get("ts") else "?"
        regime_icon = {"NORMAL": "🟢", "TENSION": "🟡", "STRESS": "🟠", "PANIC": "🔴"}.get(r.get("regime", ""), "⚪")
        print(
            f"  {regime_icon} Regime: {r.get('regime', 'UNKNOWN')} | Last run: {age_str} ago | Duration: {r.get('duration_sec', '?')}s"
        )
    print()


def show_scanner_performance():
    """Show scanner performance from PostgreSQL."""
    print(f"{'═'*66}")
    print("  🔍 SCANNER PERFORMANCE (all time)")
    print(f"{'═'*66}")

    rows = _db_query("""
        SELECT scanner_type,
            COUNT(*) as total,
            SUM(CASE WHEN viable THEN 1 ELSE 0 END) as viable,
            ROUND(AVG(edge_net)::numeric, 3) as avg_edge,
            ROUND(MAX(edge_net)::numeric, 3) as best_edge
        FROM opportunities
        GROUP BY scanner_type
        ORDER BY viable DESC
    """)

    scanner_names = {
        "A": "Cross-Exchange",
        "B": "Basis",
        "C": "P2P LATAM",
        "D": "Multi-Exchange",
        "E": "Funding Rate",
        "F": "Cross-Currency",
        "G": "Merchant Spread",
        "H": "Stablecoin",
        "I": "Cross-Platform MXN",
        "J": "DEX vs CEX",
        "K": "Futures vs Futures",
    }

    for r in rows:
        st = r["scanner_type"].strip()
        name = scanner_names.get(st, f"Scanner {st}")
        total = r["total"]
        viable = r["viable"] or 0
        rate = (viable / total * 100) if total > 0 else 0
        icon = "✅" if viable > 0 else "⚪"
        print(
            f"  {icon} [{st}] {name:<22s} | {total:>5} total | {viable:>5} viable ({rate:.0f}%) | best: {r['best_edge'] or 0:+.3f}%"
        )

    print()


def show_pnl():
    """Show P&L from trades."""
    print(f"{'═'*66}")
    print("  💰 P&L SUMMARY")
    print(f"{'═'*66}")

    # Overall
    rows = _db_query("""
        SELECT COUNT(*) as total_trades,
            ROUND(SUM(pnl)::numeric, 2) as total_pnl,
            ROUND(AVG(pnl)::numeric, 4) as avg_pnl,
            ROUND(MAX(pnl)::numeric, 4) as best_trade,
            ROUND(MIN(pnl)::numeric, 4) as worst_trade
        FROM trades WHERE pnl IS NOT NULL
    """)

    if rows and rows[0]["total_trades"] > 0:
        r = rows[0]
        pnl_sign = "+" if (r["total_pnl"] or 0) >= 0 else ""
        print(f"  📈 Total trades: {r['total_trades']} | P&L: {pnl_sign}${r['total_pnl']} USD")
        print(f"     Avg per trade: ${r['avg_pnl']} | Best: ${r['best_trade']} | Worst: ${r['worst_trade']}")
    else:
        print("  No trades with P&L recorded yet.")

    # By agent
    agent_rows = _db_query("""
        SELECT agent, COUNT(*) as trades,
            ROUND(SUM(pnl)::numeric, 2) as total_pnl
        FROM trades WHERE pnl IS NOT NULL
        GROUP BY agent ORDER BY total_pnl DESC
    """)

    if agent_rows:
        print("\n  Per agent:")
        for r in agent_rows:
            pnl_sign = "+" if (r["total_pnl"] or 0) >= 0 else ""
            print(f"    {r['agent']:<15s} | {r['trades']:>4} trades | {pnl_sign}${r['total_pnl']} USD")

    # Last 7 days daily
    daily = _db_query("""
        SELECT DATE(ts) as day, COUNT(*) as trades,
            ROUND(SUM(pnl)::numeric, 2) as pnl
        FROM trades WHERE pnl IS NOT NULL AND ts > NOW() - INTERVAL '7 days'
        GROUP BY DATE(ts) ORDER BY day DESC
    """)

    if daily:
        print("\n  Last 7 days:")
        for r in daily:
            pnl_sign = "+" if (r["pnl"] or 0) >= 0 else ""
            print(f"    {r['day']} | {r['trades']:>3} trades | {pnl_sign}${r['pnl']} USD")

    print()


def show_hodl():
    """Show HODL positions from ORACLE module."""
    print(f"{'═'*66}")
    print("  🔮 HODL POSITIONS (Oracle)")
    print(f"{'═'*66}")

    try:
        from core.oracle import check_all_positions

        results = check_all_positions()

        if not results:
            print("  No HODL positions. Add with:")
            print("  python core/oracle.py --add XRP 100 0.55 1.00 1.50 2.50 0.40")
            print("  python core/oracle.py --add ENA 500 0.80 1.50 3.00 5.00 0.50")
            print()
            return

        total_value = 0
        total_pnl = 0

        for r in results:
            token = r["token"]
            price = r["current_price"]
            pnl_pct = r["pnl_pct"]
            pnl_usd = r["pnl_usd"]
            signal = r["signal"]
            value = price * r["quantity"]

            total_value += value
            total_pnl += pnl_usd

            if signal in ("STOP_LOSS_HIT", "TRAILING_STOP"):
                icon = "🔴"
            elif signal in ("TP1_HIT", "TP2_HIT", "TP3_HIT"):
                icon = "🟢"
            else:
                icon = "⚪"

            pnl_s = f"+{pnl_pct:.1f}" if pnl_pct >= 0 else f"{pnl_pct:.1f}"
            print(
                f"  {icon} {token:6s} ${price:<10.4f} | {pnl_s:>7s}% | ${pnl_usd:>8.2f} | {r['multiplier']:.2f}x | {signal}"
            )

            if r.get("action"):
                print(f"     ⚡ {r['action']}")

        pnl_s = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"
        print(f"\n  💰 Total: ${total_value:.2f} | P&L: {pnl_s}")

    except Exception as e:
        print(f"  ❌ Oracle error: {e}")

    print()


def show_alerts():
    """Show unacknowledged alerts."""
    print(f"{'═'*66}")
    print("  🔔 ACTIVE ALERTS")
    print(f"{'═'*66}")

    rows = _db_query("""
        SELECT ts, source, severity, title, message
        FROM alerts WHERE acknowledged = FALSE
        ORDER BY ts DESC LIMIT 20
    """)

    if not rows:
        print("  ✅ No active alerts")
    else:
        for r in rows:
            sev_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(r["severity"], "⚪")
            ts_str = r["ts"].strftime("%m/%d %H:%M") if r.get("ts") else "?"
            print(f"  {sev_icon} [{ts_str}] [{r['source']}] {r['title']}")
            if r.get("message"):
                print(f"     {r['message'][:80]}")

    print()


def show_portfolio():
    """Show portfolio allocation (Omar Financiero style)."""
    print(f"{'═'*66}")
    print("  📊 PORTFOLIO ALLOCATION")
    print(f"{'═'*66}")

    rows = _db_query("SELECT * FROM v_portfolio_overview")

    if not rows:
        print("  No portfolio data yet. Add with:")
        print("  python tools/command_center.py --add-balance")
        print()
        return

    total = sum(float(r.get("total_balance", 0) or 0) for r in rows)
    if total <= 0:
        print("  No balances recorded.")
        print()
        return

    for r in rows:
        cat = r["category"]
        balance = float(r.get("total_balance", 0) or 0)
        pct = balance / total * 100
        rate = r.get("avg_rate")
        rate_str = f"{float(rate):.1f}% APY" if rate else ""

        bar_len = int(pct / 2)
        bar = "█" * bar_len

        print(f"  {cat:<15s} ${balance:>10,.2f} ({pct:>5.1f}%) {bar} {rate_str}")

    print(f"  {'─'*50}")
    print(f"  {'TOTAL':<15s} ${total:>10,.2f}")
    print()


def show_top_opportunities():
    """Show current best opportunities."""
    print(f"{'═'*66}")
    print("  ⭐ TOP OPPORTUNITIES (last 24h)")
    print(f"{'═'*66}")

    rows = _db_query("""
        SELECT opp_id, scanner_type, asset, market, edge_net, venue, metadata
        FROM opportunities
        WHERE viable = TRUE AND ts > NOW() - INTERVAL '24 hours'
        ORDER BY edge_net DESC LIMIT 5
    """)

    if not rows:
        print("  No viable opportunities in last 24h")
    else:
        for r in rows:
            asset = r["asset"] or "USDT"
            market = r["market"]
            if not market:
                # Derive from metadata for scanners that embed pair info (e.g. type F)
                meta = r.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        import json as _json

                        meta = _json.loads(meta)
                    except Exception:
                        meta = {}
                bf = meta.get("buy_fiat", "")
                sf = meta.get("sell_fiat", "")
                market = f"{bf}/{sf}" if bf and sf else "?"
            print(
                f"  [{r['scanner_type'].strip()}] {asset}/{market} | Edge: {float(r['edge_net'] or 0):+.3f}% | {r['venue'] or ''}"
            )

    print()


def full_overview():
    """Show everything."""
    show_header()
    show_system_health()
    show_top_opportunities()
    show_scanner_performance()
    show_pnl()
    show_hodl()
    show_alerts()


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--hodl" in args:
        show_header()
        show_hodl()
    elif "--scanners" in args:
        show_header()
        show_scanner_performance()
    elif "--pnl" in args:
        show_header()
        show_pnl()
    elif "--alerts" in args:
        show_header()
        show_alerts()
    elif "--portfolio" in args:
        show_header()
        show_portfolio()
    else:
        full_overview()
