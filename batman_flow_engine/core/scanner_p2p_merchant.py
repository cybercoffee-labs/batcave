"""
Scanner G: P2P Merchant Spread Scanner

PURPOSE: Find buy/sell spread on Binance P2P for merchant strategy.
         Strategy: Post BUY ad at X, SELL ad at Y, earn the spread.

DATA SOURCE: Binance P2P API
  POST https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search

OUTPUT: storage/logs/opportunities.jsonl

FIELDS:
  - type: "G"
  - scanner_id: "G-P2P-MERCHANT"
"""

import json
import uuid
import yaml
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

SCANNER_ID = "G-P2P-MERCHANT"
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

# Supported fiats for merchant strategy
FIATS = ["MXN", "ARS"]


def _load_threshold() -> float:
    """Load min_merchant_spread_G threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_merchant_spread_G", 0.5))
    except Exception:
        pass
    return 0.5  # Default 0.5%


def _append_to_log(opportunity: dict) -> bool:
    """Append opportunity to JSONL log file."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_p2p_merchant] Log error: {e}")
        return False


def _create_ssl_context() -> ssl.SSLContext:
    """Create SSL context for HTTPS requests."""
    ctx = ssl.create_default_context()
    return ctx


def fetch_p2p_ads(
    fiat: str,
    trade_type: str,
    asset: str = "USDT",
    rows: int = 5,
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch P2P ads from Binance.

    Args:
        fiat: Currency (MXN, ARS)
        trade_type: "BUY" or "SELL"
        asset: Crypto asset (USDT)
        rows: Number of ads to fetch

    Returns:
        List of ad dicts or None on error
    """
    payload = {
        "fiat": fiat,
        "page": 1,
        "rows": rows,
        "tradeType": trade_type,
        "asset": asset,
        "publisherType": None,
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; BatmanLab/1.0)",
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            BINANCE_P2P_URL,
            data=data,
            headers=headers,
            method="POST",
        )
        ctx = _create_ssl_context()

        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        ads = result.get("data", [])
        return ads

    except Exception as e:
        print(f"  [scanner_p2p_merchant] Error fetching {trade_type} ads for {fiat}: {e}")
        return None


def parse_ads(ads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse ad data from Binance P2P response.

    Args:
        ads: Raw ad list from Binance API

    Returns:
        List of parsed ad dicts with price, amount, etc.
    """
    parsed = []
    for ad in ads:
        adv = ad.get("adv", {})
        advertiser = ad.get("advertiser", {})

        price = float(adv.get("price", 0))
        trade_amount = float(adv.get("tradableQuantity", 0))
        min_amount = float(adv.get("minSingleTransAmount", 0))
        max_amount = float(adv.get("dynamicMaxSingleTransAmount", 0))

        parsed.append(
            {
                "price": price,
                "available_usdt": trade_amount,
                "min_order": min_amount,
                "max_order": max_amount,
                "nick_name": advertiser.get("nickName", ""),
                "monthly_orders": advertiser.get("monthOrderCount", 0),
                "completion_rate": float(advertiser.get("monthFinishRate", 0)) * 100,
            }
        )

    return parsed


def calculate_merchant_spread(
    buy_ads: List[Dict[str, Any]],
    sell_ads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Calculate merchant spread between best buy and sell ads.

    Merchant Strategy:
    - You post a BUY ad: users SELL USDT to you at your buy price
    - You post a SELL ad: users BUY USDT from you at your sell price
    - Your profit = sell_price - buy_price

    Args:
        buy_ads: Parsed buy ads (you buy from them)
        sell_ads: Parsed sell ads (they sell to you = you sell to them)

    Returns:
        Dict with spread analysis
    """
    if not buy_ads or not sell_ads:
        return {
            "status": "insufficient_data",
            "error": "Missing buy or sell ads",
        }

    # Best buy = lowest price (you want to buy cheap)
    best_buy = min(buy_ads, key=lambda x: x["price"])
    # Best sell = highest price (you want to sell expensive)
    best_sell = max(sell_ads, key=lambda x: x["price"])

    buy_price = best_buy["price"]
    sell_price = best_sell["price"]

    if buy_price <= 0:
        return {
            "status": "invalid_price",
            "error": "Buy price is zero or negative",
        }

    merchant_spread = sell_price - buy_price
    merchant_spread_pct = (merchant_spread / buy_price) * 100

    # Calculate depth (total available USDT on both sides)
    depth_buy = sum(ad["available_usdt"] for ad in buy_ads)
    depth_sell = sum(ad["available_usdt"] for ad in sell_ads)

    return {
        "status": "ok",
        "best_buy_price": buy_price,
        "best_sell_price": sell_price,
        "merchant_spread": round(merchant_spread, 4),
        "merchant_spread_pct": round(merchant_spread_pct, 4),
        "num_buy_ads": len(buy_ads),
        "num_sell_ads": len(sell_ads),
        "depth_buy_usd": round(depth_buy, 2),
        "depth_sell_usd": round(depth_sell, 2),
    }


def analyze_fiat(fiat: str) -> Dict[str, Any]:
    """
    Analyze merchant spread for a specific fiat currency.

    Args:
        fiat: Currency code (MXN, ARS)

    Returns:
        Analysis result dict
    """
    # Fetch BUY ads (people wanting to buy USDT = you sell to them)
    # Actually for merchant: you BUY from sell ads, you SELL to buy ads
    # tradeType=BUY: ads from people who want to BUY USDT from you
    # tradeType=SELL: ads from people who want to SELL USDT to you

    buy_ads_raw = fetch_p2p_ads(fiat, "SELL", rows=5)  # You BUY from these
    sell_ads_raw = fetch_p2p_ads(fiat, "BUY", rows=5)  # You SELL to these

    if buy_ads_raw is None or sell_ads_raw is None:
        return {
            "fiat": fiat,
            "status": "fetch_error",
            "error": "Failed to fetch ads",
        }

    buy_ads = parse_ads(buy_ads_raw)
    sell_ads = parse_ads(sell_ads_raw)

    result = calculate_merchant_spread(buy_ads, sell_ads)
    result["fiat"] = fiat

    return result


def scan_merchant_spread(log_to_file: bool = True) -> List[Dict[str, Any]]:
    """
    Scan P2P markets for merchant spread opportunities.

    Args:
        log_to_file: Whether to log opportunities to JSONL

    Returns:
        List of opportunity dicts
    """
    threshold = _load_threshold()
    print(f"[scanner_p2p_merchant] Scanning {len(FIATS)} fiats (threshold: {threshold:.2f}%)...")

    results = []

    for fiat in FIATS:
        analysis = analyze_fiat(fiat)

        if analysis.get("status") != "ok":
            print(f"  [scanner_p2p_merchant] {fiat}: {analysis.get('error', 'No data')}")
            continue

        spread_pct = analysis["merchant_spread_pct"]
        viable = spread_pct >= threshold

        print(
            f"  [scanner_p2p_merchant] {fiat}: Spread {spread_pct:+.2f}% | "
            f"Buy {analysis['best_buy_price']:.2f} → Sell {analysis['best_sell_price']:.2f}"
        )

        if spread_pct >= threshold:
            opp = {
                "opp_id": f"OPP-G-{uuid.uuid4().hex[:10].upper()}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "G",
                "scanner_id": SCANNER_ID,
                "fiat": fiat,
                "best_buy_price": analysis["best_buy_price"],
                "best_sell_price": analysis["best_sell_price"],
                "merchant_spread_pct": spread_pct,
                "num_buy_ads": analysis["num_buy_ads"],
                "num_sell_ads": analysis["num_sell_ads"],
                "depth_buy_usd": analysis["depth_buy_usd"],
                "depth_sell_usd": analysis["depth_sell_usd"],
                "viable": viable,
                "observe_only": True,
            }

            results.append(opp)

            if log_to_file:
                _append_to_log(opp)
                print(f"  [scanner_p2p_merchant] ✓ Opportunity logged for {fiat}")

    print(f"[scanner_p2p_merchant] Scan complete: {len(results)} opportunities found")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("P2P Merchant Spread Scanner (Type G)")
    print("=" * 70)
    results = scan_merchant_spread()
    print(f"\n✓ {len(results)} opportunities detected")
