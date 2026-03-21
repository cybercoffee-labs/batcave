#!/usr/bin/env python3
"""
MANUAL TRADE RECORDER — Register real P2P trades executed manually.

Use this after you execute a trade on Binance P2P + SPEI.
Records the real trade in HARVEY ledger for P&L tracking.

Run: python tools/record_manual_trade.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LEDGER_FILE = BASE_DIR / "storage" / "ledger" / "trades.jsonl"


def record():
    print("\n🦇 NIGHTWING — MANUAL TRADE RECORDER")
    print("=" * 50)
    print("Record a real P2P trade you just executed.\n")

    # Collect trade info
    fiat = input("Fiat pair [MXN]: ").strip().upper() or "MXN"

    try:
        amount_usd = float(input("Amount in USD [50]: ").strip() or "50")
    except ValueError:
        amount_usd = 50.0

    try:
        buy_price = float(input(f"P2P buy price ({fiat} per USDT): ").strip())
    except ValueError:
        print("Invalid price. Aborting.")
        return

    try:
        sell_price_input = input(f"P2P sell price ({fiat} per USDT) [same as buy]: ").strip()
        sell_price = float(sell_price_input) if sell_price_input else buy_price
    except ValueError:
        sell_price = buy_price

    try:
        spot_input = input(f"Spot rate ({fiat}/USD) [auto from Batman]: ").strip()
        if spot_input:
            spot_price = float(spot_input)
        else:
            sys.path.insert(0, str(BASE_DIR))
            from core.batman_bridge import fetch_from_batman

            batman = fetch_from_batman(fiat)
            spot_price = batman.get("spot_price", 0)
            print(f"   Auto-fetched spot: {spot_price}")
    except (ValueError, Exception):
        spot_price = 0

    # Calculate edge
    if spot_price > 0:
        premium = (buy_price - spot_price) / spot_price
        friction = 0.25  # Default friction %
        edge_net = round(premium * 100 - friction, 4)
    else:
        premium = 0
        edge_net = 0

    opp_id = input("Batman opp_id (from Nightwing output, or press Enter): ").strip() or None
    notes = input("Notes (optional): ").strip() or None

    # Build record
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle": 0,
        "mode": "MANUAL",
        "fiat": fiat,
        "amount_usd": amount_usd,
        "decision": "OPPORTUNITY",
        "action": "MANUAL_TRADE",
        "status": "executed",
        "edge_net": edge_net,
        "viable": True,
        "total_friction_pct": 0.25,
        "spot_price": spot_price,
        "p2p_buy_price": buy_price,
        "p2p_sell_price": sell_price,
        "depth_estimate": None,
        "opp_id": opp_id,
        "duration_ms": 0,
        "manual": True,
        "notes": notes,
    }

    # Calculate P&L
    pnl_usd = amount_usd * (edge_net / 100)
    pnl_mxn = pnl_usd * spot_price if spot_price else 0

    # Show summary
    print(f"\n{'=' * 50}")
    print("  Trade summary:")
    print(f"  Pair:       USDT/{fiat}")
    print(f"  Amount:     ${amount_usd:.2f} USD")
    print(f"  Buy price:  {buy_price} {fiat}")
    print(f"  Spot price: {spot_price} {fiat}")
    print(f"  Premium:    {premium*100:+.3f}%")
    print(f"  Edge net:   {edge_net:+.4f}%")
    print(f"  Est. P&L:   ${pnl_usd:+.2f} USD (${pnl_mxn:+.2f} MXN)")
    print(f"{'=' * 50}")

    confirm = input("\nSave to ledger? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    # Write to ledger
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"\n✅ Trade recorded in {LEDGER_FILE}")
    print(f"   P&L: ${pnl_usd:+.2f} USD")


if __name__ == "__main__":
    record()
