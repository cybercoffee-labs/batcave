"""
🦇 BATMAN LAB — Binance API Connector (Live Data Sync)

Connects to Binance API with YOUR keys to pull:
  - Wallet balances (all coins)
  - Spot trade history
  - P2P trade history
  - Open orders
  - Deposit/withdrawal history

Setup:
  1. Copy .env.example to .env
  2. Fill in your BINANCE_API_KEY and BINANCE_API_SECRET
  3. Run: python core/binance_sync.py --balances

Usage:
  python core/binance_sync.py --balances     # Show all balances
  python core/binance_sync.py --trades       # Import trade history
  python core/binance_sync.py --hodl         # Auto-create HODL positions from balances
  python core/binance_sync.py --full         # Everything
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.parse
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger("batman.binance_sync")

# ─────────────────────── LOAD API KEYS ───────────────────────


def _load_env():
    """Load .env file."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


_load_env()

API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
BASE_URL = "https://api.binance.com"


def _check_keys():
    if not API_KEY or API_KEY == "your_api_key_here":
        print("""
  ❌ Binance API keys not configured.

  1. Copy .env.example to .env:
     cp .env.example .env

  2. Edit .env with your real keys:
     nano .env

  3. Paste your BINANCE_API_KEY and BINANCE_API_SECRET

  ⚠️  IMPORTANT: Use a READ-ONLY API key for safety!
        """)
        return False
    return True


# ─────────────────────── SIGNED API REQUESTS ───────────────────────


