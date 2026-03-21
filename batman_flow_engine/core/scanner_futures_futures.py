"""
Scanner K: Futures vs Futures Arbitrage

PURPOSE: Compare perpetual futures prices between exchanges.
         Long on cheaper exchange, short on expensive one.
         Also capture funding rate differentials.

EXCHANGES: Binance Futures, OKX Perp, Bybit Linear
ASSETS: BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK, DOT, ARB

OUTPUT: storage/logs/opportunities.jsonl
FIELDS: type: "K", scanner_id: "K-FUTURES-FUTURES"
"""

import json
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

SCANNER_ID = "K-FUTURES-FUTURES"
TIMEOUT = 10
RETRIES = 2
USER_AGENT = "batman-flow-engine/1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

ASSETS = [
    {"asset": "BTC", "binance": "BTCUSDT", "okx": "BTC-USDT-SWAP", "bybit": "BTCUSDT"},
    {"asset": "ETH", "binance": "ETHUSDT", "okx": "ETH-USDT-SWAP", "bybit": "ETHUSDT"},
    {"asset": "SOL", "binance": "SOLUSDT", "okx": "SOL-USDT-SWAP", "bybit": "SOLUSDT"},
    {"asset": "XRP", "binance": "XRPUSDT", "okx": "XRP-USDT-SWAP", "bybit": "XRPUSDT"},
    {"asset": "DOGE", "binance": "DOGEUSDT", "okx": "DOGE-USDT-SWAP", "bybit": "DOGEUSDT"},
    {"asset": "ADA", "binance": "ADAUSDT", "okx": "ADA-USDT-SWAP", "bybit": "ADAUSDT"},
    {"asset": "AVAX", "binance": "AVAXUSDT", "okx": "AVAX-USDT-SWAP", "bybit": "AVAXUSDT"},
    {"asset": "LINK", "binance": "LINKUSDT", "okx": "LINK-USDT-SWAP", "bybit": "LINKUSDT"},
    {"asset": "DOT", "binance": "DOTUSDT", "okx": "DOT-USDT-SWAP", "bybit": "DOTUSDT"},
    {"asset": "ARB", "binance": "ARBUSDT", "okx": "ARB-USDT-SWAP", "bybit": "ARBUSDT"},
]

FEES = {"binance": 0.04, "okx": 0.05, "bybit": 0.06}


def _fetch_json(url, params=None):
    if params:
        url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            if attempt == RETRIES - 1:
                return None
            time.sleep(1)
    return None


def _append_to_log(opp):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(opp) + "\n")
        return True
    except Exception:
        return False


def _fetch_binance_futures(symbol):
    data = _fetch_json("https://fapi.binance.com/fapi/v1/ticker/bookTicker", {"symbol": symbol})
    if not data:
        return None

    try:
        result = {
            "bid": float(data["bidPrice"]),
            "ask": float(data["askPrice"]),
            "price": (float(data["bidPrice"]) + float(data["askPrice"])) / 2,
        }
    except Exception:
        return None

    # Try funding rate
    fr_data = _fetch_json("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": symbol})
    funding_rate = 0
    if fr_data:
        try:
            funding_rate = float(fr_data.get("lastFundingRate", 0))
        except Exception:
            pass
    result["funding_rate"] = funding_rate
    return result


def _fetch_okx_futures(inst_id):
    data = _fetch_json("https://www.okx.com/api/v5/market/ticker", {"instId": inst_id})
    if not data or data.get("code") != "0":
        return None

    try:
        t = data["data"][0]
        result = {"bid": float(t["bidPx"]), "ask": float(t["askPx"]), "price": float(t["last"])}
    except Exception:
        return None

    # Funding rate
    fr = _fetch_json("https://www.okx.com/api/v5/public/funding-rate", {"instId": inst_id})
    if fr and fr.get("code") == "0":
        try:
            result["funding_rate"] = float(fr["data"][0].get("fundingRate", 0))
        except Exception:
            result["funding_rate"] = 0
    else:
        result["funding_rate"] = 0
    return result


