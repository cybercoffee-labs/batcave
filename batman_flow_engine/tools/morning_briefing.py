#!/usr/bin/env python3
"""
BATMAN LAB — MORNING BRIEFING

Run this at 7 AM before you start operating.
Shows: overnight scanner results + economic news + market state + best opportunities.

Usage:
  python tools/morning_briefing.py
  python tools/morning_briefing.py --json
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
LATEST_FILE = BASE_DIR / "storage" / "latest.json"

SCANNER_NAMES = {
    "A": "Cross-Exchange (Binance vs OKX)",
    "B": "Basis (Spot vs Futures)",
    "C": "P2P Spot Arbitrage",
    "D": "Multi-Exchange (20 coins × 5 exchanges)",
    "E": "Funding Rate Arbitrage",
    "F": "Cross-Currency P2P",
    "G": "P2P Merchant Spread",
    "H": "Stablecoin Depeg",
    "I": "Cross-Platform MXN",
    "J": "DEX vs CEX (Uniswap/PancakeSwap vs Binance)",
    "K": "Futures vs Futures (Binance/OKX/Bybit perps)",
}


def _fetch_economic_headlines():
    headlines = []
    try:
        req = urllib.request.Request(
            "https://api.coingecko.com/api/v3/global",
            headers={"User-Agent": "batman-lab/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())["data"]
            headlines.append(
                {
                    "source": "CoinGecko Global",
                    "data": {
                        "btc_dominance": round(data.get("market_cap_percentage", {}).get("btc", 0), 1),
                        "total_market_cap_usd": round(data.get("total_market_cap", {}).get("usd", 0) / 1e9, 1),
                        "market_cap_change_24h": round(data.get("market_cap_change_percentage_24h_usd", 0), 2),
                    },
                }
            )
    except Exception as e:
        headlines.append({"source": "CoinGecko", "error": str(e)})

    try:
        req = urllib.request.Request(
            "https://api.alternative.me/fng/?limit=1", headers={"User-Agent": "batman-lab/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())["data"][0]
            headlines.append(
                {
                    "source": "Fear & Greed Index",
                    "data": {"value": int(data["value"]), "classification": data["value_classification"]},
                }
            )
    except Exception as e:
        headlines.append({"source": "Fear & Greed", "error": str(e)})

    try:
        req = urllib.request.Request("https://open.er-api.com/v6/latest/USD", headers={"User-Agent": "batman-lab/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            headlines.append(
                {
                    "source": "FX Rates",
                    "data": {
                        "USD_MXN": round(data.get("rates", {}).get("MXN", 0), 4),
                        "USD_ARS": round(data.get("rates", {}).get("ARS", 0), 4),
                    },
                }
            )
    except Exception as e:
        headlines.append({"source": "FX Rates", "error": str(e)})

    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", headers={"User-Agent": "batman-lab/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            headlines.append(
                {
                    "source": "Binance BTC/USDT",
                    "data": {
                        "price": round(float(data["lastPrice"]), 2),
                        "change_24h_pct": round(float(data["priceChangePercent"]), 2),
                        "volume_24h_usd": round(float(data["quoteVolume"]) / 1e6, 1),
                    },
                }
            )
    except Exception as e:
        headlines.append({"source": "Binance BTC", "error": str(e)})

    return headlines


def _read_overnight_opportunities():
    if not OPPS_FILE.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    opps = []
    for line in OPPS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("ts", "") > cutoff:
                opps.append(r)
        except Exception:
            continue
    return opps


def _batman_health():
    if not LATEST_FILE.exists():
        return {"status": "NOT RUNNING", "age_minutes": 9999}
    try:
        data = json.loads(LATEST_FILE.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        return {
            "status": "ALIVE" if age < 30 else "STALE",
            "age_minutes": round(age, 1),
            "last_run": data["timestamp"],
            "dq_score": data.get("data_quality", {}).get("dq_score"),
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def morning_briefing():
    now = datetime.now()
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          🦇 BATMAN LAB — MORNING BRIEFING                       ║
║          {now.strftime('%A %B %d, %Y — %H:%M')}                          ║
║          11 Scanners | 20 Coins | 7 CEX + 3 DEX                ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    health = _batman_health()
    status_icon = "🟢" if health["status"] == "ALIVE" else "🔴"
    print(f"  {status_icon} Batman: {health['status']} (last run {health.get('age_minutes', '?')} min ago)")
    if health.get("dq_score"):
        print(f"     Data quality: {health['dq_score']*100:.0f}%")

    print(f"\n{'═'*66}")
    print("  📰 MARKET OVERVIEW")
    print(f"{'═'*66}")

    for h in _fetch_economic_headlines():
        if "error" in h:
            print(f"  ❌ {h['source']}: {h['error']}")
        else:
            source, data = h["source"], h["data"]
            if source == "CoinGecko Global":
                print(
                    f"  🌍 Crypto Market Cap: ${data['total_market_cap_usd']}B ({data['market_cap_change_24h']:+.2f}% 24h)"
                )
                print(f"     BTC Dominance: {data['btc_dominance']}%")
            elif source == "Fear & Greed Index":
                emoji = (
                    "😱"
                    if data["value"] < 25
                    else "😰"
                    if data["value"] < 45
                    else "😐"
                    if data["value"] < 55
                    else "😊"
                    if data["value"] < 75
                    else "🤑"
                )
                print(f"  {emoji} Fear & Greed: {data['value']} ({data['classification']})")
            elif source == "FX Rates":
                print(f"  💱 USD/MXN: {data['USD_MXN']}  |  USD/ARS: {data['USD_ARS']}")
            elif source == "Binance BTC/USDT":
                arrow = "📈" if data["change_24h_pct"] > 0 else "📉"
                print(
                    f"  {arrow} BTC: ${data['price']:,.2f} ({data['change_24h_pct']:+.2f}%) | Vol: ${data['volume_24h_usd']}M"
                )

    print(f"\n{'═'*66}")
    print("  🔍 SCANNER RESULTS (last 12h) — 11 scanners active")
    print(f"{'═'*66}")

    opps = _read_overnight_opportunities()
    if not opps:
        print("  No opportunities detected.")
    else:
        by_type = {}
        for o in opps:
            by_type.setdefault(o.get("type", "?"), []).append(o)

        for st in sorted(by_type.keys()):
            so = by_type[st]
            name = SCANNER_NAMES.get(st, f"Scanner {st}")
            edges = [o.get("edge_net", 0) for o in so if o.get("edge_net") is not None]
            viable = [o for o in so if o.get("viable")]
            avg_edge = sum(edges) / len(edges) if edges else 0
            icon = "✅" if viable else "⚪"
            print(f"  {icon} [{st}] {name}")
            print(f"     {len(so)} detected | {len(viable)} viable | avg edge: {avg_edge:+.3f}%")

        viable_all = [o for o in opps if o.get("viable") and o.get("edge_net")]
        if viable_all:
            best = max(viable_all, key=lambda x: x.get("edge_net", 0))
            bt = best.get("type", "?")
            print(f"\n  ⭐ BEST: [{bt}] {SCANNER_NAMES.get(bt, '?')} — Edge: {best.get('edge_net', 0):+.3f}%")

    print(f"\n{'═'*66}")
    print("  📋 ACTION ITEMS")
    print(f"{'═'*66}")
    print("  1. Open dashboard: streamlit run dashboard/app.py")
    print("  2. Check Trade Cockpit for live opportunities")
    print("  3. Record trades in the Journal tab")
    print("  4. Review P&L at end of day")
    print(f"\n{'═'*66}")
    print("  Good morning, Erick. 11 scanners watching. Let's go. 🦇")
    print(f"{'═'*66}\n")


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(
            json.dumps(
                {
                    "health": _batman_health(),
                    "headlines": _fetch_economic_headlines(),
                    "opportunities": _read_overnight_opportunities(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
                default=str,
            )
        )
    else:
        morning_briefing()
