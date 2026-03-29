"""
Scanner I: Cross-Platform MXN Arbitrage Scanner

PURPOSE: Compare USDT/MXN prices across ALL available platforms to find
         cross-platform arbitrage. This is the CORE scanner for Erick's
         P2P trading operation.

COMPARES:
  - Binance P2P (buy/sell ads for USDT/MXN) — VERIFIED WORKING
  - Bitso Spot (order book for usdt_mxn) — VERIFIED WORKING
  - OKX P2P (buy/sell ads for USDT/MXN) — best effort, API may be unreliable
  - Bybit P2P (buy/sell ads for USDT/MXN) — best effort, API may be unreliable

SANITY CHECK: All prices are validated against Bitso spot as reference.
              Any price >3% away from Bitso is flagged as UNRELIABLE and excluded.

OUTPUT: storage/logs/opportunities.jsonl
FIELDS:
  - type: "I"
  - scanner_id: "I-CROSS-PLATFORM-MXN"
"""

import json
import ssl
import time
import uuid
import urllib.request
import urllib.error
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

SCANNER_ID = "I-CROSS-PLATFORM-MXN"
TIMEOUT = 15
RETRIES = 3
USER_AGENT = "batman-flow-engine/1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

# Max deviation from reference price (Bitso spot) before marking UNRELIABLE
MAX_DEVIATION_PCT = 3.0

# Estimated fees per platform (%)
FEES = {
    "binance_p2p": 0.00,  # Binance P2P: 0% maker fee
    "bitso_spot": 0.50,  # Bitso: 0.5% taker (can be lower with volume)
    "okx_p2p": 0.00,  # OKX P2P: 0% maker fee
    "bybit_p2p": 0.00,  # Bybit P2P: 0% maker fee
}

# Transfer/withdrawal fees (USDT via TRC20 in USD equivalent)
TRANSFER_FEES = {
    "binance_to_bitso": 1.0,
    "bitso_to_binance": 1.0,
    "binance_to_okx": 1.0,
    "okx_to_binance": 0.0,
    "binance_to_bybit": 1.0,
    "bybit_to_binance": 1.0,
    "bitso_to_okx": 1.0,
    "okx_to_bitso": 0.0,
    "bitso_to_bybit": 1.0,
    "bybit_to_bitso": 1.0,
    "okx_to_bybit": 0.0,
    "bybit_to_okx": 1.0,
    "same_platform": 0.0,
}


def _load_threshold() -> float:
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_edge_pct_I", 0.20))
    except Exception:
        pass
    return 0.20


def _append_to_log(opportunity: dict) -> bool:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_cross_mxn] Log error: {e}")
        return False


def _fetch_json(
    url: str,
    params: Optional[Dict] = None,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict] = None,
) -> Optional[Dict]:
    if params and method == "GET":
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if attempt == RETRIES - 1:
                return None
            time.sleep(1.5**attempt)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Platform Price Fetchers
# "buy"  = price at which YOU can buy USDT (lowest ask / cheapest seller)
# "sell" = price at which YOU can sell USDT (highest bid / best buyer)
# ─────────────────────────────────────────────────────────────────────────────


