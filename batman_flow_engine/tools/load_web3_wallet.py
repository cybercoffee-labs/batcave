#!/usr/bin/env python3
"""Load Erick's Web3 wallet positions into PostgreSQL."""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from database.postgres import save_venture_position

# Real data from Binance Web3 Wallet — March 23, 2026
positions = [
    # Token, Chain, Value USD, PnL%, BNB amount
    {
        "token": "ARIA",
        "chain": "bsc",
        "quantity": 0.052366,
        "avg_buy_price": 0,
        "current_value_usd": 32.94,
        "pnl_pct": 92.32,
        "notes": "Best performer +92%",
    },
    {
        "token": "NAORIS",
        "chain": "bsc",
        "quantity": 0.014037,
        "avg_buy_price": 0,
        "current_value_usd": 8.83,
        "pnl_pct": 6.92,
        "notes": "Slight profit",
    },
    {
        "token": "ASTER",
        "chain": "bsc",
        "quantity": 0.013153,
        "avg_buy_price": 0,
        "current_value_usd": 8.27,
        "pnl_pct": -41.80,
        "notes": "Down 41%",
    },
    {
        "token": "UB",
        "chain": "bsc",
        "quantity": 0.012103,
        "avg_buy_price": 0,
        "current_value_usd": 7.61,
        "pnl_pct": 0,
        "notes": "",
    },
    {
        "token": "BLUAI",
        "chain": "bsc",
        "quantity": 0.009068,
        "avg_buy_price": 0,
        "current_value_usd": 5.70,
        "pnl_pct": -74.33,
        "notes": "Down 74%",
    },
    {
        "token": "XPIN",
        "chain": "bsc",
        "quantity": 0.0076602,
        "avg_buy_price": 0,
        "current_value_usd": 4.81,
        "pnl_pct": 0,
        "notes": "",
    },
    {
        "token": "PEAQ",
        "chain": "bsc",
        "quantity": 0.0073856,
        "avg_buy_price": 0,
        "current_value_usd": 4.64,
        "pnl_pct": -72.72,
        "notes": "Down 72%",
    },
    {
        "token": "VELO",
        "chain": "bsc",
        "quantity": 0.0066336,
        "avg_buy_price": 0,
        "current_value_usd": 4.17,
        "pnl_pct": 0,
        "notes": "",
    },
    {
        "token": "XAN",
        "chain": "bsc",
        "quantity": 0.0051389,
        "avg_buy_price": 0,
        "current_value_usd": 3.23,
        "pnl_pct": -77.09,
        "notes": "Down 77%",
    },
    {
        "token": "TURTLE",
        "chain": "bsc",
        "quantity": 0.0030646,
        "avg_buy_price": 0,
        "current_value_usd": 1.92,
        "pnl_pct": -76.99,
        "notes": "Down 77%",
    },
    {
        "token": "P",
        "chain": "bsc",
        "quantity": 0.002133,
        "avg_buy_price": 0,
        "current_value_usd": 1.34,
        "pnl_pct": 0,
        "notes": "",
    },
]

print("Loading Web3 wallet positions...")
count = 0
for pos in positions:
    if save_venture_position(pos):
        pnl = pos["pnl_pct"]
        pnl_str = f"+{pnl:.1f}%" if pnl > 0 else f"{pnl:.1f}%" if pnl < 0 else "N/A"
        print(f"  ✅ {pos['token']:10s} ${pos['current_value_usd']:>7.2f} | {pnl_str}")
        count += 1

print(f"\n  Loaded {count} Web3 positions ($83.77 total)")
print("  Best: ARIA +92% | Worst: XAN -77%")
