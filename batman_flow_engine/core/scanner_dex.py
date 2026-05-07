"""
Scanner J: DEX vs CEX Arbitrage Scanner

PURPOSE: Compare DEX prices vs CEX prices for the same asset.
         When a token is cheaper on DEX, buy there and sell on CEX (or vice versa).

DEX SOURCES:
  - DexScreener API (aggregates Uniswap, PancakeSwap, Raydium, etc.)
  - Jupiter API (Solana DEX aggregator)

CEX SOURCES: Uses Scanner D's price fetchers (Binance, OKX, Bybit)

ASSETS: Top tokens that trade on both DEX and CEX

OUTPUT: storage/logs/opportunities.jsonl
FIELDS: type: "J", scanner_id: "J-DEX-CEX"

NOTE: DEX trades have gas costs. We estimate these and subtract from edge.
"""

import json
import time
import uuid
import urllib.request
import ssl
from datetime import datetime, timezone
from pathlib import Path

SCANNER_ID = "J-DEX-CEX"
TIMEOUT = 12
RETRIES = 2
USER_AGENT = "batman-flow-engine/1.0"
MIN_EDGE_PCT = 0.30  # Minimum edge after fees

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

TOKENS = [
    {"asset": "ETH", "chain": "ethereum", "cex_symbol_binance": "ETHUSDT"},
    {"asset": "SOL", "chain": "solana", "cex_symbol_binance": "SOLUSDT"},
    {"asset": "ARB", "chain": "arbitrum", "cex_symbol_binance": "ARBUSDT"},
    {"asset": "OP", "chain": "optimism", "cex_symbol_binance": "OPUSDT"},
    {"asset": "AVAX", "chain": "avalanche", "cex_symbol_binance": "AVAXUSDT"},
    {"asset": "LINK", "chain": "ethereum", "cex_symbol_binance": "LINKUSDT"},
    {"asset": "UNI", "chain": "ethereum", "cex_symbol_binance": "UNIUSDT"},
    {"asset": "DOGE", "chain": "ethereum", "cex_symbol_binance": "DOGEUSDT"},
    {"asset": "MATIC", "chain": "polygon", "cex_symbol_binance": "MATICUSDT"},
    {"asset": "NEAR", "chain": "near", "cex_symbol_binance": "NEARUSDT"},
]

GAS_COSTS = {
    "ethereum": 8.0,
    "arbitrum": 0.30,
    "optimism": 0.30,
    "polygon": 0.05,
    "avalanche": 0.50,
    "solana": 0.01,
    "bsc": 0.20,
    "near": 0.01,
}

CEX_FEE_PCT = 0.10
DEX_FEE_PCT = 0.30


def _fetch_json(url, params=None):
    if params:
        url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            if attempt == RETRIES - 1:
                return None
            time.sleep(1)
    return None


def _append_to_log(opp):
    try:
        # Audit Section C #9: stamp cycle_id from process-global context if absent.
        from core.cycle_context import stamp_cycle_id

        stamp_cycle_id(opp)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(opp) + "\n")
        return True
    except Exception:
        return False


def fetch_dexscreener_price(asset, chain):
    """Fetch price from DexScreener API."""
    data = _fetch_json("https://api.dexscreener.com/latest/dex/search", {"q": f"{asset} USDT"})
    if not data or not data.get("pairs"):
        data = _fetch_json("https://api.dexscreener.com/latest/dex/search", {"q": f"{asset} USDC"})

    if not data or not data.get("pairs"):
        return None

    best_pair = None
    for pair in data["pairs"]:
        if pair.get("chainId", "").lower() == chain.lower():
            if pair.get("baseToken", {}).get("symbol", "").upper() == asset.upper():
                if best_pair is None or float(pair.get("volume", {}).get("h24", 0)) > float(
                    best_pair.get("volume", {}).get("h24", 0)
                ):
                    best_pair = pair

    if not best_pair:
        for pair in data["pairs"][:5]:
            if pair.get("baseToken", {}).get("symbol", "").upper() == asset.upper():
                best_pair = pair
                break

    if not best_pair:
        return None

    try:
        return {
            "price": float(best_pair["priceUsd"]),
            "dex_name": best_pair.get("dexId", "unknown"),
            "chain": best_pair.get("chainId", chain),
            "pair_address": best_pair.get("pairAddress", ""),
            "volume_24h": float(best_pair.get("volume", {}).get("h24", 0)),
            "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0)),
            "price_change_24h": float(best_pair.get("priceChange", {}).get("h24", 0)),
        }
    except Exception:
        return None


