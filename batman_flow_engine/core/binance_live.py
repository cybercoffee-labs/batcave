"""
BATMAN LAB — Binance API Connector (Live)

Uses YOUR API key to pull real data and eventually execute trades.

SETUP:
  1. Create .env: BINANCE_API_KEY=xxx  BINANCE_API_SECRET=xxx
  2. Test: python core/binance_live.py --test
  3. Sync: python core/binance_live.py --sync-all
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

logger = logging.getLogger("batman.binance_live")


def _load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

_load_env()

API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
BASE_URL = "https://api.binance.com"
FAPI_URL = "https://fapi.binance.com"
TIMEOUT = 15


def _is_configured():
    return bool(API_KEY and API_SECRET and len(API_KEY) > 10)


def _sign(params):
    params["timestamp"] = int(time.time() * 1000)
    query = urllib.parse.urlencode(params)
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params


def _request(method, url, params=None, signed=False):
    if signed and not _is_configured():
        return None
    params = params or {}
    if signed:
        params = _sign(params)
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}" if query else url
    headers = {"User-Agent": "batman-lab/2.0", "X-MBX-APIKEY": API_KEY}
    try:
        req = urllib.request.Request(full_url, headers=headers, method=method)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error("API error %s: %s", e.code, body[:200])
        return None
    except Exception as e:
        logger.error("Request failed: %s", e)
        return None


def _real_token_name(asset):
    """Strip Binance Earn prefixes. LDXRP -> XRP, LDVET -> VET."""
    if asset.startswith("LD") and len(asset) > 2:
        return asset[2:]
    return asset


# ─────────────────────── ACCOUNT ───────────────────────

def test_connection():
    server_time = _request("GET", f"{BASE_URL}/api/v3/time")
    if not server_time:
        return {"status": "error", "error": "Cannot reach Binance API"}
    if not _is_configured():
        return {"status": "no_keys", "message": "Create .env file first"}
    account = _request("GET", f"{BASE_URL}/api/v3/account", signed=True)
    if not account:
        return {"status": "auth_failed", "error": "API keys invalid"}
    return {
        "status": "ok",
        "permissions": account.get("permissions", []),
        "can_trade": account.get("canTrade", False),
        "can_withdraw": account.get("canWithdraw", False),
        "account_type": account.get("accountType", "UNKNOWN"),
        "balances_count": len([b for b in account.get("balances", []) if float(b["free"]) > 0 or float(b["locked"]) > 0]),
    }


# ─────────────────────── BALANCES ───────────────────────

def get_spot_balances():
    account = _request("GET", f"{BASE_URL}/api/v3/account", signed=True)
    if not account:
        return []
    balances = []
    for b in account.get("balances", []):
        free, locked = float(b["free"]), float(b["locked"])
        total = free + locked
        if total > 0.00001:
            balances.append({"asset": b["asset"], "free": free, "locked": locked, "total": total})
    return sorted(balances, key=lambda x: x["total"], reverse=True)


def get_futures_positions():
    data = _request("GET", f"{FAPI_URL}/fapi/v2/positionRisk", signed=True)
    if not data:
        return []
    positions = []
    for p in data:
        amt = float(p.get("positionAmt", 0))
        if abs(amt) > 0:
            positions.append({
                "symbol": p["symbol"], "side": "LONG" if amt > 0 else "SHORT",
                "quantity": abs(amt), "entry_price": float(p.get("entryPrice", 0)),
                "mark_price": float(p.get("markPrice", 0)),
                "unrealized_pnl": float(p.get("unRealizedProfit", 0)),
                "leverage": int(p.get("leverage", 1)),
            })
    return positions


def get_earn_positions():
    data = _request("GET", f"{BASE_URL}/sapi/v1/simple-earn/flexible/position", params={"size": 100}, signed=True)
    positions = []
    if data and data.get("rows"):
        for row in data["rows"]:
            positions.append({
                "asset": row.get("asset", ""),
                "quantity": float(row.get("totalAmount", 0)),
                "apy": float(row.get("latestAnnualPercentageRate", 0)) * 100,
                "type": "flexible",
                "accrued_reward": float(row.get("cumulativeTotalRewards", 0)),
            })
    return positions


# ─────────────────────── TRADE HISTORY ───────────────────────

def get_spot_trades(symbol, limit=500):
    data = _request("GET", f"{BASE_URL}/api/v3/myTrades", params={"symbol": symbol, "limit": limit}, signed=True)
    if not data:
        return []
    return [{
        "trade_id": f"BN-{t['id']}", "symbol": t["symbol"],
        "side": "BUY" if t["isBuyer"] else "SELL",
        "price": float(t["price"]), "quantity": float(t["qty"]),
        "fee": float(t["commission"]), "fee_asset": t["commissionAsset"],
        "ts": datetime.fromtimestamp(t["time"] / 1000, tz=timezone.utc).isoformat(),
    } for t in data]


def get_all_spot_trades(symbols=None, limit=500):
    if symbols is None:
        symbols = ["XRPUSDT", "ENAUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT",
                    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "VETUSDT", "VTHOUSDT",
                    "SUIUSDT", "GUNUSDT", "HFTUSDT", "PYTHUSDT", "SOLVUSDT"]
    all_trades = []
    for sym in symbols:
        trades = get_spot_trades(sym, limit)
        all_trades.extend(trades)
        if trades:
            print(f"  got {sym}: {len(trades)} trades")
        time.sleep(0.2)
    return sorted(all_trades, key=lambda x: x["ts"], reverse=True)


# ─────────────────────── SYNC TO POSTGRESQL ───────────────────────

def sync_balances_to_db():
    from database.postgres import save_hodl_position, get_cursor
    from core.oracle import fetch_price

    balances = get_spot_balances()
    if not balances:
        print("  No balances found")
        return 0

    synced = 0
    for b in balances:
        raw_asset = b["asset"]
        total = b["total"]
        asset = _real_token_name(raw_asset)
        is_earn = raw_asset != asset

        if asset in ("USDT", "BUSD", "USD", "FDUSD"):
            continue
        if total < 0.00001:
            continue

        price = fetch_price(asset)

        # Skip dust (less than $0.50)
        if price is not None and price * total < 0.50:
            continue

        # Check if exists
        try:
            with get_cursor() as cur:
                cur.execute("SELECT id FROM hodl_positions WHERE token = %s AND status = 'active'", (asset,))
                exists = cur.fetchone()
        except Exception:
            exists = None

        if exists:
            try:
                with get_cursor() as cur:
                    cur.execute("""
                        UPDATE hodl_positions SET quantity = %s, current_price = %s, updated_at = NOW()
                        WHERE token = %s AND status = 'active'
                    """, (total, price, asset))
                synced += 1
            except Exception:
                pass
        else:
            pos = {
                "token": asset,
                "exchange": "binance-earn" if is_earn else "binance",
                "quantity": total,
                "avg_buy_price": 0,
                "trailing_stop_pct": 15.0,
            }
            if save_hodl_position(pos):
                synced += 1
                value_str = f"${price * total:.2f}" if price else "price N/A"
                tag = " (Earn)" if is_earn else ""
                print(f"  + {asset}{tag} = {total:.4f} ({value_str})")

    return synced


def sync_trades_to_db(symbols=None):
    from database.postgres import save_trade
    trades = get_all_spot_trades(symbols)
    if not trades:
        return 0
    imported = 0
    for t in trades:
        trade_data = {
            "trade_id": t["trade_id"], "agent": "binance-live", "ts": t["ts"],
            "asset": t["symbol"].replace("USDT", "").replace("BUSD", ""),
            "market": "USDT", "side": t["side"], "price": t["price"],
            "quantity": t["quantity"], "fee": t["fee"], "status": "executed",
        }
        if save_trade(trade_data):
            imported += 1
    return imported


def calculate_avg_buy_prices():
    try:
        from database.postgres import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT asset,
                    SUM(CASE WHEN side = 'BUY' THEN quantity * price ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END), 0) as avg_buy,
                    SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) as bought,
                    SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) as sold
                FROM trades WHERE agent = 'binance-live' GROUP BY asset
            """)
            return {row[0]: {"avg_buy_price": float(row[1]) if row[1] else 0,
                             "total_bought": float(row[2]), "total_sold": float(row[3])} for row in cur.fetchall()}
    except Exception:
        return {}