def _fetch_bybit_futures(symbol):
    data = _fetch_json("https://api.bybit.com/v5/market/tickers", {"category": "linear", "symbol": symbol})
    if not data or data.get("retCode") != 0:
        return None

    try:
        t = data["result"]["list"][0]
        return {
            "bid": float(t["bid1Price"]),
            "ask": float(t["ask1Price"]),
            "price": float(t["lastPrice"]),
            "funding_rate": float(t.get("fundingRate", 0)),
        }
    except Exception:
        return None


def scan_futures_futures(log_to_file=True):
    results = []
    threshold = 0.10

    print(f"[scanner_ff] Scanning {len(ASSETS)} assets across 3 futures exchanges...")

    for ac in ASSETS:
        asset = ac["asset"]
        prices: Dict[str, Dict[str, float]] = {}

        if ac.get("binance"):
            d = _fetch_binance_futures(ac["binance"])
            if d and d.get("bid", 0) > 0:
                prices["binance"] = d

        if ac.get("okx"):
            d = _fetch_okx_futures(ac["okx"])
            if d and d.get("bid", 0) > 0:
                prices["okx"] = d

        if ac.get("bybit"):
            d = _fetch_bybit_futures(ac["bybit"])
            if d and d.get("bid", 0) > 0:
                prices["bybit"] = d

        if len(prices) < 2:
            continue

        # Find best long (lowest ask) and best short (highest bid)
        best_long_ex = None
        lowest_ask = float("inf")
        best_short_ex = None
        highest_bid = 0

        for ex, d in prices.items():
            if d["ask"] < lowest_ask:
                lowest_ask = d["ask"]
                best_long_ex = ex
            if d["bid"] > highest_bid:
                highest_bid = d["bid"]
                best_short_ex = ex

        if not best_long_ex or not best_short_ex or best_long_ex == best_short_ex:
            continue

        spread_pct = ((highest_bid - lowest_ask) / lowest_ask) * 100
        total_fees = FEES.get(best_long_ex, 0.05) + FEES.get(best_short_ex, 0.05)
        edge_net = spread_pct - total_fees

        # Funding rate differential (annualized)
        fr_long = prices[best_long_ex].get("funding_rate", 0)
        fr_short = prices[best_short_ex].get("funding_rate", 0)
        funding_diff_8h = fr_short - fr_long
        funding_annualized = funding_diff_8h * 3 * 365 * 100

        if spread_pct < threshold:
            continue

        opp = {
            "opp_id": f"OPP-K-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "K",
            "scanner_id": SCANNER_ID,
            "asset": asset,
            "long_exchange": best_long_ex,
            "short_exchange": best_short_ex,
            "long_price": round(lowest_ask, 6),
            "short_price": round(highest_bid, 6),
            "spread_pct": round(spread_pct, 4),
            "total_fees_pct": round(total_fees, 4),
            "edge_net": round(edge_net, 4),
            "funding_rate_long": round(fr_long * 100, 6),
            "funding_rate_short": round(fr_short * 100, 6),
            "funding_diff_annualized_pct": round(funding_annualized, 2),
            "viable": edge_net > 0,
            "observe_only": True,
        }

        results.append(opp)
        if log_to_file:
            _append_to_log(opp)

        print(
            f"  [scanner_ff] {asset}: Long@{best_long_ex} ${lowest_ask:,.2f} | "
            f"Short@{best_short_ex} ${highest_bid:,.2f} | "
            f"Edge: {edge_net:+.4f}% | Funding diff: {funding_annualized:+.1f}% APY"
        )

    print(f"[scanner_ff] Done: {len(results)} opportunities")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Futures vs Futures Scanner (Type K)")
    print("=" * 70)
    results = scan_futures_futures()
    print(f"\n✓ {len(results)} opportunities detected")