def fetch_cex_price(symbol):
    """Fetch CEX price from Binance."""
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


def scan_dex_cex(log_to_file=True):
    results = []

    print(f"[scanner_dex] Scanning {len(TOKENS)} tokens DEX vs CEX (min edge: {MIN_EDGE_PCT}%)...")

    for token in TOKENS:
        asset = token["asset"]
        chain = token["chain"]

        dex = fetch_dexscreener_price(asset, chain)
        if not dex:
            print(f"  [scanner_dex] {asset}: No DEX data found")
            continue

        cex = fetch_cex_price(token["cex_symbol_binance"])
        if not cex:
            print(f"  [scanner_dex] {asset}: No CEX data")
            continue

        dex_price = dex["price"]
        cex_price = cex["price"]

        if dex_price <= 0 or cex_price <= 0:
            continue

        if dex_price < cex_price:
            buy_venue = f"DEX ({dex['dex_name']})"
            sell_venue = "Binance"
            buy_price = dex_price
            sell_price = cex["bid"]
            direction = "dex_to_cex"
        else:
            buy_venue = "Binance"
            sell_venue = f"DEX ({dex['dex_name']})"
            buy_price = cex["ask"]
            sell_price = dex_price
            direction = "cex_to_dex"

        gross_spread = ((sell_price - buy_price) / buy_price) * 100

        gas_usd = GAS_COSTS.get(dex.get("chain", chain), 5.0)
        gas_pct_100usd = (gas_usd / 100) * 100
        total_fees = CEX_FEE_PCT + DEX_FEE_PCT + gas_pct_100usd

        edge_net = gross_spread - total_fees
        viable = edge_net > 0

        opp = {
            "opp_id": f"OPP-J-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "J",
            "scanner_id": SCANNER_ID,
            "asset": asset,
            "chain": dex.get("chain", chain),
            "direction": direction,
            "buy_venue": buy_venue,
            "sell_venue": sell_venue,
            "dex_price": round(dex_price, 6),
            "cex_price": round(cex_price, 6),
            "dex_name": dex["dex_name"],
            "buy_price": round(buy_price, 6),
            "sell_price": round(sell_price, 6),
            "gross_spread_pct": round(gross_spread, 4),
            "gas_cost_usd": gas_usd,
            "gas_pct_of_100usd": round(gas_pct_100usd, 2),
            "total_fees_pct": round(total_fees, 2),
            "edge_net": round(edge_net, 4),
            "viable": viable,
            "dex_volume_24h": round(dex.get("volume_24h", 0), 0),
            "dex_liquidity_usd": round(dex.get("liquidity_usd", 0), 0),
            "observe_only": True,
        }

        results.append(opp)
        if log_to_file and viable:
            _append_to_log(opp)

        status = "✅" if viable else "⚪"
        print(
            f"  [scanner_dex] {status} {asset} ({chain}): DEX ${dex_price:.4f} vs CEX ${cex_price:.4f} | Edge: {edge_net:+.3f}% | Gas: ${gas_usd}"
        )

        time.sleep(0.5)

    viable_count = sum(1 for r in results if r["viable"])
    print(f"[scanner_dex] Done: {len(results)} analyzed, {viable_count} viable")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("DEX vs CEX Scanner (Type J)")
    print("=" * 70)
    results = scan_dex_cex()
    print(f"\n✓ {len(results)} routes analyzed")