def update_hodl_avg_prices():
    avg_prices = calculate_avg_buy_prices()
    if not avg_prices:
        return 0
    updated = 0
    try:
        from database.postgres import get_cursor
        with get_cursor() as cur:
            for asset, data in avg_prices.items():
                if data["avg_buy_price"] > 0:
                    cur.execute("""
                        UPDATE hodl_positions SET avg_buy_price = %s, updated_at = NOW()
                        WHERE token = %s AND status = 'active' AND avg_buy_price = 0
                    """, (data["avg_buy_price"], asset))
                    updated += cur.rowcount
    except Exception:
        pass
    return updated


# ─────────────────────── FULL SYNC ───────────────────────

def full_sync():
    print(f"""
{'='*66}
  BATMAN LAB — Binance Full Sync
{'='*66}
    """)

    print("  Testing connection...")
    conn = test_connection()
    if conn["status"] != "ok":
        print(f"  ERROR: {conn.get('error', conn.get('message', '?'))}")
        return
    print(f"  Connected! Assets with balance: {conn['balances_count']}")

    # Step 1: Balances
    print(f"\n  Step 1: Syncing balances...")
    balances = get_spot_balances()
    print(f"  Found {len(balances)} assets:")
    for b in balances[:15]:
        real = _real_token_name(b['asset'])
        tag = " (Earn)" if real != b['asset'] else ""
        print(f"    {real:8s}{tag:8s} {b['total']:>15.6f}")
    if len(balances) > 15:
        print(f"    ... and {len(balances) - 15} more")

    synced = sync_balances_to_db()
    print(f"  Synced {synced} positions to database")

    # Step 2: Trades
    print(f"\n  Step 2: Syncing trade history...")
    imported = sync_trades_to_db()
    print(f"  Imported {imported} trades")

    # Step 3: Avg prices
    print(f"\n  Step 3: Calculating average buy prices...")
    updated = update_hodl_avg_prices()
    print(f"  Updated {updated} positions with avg buy price")

    # Step 4: Futures
    print(f"\n  Step 4: Checking futures...")
    futures = get_futures_positions()
    if futures:
        for f in futures:
            s = "+" if f["unrealized_pnl"] >= 0 else ""
            print(f"    {f['symbol']} {f['side']} {f['quantity']} @ ${f['entry_price']:.2f} | PnL: {s}${f['unrealized_pnl']:.2f}")
    else:
        print(f"    No open futures")

    # Step 5: Earn
    print(f"\n  Step 5: Checking Earn...")
    earn = get_earn_positions()
    if earn:
        for e in earn:
            print(f"    {e['asset']}: {e['quantity']:.4f} | APY: {e['apy']:.1f}% | Rewards: {e['accrued_reward']:.6f}")
    else:
        print(f"    No Earn positions")

    print(f"\n{'='*66}")
    print(f"  DONE. Run: python tools/command_center.py")
    print(f"{'='*66}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        print(json.dumps(test_connection(), indent=2))
    elif "--balances" in args:
        for b in get_spot_balances():
            real = _real_token_name(b['asset'])
            print(f"  {real:8s} {b['total']:>15.8f}")
    elif "--sync-all" in args:
        full_sync()
    elif "--trades" in args:
        trades = get_all_spot_trades()
        print(f"  Total: {len(trades)} trades")
    elif "--positions" in args:
        print(json.dumps(get_futures_positions(), indent=2))
    else:
        print(__doc__)