def _sign_request(params: dict) -> dict:
    """Add timestamp and HMAC-SHA256 signature to request params."""
    params["timestamp"] = int(time.time() * 1000)
    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(API_SECRET.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params


def _api_request(endpoint: str, params: dict = None, signed: bool = False) -> Optional[dict]:
    """Make a Binance API request."""
    params = params or {}

    if signed:
        params = _sign_request(params)

    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{endpoint}"
    if query:
        url = f"{url}?{query}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "X-MBX-APIKEY": API_KEY,
                "User-Agent": "batman-lab/1.0",
            },
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        logger.error("Binance API error %s: %s — %s", e.code, endpoint, error_body)
        print(f"  ❌ API Error {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        logger.error("Binance API request failed: %s", e)
        return None


# ─────────────────────── ACCOUNT DATA ───────────────────────


def get_account_balances() -> list:
    """Get all non-zero balances from Binance account."""
    data = _api_request("/api/v3/account", signed=True)
    if not data:
        return []

    balances = []
    for b in data.get("balances", []):
        free = float(b.get("free", 0))
        locked = float(b.get("locked", 0))
        total = free + locked
        if total > 0:
            balances.append(
                {
                    "asset": b["asset"],
                    "free": free,
                    "locked": locked,
                    "total": total,
                }
            )

    # Sort by estimated USD value (fetch prices for top assets)
    return sorted(balances, key=lambda x: x["total"], reverse=True)


def get_spot_trades(symbol: str, limit: int = 500) -> list:
    """Get spot trade history for a specific symbol."""
    data = _api_request("/api/v3/myTrades", {"symbol": symbol, "limit": limit}, signed=True)
    return data if isinstance(data, list) else []


def get_all_spot_trades(symbols: list = None, limit: int = 500) -> list:
    """Get spot trades for multiple symbols."""
    if not symbols:
        # Get symbols from balances
        balances = get_account_balances()
        symbols = [f"{b['asset']}USDT" for b in balances if b["asset"] not in ("USDT", "BUSD", "USD", "MXN")]

    all_trades = []
    for symbol in symbols:
        print(f"    Fetching {symbol}...")
        trades = get_spot_trades(symbol, limit)
        for t in trades:
            all_trades.append(
                {
                    "trade_id": f"BN-{t['id']}",
                    "agent": "binance-spot",
                    "ts": datetime.fromtimestamp(t["time"] / 1000, tz=timezone.utc).isoformat(),
                    "asset": t.get("symbol", symbol).replace("USDT", ""),
                    "market": "USDT",
                    "side": "BUY" if t.get("isBuyer") else "SELL",
                    "price": float(t.get("price", 0)),
                    "quantity": float(t.get("qty", 0)),
                    "fee": float(t.get("commission", 0)),
                    "status": "executed",
                    "metadata": {
                        "source": "binance-api",
                        "binance_trade_id": t["id"],
                        "symbol": symbol,
                        "fee_asset": t.get("commissionAsset"),
                        "is_maker": t.get("isMaker"),
                    },
                }
            )
        time.sleep(0.2)  # Rate limit

    return sorted(all_trades, key=lambda x: x["ts"])


def get_deposit_history(days: int = 90) -> list:
    """Get recent deposit history."""
    start_time = int((time.time() - days * 86400) * 1000)
    data = _api_request("/sapi/v1/capital/deposit/hisrec", {"startTime": start_time}, signed=True)
    return data if isinstance(data, list) else []


def get_withdrawal_history(days: int = 90) -> list:
    """Get recent withdrawal history."""
    start_time = int((time.time() - days * 86400) * 1000)
    data = _api_request("/sapi/v1/capital/withdraw/history", {"startTime": start_time}, signed=True)
    return data if isinstance(data, list) else []


# ─────────────────────── PRICE ENRICHMENT ───────────────────────


def get_all_prices() -> dict:
    """Get current prices for all symbols."""
    data = _api_request("/api/v3/ticker/price")
    if not data:
        return {}
    return {item["symbol"]: float(item["price"]) for item in data}


def enrich_balances_with_usd(balances: list) -> list:
    """Add USD value to each balance."""
    prices = get_all_prices()

    for b in balances:
        asset = b["asset"]
        if asset in ("USDT", "BUSD", "USD"):
            b["usd_value"] = b["total"]
            b["price_usd"] = 1.0
        else:
            symbol = f"{asset}USDT"
            price = prices.get(symbol, 0)
            b["price_usd"] = price
            b["usd_value"] = b["total"] * price

    return sorted(balances, key=lambda x: x.get("usd_value", 0), reverse=True)


# ─────────────────────── AUTO HODL SETUP ───────────────────────


def auto_create_hodl_positions(balances: list, min_usd: float = 1.0):
    """Automatically create HODL positions from Binance balances.
    Only creates for assets worth > min_usd.
    Does NOT set targets — those need to be set manually.
    """
    from database.postgres import save_hodl_position

    created = 0
    for b in balances:
        if b.get("usd_value", 0) < min_usd:
            continue
        if b["asset"] in ("USDT", "BUSD", "USD", "MXN", "BNB"):
            continue  # Skip stablecoins and dust

        pos = {
            "token": b["asset"],
            "exchange": "binance",
            "quantity": b["total"],
            "avg_buy_price": b.get("price_usd", 0),  # Current price as placeholder
        }

        if save_hodl_position(pos):
            created += 1
            print(f"    ✅ {b['asset']}: {b['total']:.4f} (${b.get('usd_value', 0):.2f})")

    return created


# ─────────────────────── SYNC TO POSTGRES ───────────────────────


def sync_trades_to_db(trades: list) -> int:
    """Save imported trades to PostgreSQL."""
    from database.postgres import save_trade

    imported = 0
    for trade in trades:
        if save_trade(trade):
            imported += 1
    return imported


# ─────────────────────── CLI ───────────────────────


def show_balances():
    """Display all Binance balances with USD values."""
    print("\n  📊 Fetching Binance balances...")
    balances = get_account_balances()

    if not balances:
        print("  ❌ No balances found (check API key)")
        return

    balances = enrich_balances_with_usd(balances)

    print("""
╔══════════════════════════════════════════════════════════════════╗
║          💰 BINANCE WALLET — Live Balances                       ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    total_usd = 0
    for b in balances:
        usd = b.get("usd_value", 0)
        if usd < 0.01:
            continue
        total_usd += usd

        locked_str = f" (🔒{b['locked']:.4f})" if b["locked"] > 0 else ""
        print(f"  {b['asset']:8s} {b['total']:>15.4f}{locked_str:20s} ${usd:>10.2f}")

    print(f"\n  {'─'*60}")
    print(f"  {'TOTAL':8s} {'':>15s} {'':20s} ${total_usd:>10.2f}")
    print()

    return balances


def show_and_import_trades():
    """Fetch and import spot trades into PostgreSQL."""
    print("\n  📊 Fetching Binance trade history...")

    balances = get_account_balances()
    symbols = [
        f"{b['asset']}USDT"
        for b in balances
        if b["asset"] not in ("USDT", "BUSD", "USD", "MXN", "BNB") and b["total"] > 0
    ]

    if not symbols:
        print("  No assets to fetch trades for")
        return

    print(f"  Fetching trades for {len(symbols)} assets: {', '.join(s.replace('USDT','') for s in symbols[:10])}...")
    trades = get_all_spot_trades(symbols)

    print(f"\n  📊 Found {len(trades)} trades total")
    if not trades:
        return

    # Preview
    print("\n  Latest 5 trades:")
    for t in trades[-5:]:
        print(f"    {t['ts'][:16]} {t['side']:4s} {t['quantity']:.4f} {t['asset']} @ ${t['price']:.4f}")

    print(f"\n  Import {len(trades)} trades to PostgreSQL? (y/n): ", end="")
    if input().strip().lower() == "y":
        imported = sync_trades_to_db(trades)
        print(f"  ✅ Imported {imported} trades")


def auto_hodl():
    """Auto-create HODL positions from current balances."""
    print("\n  🔮 Creating HODL positions from Binance balances...")
    balances = get_account_balances()
    balances = enrich_balances_with_usd(balances)

    created = auto_create_hodl_positions(balances, min_usd=1.0)
    print(f"\n  ✅ Created {created} HODL positions")
    print("  ⚠️  Targets NOT set — use Oracle to add TP1/TP2/TP3/stop:")
    print("     python tools/command_center.py --hodl")


def full_sync():
    """Full sync: balances + trades + HODL positions."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║       🦇 BATMAN LAB — Full Binance Sync                          ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    balances = show_balances()
    if not balances:
        return

    print("\n  📦 Step 2: Import trade history...")
    show_and_import_trades()

    print("\n  📦 Step 3: Create HODL positions...")
    auto_hodl()

    print("""
  ═══════════════════════════════════════════════════
  ✅ SYNC COMPLETE

  Next: Set your targets and stops:
    python tools/command_center.py --hodl
    python core/oracle.py --status
  ═══════════════════════════════════════════════════
    """)


if __name__ == "__main__":
    if not _check_keys():
        sys.exit(1)

    args = sys.argv[1:]

    if "--balances" in args:
        show_balances()
    elif "--trades" in args:
        show_and_import_trades()
    elif "--hodl" in args:
        auto_hodl()
    elif "--full" in args:
        full_sync()
    else:
        print("""
  🦇 Binance Sync — Usage:
    python core/binance_sync.py --balances   # Show wallet balances
    python core/binance_sync.py --trades     # Import trade history
    python core/binance_sync.py --hodl       # Auto-create HODL positions
    python core/binance_sync.py --full       # Everything
        """)
