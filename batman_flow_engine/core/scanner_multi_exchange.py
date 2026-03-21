"""
Scanner D: Multi-Exchange Price Scanner (EXPANDED)

PURPOSE: Compare 20 assets across Binance, OKX, Bybit, KuCoin, MEXC simultaneously.
         Detect cross-exchange arbitrage when spread > threshold.

ASSETS: BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK, DOT, MATIC,
        UNI, ATOM, NEAR, APT, ARB, OP, FIL, LTC, BCH, XLM

EXCHANGES: Binance, OKX, Bybit, KuCoin, MEXC (5 exchanges)

OUTPUT: storage/logs/opportunities.jsonl
FIELDS: type: "D", scanner_id: "D-MULTI-EXCHANGE"
"""

import json
import time
import uuid
import urllib.request
import urllib.error
import yaml
from datetime import datetime, timezone
from pathlib import Path

SCANNER_ID = "D-MULTI-EXCHANGE"
TIMEOUT = 10
RETRIES = 2
USER_AGENT = "batman-flow-engine/1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

# 20 assets with exchange-specific symbol formats
ASSETS = [
    {
        "asset": "BTC",
        "binance": "BTCUSDT",
        "okx": "BTC-USDT",
        "bybit": "BTCUSDT",
        "kucoin": "BTC-USDT",
        "mexc": "BTCUSDT",
    },
    {
        "asset": "ETH",
        "binance": "ETHUSDT",
        "okx": "ETH-USDT",
        "bybit": "ETHUSDT",
        "kucoin": "ETH-USDT",
        "mexc": "ETHUSDT",
    },
    {
        "asset": "SOL",
        "binance": "SOLUSDT",
        "okx": "SOL-USDT",
        "bybit": "SOLUSDT",
        "kucoin": "SOL-USDT",
        "mexc": "SOLUSDT",
    },
    {
        "asset": "XRP",
        "binance": "XRPUSDT",
        "okx": "XRP-USDT",
        "bybit": "XRPUSDT",
        "kucoin": "XRP-USDT",
        "mexc": "XRPUSDT",
    },
    {
        "asset": "DOGE",
        "binance": "DOGEUSDT",
        "okx": "DOGE-USDT",
        "bybit": "DOGEUSDT",
        "kucoin": "DOGE-USDT",
        "mexc": "DOGEUSDT",
    },
    {
        "asset": "ADA",
        "binance": "ADAUSDT",
        "okx": "ADA-USDT",
        "bybit": "ADAUSDT",
        "kucoin": "ADA-USDT",
        "mexc": "ADAUSDT",
    },
    {
        "asset": "AVAX",
        "binance": "AVAXUSDT",
        "okx": "AVAX-USDT",
        "bybit": "AVAXUSDT",
        "kucoin": "AVAX-USDT",
        "mexc": "AVAXUSDT",
    },
    {
        "asset": "LINK",
        "binance": "LINKUSDT",
        "okx": "LINK-USDT",
        "bybit": "LINKUSDT",
        "kucoin": "LINK-USDT",
        "mexc": "LINKUSDT",
    },
    {
        "asset": "DOT",
        "binance": "DOTUSDT",
        "okx": "DOT-USDT",
        "bybit": "DOTUSDT",
        "kucoin": "DOT-USDT",
        "mexc": "DOTUSDT",
    },
    {
        "asset": "MATIC",
        "binance": "MATICUSDT",
        "okx": "MATIC-USDT",
        "bybit": "MATICUSDT",
        "kucoin": "MATIC-USDT",
        "mexc": "MATICUSDT",
    },
    {
        "asset": "UNI",
        "binance": "UNIUSDT",
        "okx": "UNI-USDT",
        "bybit": "UNIUSDT",
        "kucoin": "UNI-USDT",
        "mexc": "UNIUSDT",
    },
    {
        "asset": "ATOM",
        "binance": "ATOMUSDT",
        "okx": "ATOM-USDT",
        "bybit": "ATOMUSDT",
        "kucoin": "ATOM-USDT",
        "mexc": "ATOMUSDT",
    },
    {
        "asset": "NEAR",
        "binance": "NEARUSDT",
        "okx": "NEAR-USDT",
        "bybit": "NEARUSDT",
        "kucoin": "NEAR-USDT",
        "mexc": "NEARUSDT",
    },
    {
        "asset": "APT",
        "binance": "APTUSDT",
        "okx": "APT-USDT",
        "bybit": "APTUSDT",
        "kucoin": "APT-USDT",
        "mexc": "APTUSDT",
    },
    {
        "asset": "ARB",
        "binance": "ARBUSDT",
        "okx": "ARB-USDT",
        "bybit": "ARBUSDT",
        "kucoin": "ARB-USDT",
        "mexc": "ARBUSDT",
    },
    {"asset": "OP", "binance": "OPUSDT", "okx": "OP-USDT", "bybit": "OPUSDT", "kucoin": "OP-USDT", "mexc": "OPUSDT"},
    {
        "asset": "FIL",
        "binance": "FILUSDT",
        "okx": "FIL-USDT",
        "bybit": "FILUSDT",
        "kucoin": "FIL-USDT",
        "mexc": "FILUSDT",
    },
    {
        "asset": "LTC",
        "binance": "LTCUSDT",
        "okx": "LTC-USDT",
        "bybit": "LTCUSDT",
        "kucoin": "LTC-USDT",
        "mexc": "LTCUSDT",
    },
    {
        "asset": "BCH",
        "binance": "BCHUSDT",
        "okx": "BCH-USDT",
        "bybit": "BCHUSDT",
        "kucoin": "BCH-USDT",
        "mexc": "BCHUSDT",
    },
    {
        "asset": "XLM",
        "binance": "XLMUSDT",
        "okx": "XLM-USDT",
        "bybit": "XLMUSDT",
        "kucoin": "XLM-USDT",
        "mexc": "XLMUSDT",
    },
]

