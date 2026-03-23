"""
ORACLE Module — HODL Portfolio Manager + Anti-FOMO System

Tracks long-term crypto holdings (XRP, ENA, etc.)
Sets targets, trailing stops, and alerts when to SELL or HOLD.
The system that solves "suben y no sé cuándo venderlas"

Usage:
  python core/oracle.py --status           # Show all positions
  python core/oracle.py --check            # Check alerts
  python core/oracle.py --add XRP 100 0.55 1.00 1.50 2.50 0.40
"""

import json
import logging
import sys
import urllib.request
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Fix import path — core/database.py shadows database/ package
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger("batman.oracle")

# ─────────────────────── PRICE FETCHING ───────────────────────

BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
    "XRP": "XRPUSDT", "ENA": "ENAUSDT", "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT", "AVAX": "AVAXUSDT", "LINK": "LINKUSDT",
    "DOT": "DOTUSDT", "MATIC": "MATICUSDT", "UNI": "UNIUSDT",
    "ATOM": "ATOMUSDT", "NEAR": "NEARUSDT", "APT": "APTUSDT",
    "ARB": "ARBUSDT", "OP": "OPUSDT", "FIL": "FILUSDT",
    "LTC": "LTCUSDT", "BCH": "BCHUSDT", "XLM": "XLMUSDT",
    "PEPE": "PEPEUSDT", "SHIB": "SHIBUSDT", "WIF": "WIFUSDT",
}


def fetch_price(token: str) -> Optional[float]:
    """Fetch current price from Binance."""
    symbol = BINANCE_SYMBOLS.get(token.upper(), f"{token.upper()}USDT")
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "batman-oracle/1.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            return float(data["price"])
    except Exception as e:
        logger.warning("Failed to fetch price for %s: %s", token, e)
        return None


def fetch_all_prices(tokens: list) -> dict:
    prices = {}
    for token in tokens:
        price = fetch_price(token)
        if price is not None:
            prices[token] = price
    return prices


# ─────────────────────── SIGNAL LOGIC ───────────────────────

def evaluate_position(pos: dict, current_price: float) -> dict:
    """Evaluate a HODL position and generate signal."""
    avg_buy = float(pos.get("avg_buy_price", 0))
    tp1 = pos.get("take_profit_1")
    tp2 = pos.get("take_profit_2")
    tp3 = pos.get("take_profit_3")
    stop = pos.get("stop_loss")
    trail_pct = float(pos.get("trailing_stop_pct", 15))
    peak = float(pos.get("peak_price", 0) or 0)
    quantity = float(pos.get("quantity", 0))

    new_peak = max(peak, current_price)

    if avg_buy > 0:
        pnl_pct = ((current_price - avg_buy) / avg_buy) * 100
        pnl_usd = (current_price - avg_buy) * quantity
    else:
        pnl_pct = 0
        pnl_usd = 0

    multiplier = current_price / avg_buy if avg_buy > 0 else 0

    signal = "HOLD"
    urgency = "low"
    action = None

    if stop and current_price <= float(stop):
        signal = "STOP_LOSS_HIT"
        urgency = "critical"
        action = f"SELL ALL — price ${current_price:.4f} hit stop loss ${float(stop):.4f}"

    elif new_peak > 0 and current_price < new_peak * (1 - trail_pct / 100):
        trail_price = new_peak * (1 - trail_pct / 100)
        signal = "TRAILING_STOP"
        urgency = "critical"
        action = f"SELL — dropped {trail_pct}% from peak ${new_peak:.4f} (trail trigger: ${trail_price:.4f})"

    elif tp3 and current_price >= float(tp3) and not pos.get("tp3_hit"):
        signal = "TP3_HIT"
        urgency = "high"
        action = f"SELL 25% — TP3 ${float(tp3):.4f} reached! Keep 25% moon bag"

    elif tp2 and current_price >= float(tp2) and not pos.get("tp2_hit"):
        signal = "TP2_HIT"
        urgency = "high"
        action = f"SELL 25% — TP2 ${float(tp2):.4f} reached!"

    elif tp1 and current_price >= float(tp1) and not pos.get("tp1_hit"):
        signal = "TP1_HIT"
        urgency = "medium"
        action = f"SELL 25% — TP1 ${float(tp1):.4f} reached!"

    elif pnl_pct > 50:
        signal = "STRONG_PROFIT"
        urgency = "low"
        action = f"Consider taking partial profits ({pnl_pct:.1f}% up)"

    return {
        "token": pos.get("token"),
        "current_price": current_price,
        "avg_buy_price": avg_buy,
        "quantity": quantity,
        "pnl_pct": round(pnl_pct, 2),
        "pnl_usd": round(pnl_usd, 2),
        "multiplier": round(multiplier, 2),
        "peak_price": new_peak,
        "signal": signal,
        "urgency": urgency,
        "action": action,
    }


