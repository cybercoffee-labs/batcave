#!/usr/bin/env python3
"""
Batman Lab — Portfolio Setup Tool

Load your initial positions into PostgreSQL.
Run once to set up, then use command_center.py to monitor.

Usage:
  python tools/setup_portfolio.py
"""

import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.postgres import save_hodl_position, save_venture_position, save_portfolio_snapshot


def setup_hodl_positions():
    """Add your HODL crypto positions. EDIT THESE WITH YOUR REAL DATA."""
    print("\n📦 Setting up HODL positions...")

    positions = [
        # ──── EDIT THESE WITH YOUR REAL HOLDINGS ────
        # {"token": "XRP",  "exchange": "binance", "quantity": 100, "avg_buy_price": 0.55,
        #  "take_profit_1": 1.00, "take_profit_2": 1.50, "take_profit_3": 2.50,
        #  "stop_loss": 0.40, "trailing_stop_pct": 15.0},

        # {"token": "ENA",  "exchange": "binance", "quantity": 500, "avg_buy_price": 0.80,
        #  "take_profit_1": 1.50, "take_profit_2": 3.00, "take_profit_3": 5.00,
        #  "stop_loss": 0.50, "trailing_stop_pct": 20.0},

        # ──── UNCOMMENT AND EDIT THE ABOVE, OR ADD YOUR OWN ────
    ]

    if not positions:
        print("  ⚠️  No positions configured. Edit tools/setup_portfolio.py first.")
        print("  Uncomment the example positions and fill in your real data.")
        print("\n  Or add positions via CLI:")
        print("  python core/oracle.py --add XRP 100 0.55 1.00 1.50 2.50 0.40")
        return 0

    count = 0
    for pos in positions:
        if save_hodl_position(pos):
            print(f"  ✅ {pos['token']}: {pos['quantity']} @ ${pos['avg_buy_price']}")
            count += 1
        else:
            print(f"  ❌ Failed: {pos['token']}")

    return count


def setup_venture_positions():
    """Add your Web3 early project positions. EDIT THESE."""
    print("\n📦 Setting up Venture positions...")

    positions = [
        # ──── EDIT THESE WITH YOUR REAL WEB3 HOLDINGS ────
        # {"token": "XPIN",   "chain": "ethereum", "quantity": 10000, "avg_buy_price": 0.001},
        # {"token": "NAORIS", "chain": "ethereum", "quantity": 5000,  "avg_buy_price": 0.05},
        # {"token": "ARIA",   "chain": "solana",   "quantity": 1000,  "avg_buy_price": 0.10},
        # {"token": "ASTER",  "chain": "ethereum", "quantity": 2000,  "avg_buy_price": 0.02},
    ]

    if not positions:
        print("  ⚠️  No venture positions configured. Edit this file first.")
        return 0

    count = 0
    for pos in positions:
        if save_venture_position(pos):
            print(f"  ✅ {pos['token']} ({pos['chain']}): {pos['quantity']}")
            count += 1

    return count


def setup_portfolio_balances():
    """Add your passive investment balances. EDIT THESE."""
    print("\n📦 Setting up Portfolio balances...")

    balances = [
        # ──── EDIT THESE WITH YOUR REAL BALANCES ────
        # {"platform": "cetes",   "instrument": "CETES 28d",     "balance": 5000,  "currency": "MXN", "interest_rate": 10.5, "category": "renta_fija"},
        # {"platform": "nu",      "instrument": "Nu Cuenta",     "balance": 3000,  "currency": "MXN", "interest_rate": 15.0, "category": "renta_fija"},
        # {"platform": "finsus",  "instrument": "Finsus Cuenta", "balance": 2000,  "currency": "MXN", "interest_rate": 15.0, "category": "renta_fija"},
        # {"platform": "gbm",     "instrument": "VOO ETF",       "balance": 1000,  "currency": "USD", "interest_rate": None, "category": "bolsa"},
        # {"platform": "gbm",     "instrument": "FUNO11",        "balance": 500,   "currency": "MXN", "interest_rate": None, "category": "fibra"},
        # {"platform": "binance", "instrument": "USDT (P2P)",    "balance": 28,    "currency": "USD", "interest_rate": None, "category": "crypto"},
        # {"platform": "bbva",    "instrument": "Cuenta Debito", "balance": 5000,  "currency": "MXN", "interest_rate": 0,    "category": "efectivo"},
    ]

    if not balances:
        print("  ⚠️  No balances configured. Edit this file first.")
        return 0

    count = save_portfolio_snapshot(balances)
    print(f"  ✅ Saved {count} balance records")
    return count


def main():
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║       🦇 BATMAN LAB — Portfolio Setup                            ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    hodl = setup_hodl_positions()
    venture = setup_venture_positions()
    portfolio = setup_portfolio_balances()

    print(f"""
{'═'*66}
  Summary: {hodl} HODL + {venture} Venture + {portfolio} Portfolio records
  
  Next steps:
  1. Edit this file with your REAL positions
  2. Run: python tools/command_center.py
  3. Add HODL via CLI: python core/oracle.py --add TOKEN QTY PRICE TP1 TP2 TP3 STOP
{'═'*66}
    """)


if __name__ == "__main__":
    main()