def fetch_binance_p2p_mxn() -> Dict[str, Any]:
    """Fetch Binance P2P USDT/MXN prices. VERIFIED WORKING."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    hdrs = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    result = {"platform": "binance_p2p", "status": "error"}

    try:
        # SELL ads = people selling USDT = you BUY from them
        payload_sell = json.dumps(
            {
                "fiat": "MXN",
                "page": 1,
                "rows": 5,
                "tradeType": "SELL",
                "asset": "USDT",
                "publisherType": None,
            }
        ).encode()
        data_sell = _fetch_json(url, method="POST", body=payload_sell, headers=hdrs)

        # BUY ads = people buying USDT = you SELL to them
        payload_buy = json.dumps(
            {
                "fiat": "MXN",
                "page": 1,
                "rows": 5,
                "tradeType": "BUY",
                "asset": "USDT",
                "publisherType": None,
            }
        ).encode()
        data_buy = _fetch_json(url, method="POST", body=payload_buy, headers=hdrs)

        sell_ads = data_sell.get("data", []) if data_sell else []
        buy_ads = data_buy.get("data", []) if data_buy else []

        prices_sell = [float(a["adv"]["price"]) for a in sell_ads if a.get("adv", {}).get("price")]
        prices_buy = [float(a["adv"]["price"]) for a in buy_ads if a.get("adv", {}).get("price")]

        buy_price = min(prices_sell) if prices_sell else 0
        sell_price = max(prices_buy) if prices_buy else 0

        depth_buy = sum(float(a["adv"].get("tradableQuantity", 0)) for a in sell_ads)
        depth_sell = sum(float(a["adv"].get("tradableQuantity", 0)) for a in buy_ads)

        if buy_price > 0 and sell_price > 0:
            result.update(
                {
                    "buy": buy_price,
                    "sell": sell_price,
                    "depth_buy_usd": round(depth_buy, 2),
                    "depth_sell_usd": round(depth_sell, 2),
                    "num_ads": len(sell_ads) + len(buy_ads),
                    "status": "ok",
                    "reliable": True,
                }
            )
    except Exception as e:
        result["error"] = str(e)

    return result


def fetch_bitso_spot_mxn() -> Dict[str, Any]:
    """Fetch Bitso spot USDT/MXN. VERIFIED WORKING."""
    result = {"platform": "bitso_spot", "status": "error"}

    data = _fetch_json("https://api.bitso.com/v3/ticker/", {"book": "usdt_mxn"})

    if not data or not data.get("success"):
        result["error"] = "Bitso API error"
        return result

    try:
        payload = data["payload"]
        result.update(
            {
                "buy": float(payload["ask"]),
                "sell": float(payload["bid"]),
                "last": float(payload["last"]),
                "volume_24h": float(payload.get("volume", 0)),
                "status": "ok",
                "reliable": True,
            }
        )
    except Exception as e:
        result["error"] = str(e)

    return result


def fetch_okx_p2p_mxn() -> Dict[str, Any]:
    """
    Fetch OKX P2P USDT/MXN prices.
    NOTE: OKX P2P API may be unreliable — results validated against reference.
    """
    url = "https://www.okx.com/v3/c2c/tradingOrders/books"
    result = {"platform": "okx_p2p", "status": "error", "reliable": False}

    try:
        params_sell = {
            "quoteCurrency": "mxn",
            "baseCurrency": "usdt",
            "side": "sell",
            "paymentMethod": "all",
            "userType": "all",
            "showTrade": "false",
            "showFollow": "false",
            "showAlreadyTraded": "false",
            "isAbleFilter": "false",
            "receivingAds": "false",
            "urlId": "0",
        }
        data_sell = _fetch_json(url, params=params_sell)

        params_buy = params_sell.copy()
        params_buy["side"] = "buy"
        data_buy = _fetch_json(url, params=params_buy)

        sell_prices = []
        buy_prices = []

        # OKX API response format varies — try multiple paths
        if data_sell and data_sell.get("code") == 0:
            data_payload = data_sell.get("data", {})
            if isinstance(data_payload, dict):
                ads = data_payload.get("sell", data_payload.get("buy", []))
            elif isinstance(data_payload, list):
                ads = data_payload
            else:
                ads = []
            for ad in ads[:10]:
                p = ad.get("price") or ad.get("unitPrice")
                if p:
                    sell_prices.append(float(p))

        if data_buy and data_buy.get("code") == 0:
            data_payload = data_buy.get("data", {})
            if isinstance(data_payload, dict):
                ads = data_payload.get("buy", data_payload.get("sell", []))
            elif isinstance(data_payload, list):
                ads = data_payload
            else:
                ads = []
            for ad in ads[:10]:
                p = ad.get("price") or ad.get("unitPrice")
                if p:
                    buy_prices.append(float(p))

        if sell_prices and buy_prices:
            result.update(
                {
                    "buy": min(sell_prices),
                    "sell": max(buy_prices),
                    "num_sell_ads": len(sell_prices),
                    "num_buy_ads": len(buy_prices),
                    "status": "ok",
                    "reliable": True,
                }
            )
        elif sell_prices:
            result.update({"buy": min(sell_prices), "sell": 0, "status": "partial"})
        elif buy_prices:
            result.update({"buy": 0, "sell": max(buy_prices), "status": "partial"})
        else:
            result["error"] = "No MXN ads found on OKX P2P"

    except Exception as e:
        result["error"] = str(e)

    return result


def fetch_bybit_p2p_mxn() -> Dict[str, Any]:
    """
    Fetch Bybit P2P USDT/MXN prices.
    NOTE: Bybit P2P public API is UNRELIABLE — returns wrong prices.
    Results validated against reference price.
    """
    url = "https://api2.bybit.com/fiat/otc/item/online"
    hdrs = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    result = {"platform": "bybit_p2p", "status": "error", "reliable": False}

    try:
        # side=1 = sellers (you buy), side=0 = buyers (you sell)
        payload_sell = json.dumps(
            {
                "tokenId": "USDT",
                "currencyId": "MXN",
                "side": "1",
                "size": "10",
                "page": "1",
            }
        ).encode()
        data_sell = _fetch_json(url, method="POST", body=payload_sell, headers=hdrs)

        payload_buy = json.dumps(
            {
                "tokenId": "USDT",
                "currencyId": "MXN",
                "side": "0",
                "size": "10",
                "page": "1",
            }
        ).encode()
        data_buy = _fetch_json(url, method="POST", body=payload_buy, headers=hdrs)

        sell_prices = []
        buy_prices = []

        if data_sell and data_sell.get("ret_code") == 0:
            items = data_sell.get("result", {}).get("items", [])
            for item in items[:10]:
                p = item.get("price")
                if p:
                    sell_prices.append(float(p))

        if data_buy and data_buy.get("ret_code") == 0:
            items = data_buy.get("result", {}).get("items", [])
            for item in items[:10]:
                p = item.get("price")
                if p:
                    buy_prices.append(float(p))

        if sell_prices and buy_prices:
            result.update(
                {
                    "buy": min(sell_prices),
                    "sell": max(buy_prices),
                    "num_sell_ads": len(sell_prices),
                    "num_buy_ads": len(buy_prices),
                    "status": "ok",
                    "reliable": True,
                }
            )
        elif sell_prices:
            result.update({"buy": min(sell_prices), "sell": 0, "status": "partial"})
        elif buy_prices:
            result.update({"buy": 0, "sell": max(buy_prices), "status": "partial"})
        else:
            result["error"] = "No MXN ads found on Bybit P2P"

    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Sanity Check
# ─────────────────────────────────────────────────────────────────────────────


def _sanity_check(
    prices: Dict[str, Dict[str, Any]], reference_platform: str = "bitso_spot"
) -> Dict[str, Dict[str, Any]]:
    """
    Validate all prices against a reference (Bitso spot).
    Any price >MAX_DEVIATION_PCT away from reference is marked unreliable.
    """
    ref = prices.get(reference_platform, {})
    ref_price = ref.get("last") or ref.get("buy", 0)

    if ref_price <= 0:
        # No reference — try Binance P2P as fallback
        ref = prices.get("binance_p2p", {})
        ref_price = (ref.get("buy", 0) + ref.get("sell", 0)) / 2 if ref.get("buy") else 0

    if ref_price <= 0:
        print("  [scanner_cross_mxn] ⚠️  No reference price available for sanity check")
        return prices

    print(f"  [scanner_cross_mxn] Reference price (Bitso): ${ref_price:.4f} MXN")

    for platform, data in prices.items():
        if data.get("status") not in ("ok", "partial"):
            continue

        for field in ("buy", "sell"):
            p = data.get(field, 0)
            if p <= 0:
                continue

            deviation_pct = abs((p - ref_price) / ref_price) * 100

            if deviation_pct > MAX_DEVIATION_PCT:
                data["reliable"] = False
                data[f"{field}_deviation_pct"] = round(deviation_pct, 2)
                print(
                    f"  [scanner_cross_mxn] ⚠️  {platform} {field}=${p:.4f} is "
                    f"{deviation_pct:.1f}% away from reference — UNRELIABLE"
                )

    return prices


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Platform Comparison
# ─────────────────────────────────────────────────────────────────────────────


def find_cross_platform_opportunities(
    prices: Dict[str, Dict[str, Any]],
    threshold: float = 0.20,
    trade_amount_usd: float = 100.0,
) -> List[Dict[str, Any]]:
    """Compare all RELIABLE platform prices and find arbitrage routes."""
    opportunities = []

    # Only use reliable platforms
    active = {}
    for k, v in prices.items():
        if v.get("status") in ("ok", "partial") and v.get("reliable", False):
            if v.get("buy", 0) > 0:
                active[k] = v

    platforms = list(active.keys())

    for i, buy_platform in enumerate(platforms):
        for j, sell_platform in enumerate(platforms):
            if i == j:
                continue

            buy_data = active[buy_platform]
            sell_data = active[sell_platform]

            buy_price = buy_data.get("buy", 0)
            sell_price = sell_data.get("sell", 0)

            if buy_price <= 0 or sell_price <= 0:
                continue

            gross_spread_pct = ((sell_price - buy_price) / buy_price) * 100

            buy_fee_pct = FEES.get(buy_platform, 0.10)
            sell_fee_pct = FEES.get(sell_platform, 0.10)

            # Transfer fee
            buy_base = buy_platform.split("_")[0]
            sell_base = sell_platform.split("_")[0]
            if buy_base == sell_base:
                transfer_usd = 0
            else:
                transfer_key = f"{buy_base}_to_{sell_base}"
                transfer_usd = TRANSFER_FEES.get(transfer_key, 1.0)
            transfer_fee_pct = (transfer_usd / trade_amount_usd) * 100

            total_friction_pct = buy_fee_pct + sell_fee_pct + transfer_fee_pct
            edge_net = gross_spread_pct - total_friction_pct
            viable = edge_net >= threshold

            opp = {
                "buy_platform": buy_platform,
                "sell_platform": sell_platform,
                "buy_price_mxn": round(buy_price, 4),
                "sell_price_mxn": round(sell_price, 4),
                "gross_spread_pct": round(gross_spread_pct, 4),
                "buy_fee_pct": buy_fee_pct,
                "sell_fee_pct": sell_fee_pct,
                "transfer_fee_pct": round(transfer_fee_pct, 4),
                "total_friction_pct": round(total_friction_pct, 4),
                "edge_net": round(edge_net, 4),
                "viable": viable,
                "estimated_pnl_usd": round(trade_amount_usd * (edge_net / 100), 4),
            }
            opportunities.append(opp)

    opportunities.sort(key=lambda x: x["edge_net"], reverse=True)
    return opportunities


def scan_cross_platform_mxn(log_to_file: bool = True) -> List[Dict[str, Any]]:
    """Main scanner function."""
    threshold = _load_threshold()
    print(f"[scanner_cross_mxn] Scanning USDT/MXN across all platforms (threshold: {threshold:.2f}%)...")

    prices = {}

    # Fetch from all platforms — Bitso FIRST (it's our reference)
    print("  [scanner_cross_mxn] Fetching Bitso Spot (reference)...")
    prices["bitso_spot"] = fetch_bitso_spot_mxn()

    print("  [scanner_cross_mxn] Fetching Binance P2P...")
    prices["binance_p2p"] = fetch_binance_p2p_mxn()

    print("  [scanner_cross_mxn] Fetching OKX P2P...")
    prices["okx_p2p"] = fetch_okx_p2p_mxn()

    print("  [scanner_cross_mxn] Fetching Bybit P2P...")
    prices["bybit_p2p"] = fetch_bybit_p2p_mxn()

    # Sanity check all prices against Bitso
    prices = _sanity_check(prices)

    # Print price summary
    print(f"\n  {'Platform':<18} {'Buy USDT @':<14} {'Sell USDT @':<14} {'Status':<10} {'Reliable'}")
    print(f"  {'─'*70}")
    for name, data in prices.items():
        status = data.get("status", "error")
        reliable = "✅" if data.get("reliable") else "❌"
        if status in ("ok", "partial"):
            buy_p = f"${data.get('buy', 0):.4f}" if data.get("buy", 0) > 0 else "N/A"
            sell_p = f"${data.get('sell', 0):.4f}" if data.get("sell", 0) > 0 else "N/A"
            print(f"  {name:<18} {buy_p:<14} {sell_p:<14} {status:<10} {reliable}")
        else:
            print(f"  {name:<18} {'--':<14} {'--':<14} {data.get('error', 'error')[:25]:<10} {reliable}")

    # Find opportunities (only reliable platforms)
    opportunities = find_cross_platform_opportunities(prices, threshold)

    results = []
    for opp in opportunities:
        full_opp = {
            "opp_id": f"OPP-I-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "I",
            "scanner_id": SCANNER_ID,
            "asset": "USDT",
            "fiat": "MXN",
            "market": "MXN",
            **opp,
            "spot_price": opp["buy_price_mxn"],
            "observe_only": True,
        }
        results.append(full_opp)
        if log_to_file and opp["viable"]:
            _append_to_log(full_opp)

    viable = [o for o in opportunities if o["viable"]]
    print(f"\n  [scanner_cross_mxn] Routes analyzed: {len(opportunities)}")
    print(f"  [scanner_cross_mxn] Viable routes (reliable only): {len(viable)}")

    if viable:
        print("\n  ⭐ TOP ROUTES:")
        for i, route in enumerate(viable[:5]):
            print(
                f"    {i+1}. Buy@{route['buy_platform']} ${route['buy_price_mxn']:.2f} → "
                f"Sell@{route['sell_platform']} ${route['sell_price_mxn']:.2f} | "
                f"Edge: {route['edge_net']:+.3f}% | "
                f"P&L: ${route['estimated_pnl_usd']:+.2f}/trade"
            )
    else:
        print("\n  No viable cross-platform routes found right now.")
        print("  (This is normal — cross-platform arb windows are brief)")

    print(f"\n[scanner_cross_mxn] Scan complete: {len(results)} routes, {len(viable)} viable")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Cross-Platform MXN Scanner (Type I)")
    print("Comparing USDT/MXN: Binance P2P vs Bitso vs OKX P2P vs Bybit P2P")
    print("=" * 70)
    results = scan_cross_platform_mxn()
    print(f"\n✓ {len(results)} routes analyzed")