DEFAULT_FEES = {
    "binance": 0.10,
    "okx": 0.10,
    "bybit": 0.10,
    "kucoin": 0.10,
    "mexc": 0.10,
}


def _fetch_json(url, params=None):
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
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


def _load_threshold():
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_spread_pct_D", 0.08))
    except Exception:
        pass
    return 0.08


def _append_to_log(opp):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(opp) + "\n")
        return True
    except Exception:
        return False


def _fetch_binance_price(symbol):
    data = _fetch_json("https://api.binance.com/api/v3/ticker/bookTicker", {"symbol": symbol})
    if data:
        try:
            return {
                "bid": float(data["bidPrice"]),
                "ask": float(data["askPrice"]),
                "price": (float(data["bidPrice"]) + float(data["askPrice"])) / 2,
            }
        except Exception:
            pass
    return None


def _fetch_okx_price(inst_id):
    data = _fetch_json("https://www.okx.com/api/v5/market/ticker", {"instId": inst_id})
    if data and data.get("code") == "0":
        try:
            t = data["data"][0]
            return {"bid": float(t["bidPx"]), "ask": float(t["askPx"]), "price": float(t["last"])}
        except Exception:
            pass
    return None


def _fetch_bybit_price(symbol):
    data = _fetch_json("https://api.bybit.com/v5/market/tickers", {"category": "spot", "symbol": symbol})
    if data and data.get("retCode") == 0:
        try:
            t = data["result"]["list"][0]
            return {"bid": float(t["bid1Price"]), "ask": float(t["ask1Price"]), "price": float(t["lastPrice"])}
        except Exception:
            pass
    return None


def _fetch_kucoin_price(symbol):
    data = _fetch_json("https://api.kucoin.com/api/v1/market/orderbook/level1", {"symbol": symbol})
    if data and data.get("code") == "200000":
        try:
            d = data["data"]
            return {"bid": float(d["bestBid"]), "ask": float(d["bestAsk"]), "price": float(d["price"])}
        except Exception:
            pass
    return None