# ─────────────────────── DATABASE OPERATIONS ───────────────────────

def load_positions_from_db():
    try:
        from database.postgres import get_all_hodl
        return get_all_hodl()
    except Exception:
        return []


def save_position_to_db(pos: dict):
    try:
        from database.postgres import save_hodl_position
        return save_hodl_position(pos)
    except Exception as e:
        logger.error("Failed to save position: %s", e)
        print(f"Failed to save position: {e}")
        return False


def update_prices_in_db(prices: dict):
    try:
        from database.postgres import update_hodl_prices
        return update_hodl_prices(prices)
    except Exception as e:
        logger.error("Failed to update prices: %s", e)
        return 0


def save_alert_to_db(source, title, message, severity="info", metadata=None):
    try:
        from database.postgres import save_alert
        return save_alert(source, title, message, severity, metadata)
    except Exception:
        return False


# ─────────────────────── CHECK CYCLE ───────────────────────

def check_all_positions():
    positions = load_positions_from_db()

    if not positions:
        print("  No HODL positions found. Use --add to add positions.")
        return []

    tokens = list(set(p.get("token") for p in positions if p.get("token")))
    print(f"  Fetching prices for {len(tokens)} tokens...")
    prices = fetch_all_prices(tokens)

    if not prices:
        print("  ❌ Could not fetch any prices")
        return []

    updated = update_prices_in_db(prices)
    print(f"  Updated {updated} positions in database")

    results = []
    for pos in positions:
        token = pos.get("token")
        price = prices.get(token)
        if price is None:
            continue

        evaluation = evaluate_position(pos, price)
        results.append(evaluation)

        if evaluation["signal"] != "HOLD":
            save_alert_to_db(
                source="oracle",
                title=f"{token}: {evaluation['signal']}",
                message=evaluation.get("action", ""),
                severity="critical" if evaluation["urgency"] == "critical" else "warning",
                metadata=evaluation,
            )

    return results


# ─────────────────────── CLI ───────────────────────

def print_status():
    results = check_all_positions()
    if not results:
        return

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          🔮 ORACLE — HODL Portfolio Status                       ║
╚══════════════════════════════════════════════════════════════════╝
    """)

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
        elif signal == "STRONG_PROFIT":
            icon = "🟡"
        else:
            icon = "⚪"

        pnl_sign = "+" if pnl_pct >= 0 else ""
        print(f"  {icon} {token:6s} | ${price:<10.4f} | {pnl_sign}{pnl_pct:.1f}% | ${pnl_sign}{pnl_usd:.2f} | {r['multiplier']:.2f}x | {signal}")

        if r.get("action"):
            print(f"     ⚡ ACTION: {r['action']}")

    print(f"\n{'─'*66}")
    pnl_sign = "+" if total_pnl >= 0 else ""
    print(f"  💰 Total value: ${total_value:.2f} | P&L: {pnl_sign}${total_pnl:.2f}")
    print()


def add_position(token, quantity, avg_price, tp1=None, tp2=None, tp3=None, stop=None, trail=15.0):
    pos = {
        "token": token.upper(),
        "exchange": "binance",
        "quantity": float(quantity),
        "avg_buy_price": float(avg_price),
        "take_profit_1": float(tp1) if tp1 else None,
        "take_profit_2": float(tp2) if tp2 else None,
        "take_profit_3": float(tp3) if tp3 else None,
        "stop_loss": float(stop) if stop else None,
        "trailing_stop_pct": float(trail),
    }

    success = save_position_to_db(pos)
    if success:
        print(f"  ✅ Added {token.upper()}: {quantity} @ ${avg_price}")
        if tp1:
            print(f"     TP1: ${tp1} | TP2: ${tp2} | TP3: ${tp3}")
        if stop:
            print(f"     Stop: ${stop} | Trail: {trail}%")
    else:
        print(f"  ❌ Failed to add {token}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--add" in args:
        idx = args.index("--add")
        remaining = args[idx + 1:]
        if len(remaining) >= 3:
            token, qty, price = remaining[0], remaining[1], remaining[2]
            tp1 = remaining[3] if len(remaining) > 3 else None
            tp2 = remaining[4] if len(remaining) > 4 else None
            tp3 = remaining[5] if len(remaining) > 5 else None
            stop = remaining[6] if len(remaining) > 6 else None
            add_position(token, qty, price, tp1, tp2, tp3, stop)
        else:
            print("Usage: python core/oracle.py --add TOKEN QTY PRICE [TP1 TP2 TP3 STOP]")
    elif "--check" in args:
        results = check_all_positions()
        alerts = [r for r in results if r["signal"] != "HOLD"]
        if alerts:
            print(f"\n  ⚠️  {len(alerts)} ALERTS:")
            for a in alerts:
                print(f"    {a['token']}: {a['signal']} — {a.get('action', '')}")
        else:
            print("  ✅ All positions normal. HOLD.")
    else:
        print_status()