def _fetch_mexc_price(symbol):
    data = _fetch_json("https://api.mexc.com/api/v3/ticker/bookTicker", {"symbol": symbol})
    if data:
        try:
            return {
                "bid": float(data["bidPrice"]),
                "ask": float(data["askPrice"]),
                "price": (float(data["bidPrice"]) + float(data["askPrice"])) / 2,
            }
        except Exception:
            pass
    return None


def fetch_all_prices(asset_config):
    prices = {}
    fetchers = {
        "binance": (_fetch_binance_price, "binance"),
        "okx": (_fetch_okx_price, "okx"),
        "bybit": (_fetch_bybit_price, "bybit"),
        "kucoin": (_fetch_kucoin_price, "kucoin"),
        "mexc": (_fetch_mexc_price, "mexc"),
    }
    for exchange, (fetcher, key) in fetchers.items():
        symbol = asset_config.get(exchange)
        if symbol:
            try:
                data = fetcher(symbol)
                if data and data.get("bid", 0) > 0:
                    prices[exchange] = data
            except Exception:
                pass
    return prices


def find_arbitrage_opportunity(asset, prices, threshold=0.08):
    if len(prices) < 2:
        return None

    best_buy_exchange, lowest_ask = None, float("inf")
    best_sell_exchange, highest_bid = None, 0

    for exchange, data in prices.items():
        if data["ask"] < lowest_ask:
            lowest_ask, best_buy_exchange = data["ask"], exchange
        if data["bid"] > highest_bid:
            highest_bid, best_sell_exchange = data["bid"], exchange

    if not best_buy_exchange or not best_sell_exchange or lowest_ask <= 0:
        return None

    spread_pct = ((highest_bid - lowest_ask) / lowest_ask) * 100
    total_fees = DEFAULT_FEES.get(best_buy_exchange, 0.10) + DEFAULT_FEES.get(best_sell_exchange, 0.10)
    edge_net = spread_pct - total_fees

    if spread_pct < threshold:
        return None

    return {
        "asset": asset,
        "buy_exchange": best_buy_exchange,
        "sell_exchange": best_sell_exchange,
        "buy_price": round(lowest_ask, 6),
        "sell_price": round(highest_bid, 6),
        "spread_pct": round(spread_pct, 4),
        "estimated_fees_pct": round(total_fees, 2),
        "edge_net": round(edge_net, 4),
        "viable": edge_net > 0,
        "all_prices": {ex: round(p["price"], 4) for ex, p in prices.items()},
    }


def scan_multi_exchange(log_to_file=True):
    results = []
    threshold = _load_threshold()
    print(f"[scanner_multi] Scanning {len(ASSETS)} assets across 5 exchanges (threshold: {threshold:.2f}%)...")

    for asset_config in ASSETS:
        asset = asset_config["asset"]
        prices = fetch_all_prices(asset_config)

        if len(prices) < 2:
            continue

        opp = find_arbitrage_opportunity(asset, prices, threshold)

        if opp:
            full_opp = {
                "opp_id": f"OPP-D-{uuid.uuid4().hex[:10].upper()}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "D",
                "scanner_id": SCANNER_ID,
                **opp,
                "observe_only": True,
            }
            results.append(full_opp)
            if log_to_file:
                _append_to_log(full_opp)
            print(
                f"  [scanner_multi] {asset}: Buy@{opp['buy_exchange']} ${opp['buy_price']:,.4f} → Sell@{opp['sell_exchange']} ${opp['sell_price']:,.4f} | Edge: {opp['edge_net']:+.4f}%"
            )
        else:
            price_strs = [f"{ex}=${p['price']:,.4f}" for ex, p in prices.items()]
            print(f"  [scanner_multi] {asset}: {' | '.join(price_strs)} | Below threshold")

    print(f"[scanner_multi] Done: {len(results)} opportunities from {len(ASSETS)} assets")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print(f"Multi-Exchange Scanner (Type D) — {len(ASSETS)} assets × 5 exchanges")
    print("=" * 70)
    results = scan_multi_exchange()
    print(f"\n✓ {len(results)} opportunities detected")
