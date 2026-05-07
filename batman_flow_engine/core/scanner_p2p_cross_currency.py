"""
Scanner F: P2P Cross-Currency Premium Scanner

PURPOSE: Compare P2P premiums between MXN, ARS, COP, VES simultaneously.
         Detect cross-currency arbitrage opportunities when premium spread > threshold.

DATA SOURCES:
  - P2P prices: Binance P2P API (via p2p_latam.py)
  - FX rates: open.er-api.com (via p2p_latam.py)

OUTPUT: storage/logs/opportunities.jsonl

FIELDS:
  - type: "F"
  - scanner_id: "F-P2P-CROSS-CURRENCY"
"""

import json
import uuid
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
from itertools import combinations

# Import from existing p2p_latam module
from .p2p_latam import (
    get_fiat_spot_rates,
    get_p2p_price_binance,
)

SCANNER_ID = "F-P2P-CROSS-CURRENCY"
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

# Currencies to compare
CURRENCIES = ["MXN", "ARS", "COP", "VES"]

# Default cross-currency transfer costs
TRANSFER_COSTS = {
    ("MXN", "ARS"): 1.0,  # Estimated % cost to move value MXN -> ARS
    ("MXN", "COP"): 1.0,
    ("MXN", "VES"): 1.2,
    ("ARS", "COP"): 1.2,
    ("ARS", "VES"): 1.5,
    ("COP", "VES"): 1.3,
}


def _load_threshold() -> float:
    """Load min_cross_currency_F threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_cross_currency_F", 1.0))
    except Exception:
        pass
    return 1.0  # Default 1.0%


def _append_to_log(opportunity: dict) -> bool:
    """Append opportunity to JSONL log file."""
    try:
        # Audit Section C #9: stamp cycle_id from process-global context if absent.
        from core.cycle_context import stamp_cycle_id

        stamp_cycle_id(opportunity)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_cross_currency] Log error: {e}")
        return False


def _get_transfer_cost(fiat1: str, fiat2: str) -> float:
    """Get estimated transfer cost between two currencies."""
    key = tuple(sorted([fiat1, fiat2]))
    return TRANSFER_COSTS.get(key, 1.0)


def calculate_premium(p2p_buy_price: float, spot_rate: float) -> float:
    """
    Calculate P2P premium percentage.

    Args:
        p2p_buy_price: P2P buy price in local currency per USDT
        spot_rate: Official FX rate (local currency per USD)

    Returns:
        Premium as percentage (e.g., 2.5 for 2.5% premium)
    """
    if spot_rate <= 0:
        return 0.0
    premium = ((p2p_buy_price - spot_rate) / spot_rate) * 100
    return round(premium, 4)


def fetch_all_premiums() -> Dict[str, Dict[str, Any]]:
    """
    Fetch P2P premiums for all currencies.

    Returns:
        Dict mapping currency to premium data:
        {
            "MXN": {"p2p_buy": 17.50, "spot_rate": 17.00, "premium_pct": 2.94},
            ...
        }
    """
    results = {}

    # Get official FX rates
    spot_rates = get_fiat_spot_rates(CURRENCIES)

    for fiat in CURRENCIES:
        try:
            # Get P2P buy price (what you pay to buy USDT)
            p2p_buy = get_p2p_price_binance(fiat, "USDT", "BUY")

            # Get spot rate
            rate_info = spot_rates.get(fiat, {})
            spot_rate = rate_info.get("rate")

            if p2p_buy and spot_rate:
                premium_pct = calculate_premium(p2p_buy, spot_rate)
                results[fiat] = {
                    "p2p_buy": p2p_buy,
                    "spot_rate": spot_rate,
                    "premium_pct": premium_pct,
                    "rate_source": rate_info.get("source", "unknown"),
                    "rate_type": rate_info.get("rate_type", "official"),
                    "status": "ok",
                }
            else:
                results[fiat] = {
                    "status": "no_data",
                    "error": "Missing P2P or spot data",
                }
        except Exception as e:
            results[fiat] = {
                "status": "error",
                "error": str(e),
            }

    return results


def find_cross_currency_opportunities(
    premiums: Dict[str, Dict[str, Any]], threshold: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Find cross-currency arbitrage opportunities.

    Strategy: Buy USDT with low-premium currency, sell for high-premium currency.

    Args:
        premiums: Dict of currency -> premium data
        threshold: Minimum cross-premium spread to consider (%)

    Returns:
        List of opportunity dicts
    """
    opportunities = []

    # Get valid currencies (those with ok status)
    valid_currencies = [fiat for fiat, data in premiums.items() if data.get("status") == "ok"]

    if len(valid_currencies) < 2:
        return opportunities

    # Compare all pairs
    for buy_fiat, sell_fiat in combinations(valid_currencies, 2):
        buy_data = premiums[buy_fiat]
        sell_data = premiums[sell_fiat]

        buy_premium = buy_data["premium_pct"]
        sell_premium = sell_data["premium_pct"]

        # Calculate cross-premium spread
        # Positive spread = buy_fiat has lower premium than sell_fiat
        cross_spread = sell_premium - buy_premium

        if cross_spread < threshold:
            # Try reverse direction
            cross_spread_rev = buy_premium - sell_premium
            if cross_spread_rev >= threshold:
                # Swap direction
                buy_fiat, sell_fiat = sell_fiat, buy_fiat
                buy_data, sell_data = sell_data, buy_data
                buy_premium, sell_premium = sell_premium, buy_premium
                cross_spread = cross_spread_rev
            else:
                continue

        # Calculate transfer cost and edge
        transfer_cost = _get_transfer_cost(buy_fiat, sell_fiat)
        edge_net = cross_spread - transfer_cost

        opportunities.append(
            {
                "buy_fiat": buy_fiat,
                "sell_fiat": sell_fiat,
                "buy_premium_pct": float(buy_premium),
                "sell_premium_pct": float(sell_premium),
                "cross_premium_spread": float(round(cross_spread, 4)),
                "estimated_transfer_cost_pct": float(transfer_cost),
                "edge_net": float(round(edge_net, 4)),
                "viable": bool(edge_net > 0),
                "route": f"{buy_fiat}→USDT(Binance P2P)→USDT→{sell_fiat}(Binance P2P)",
                "buy_p2p_price": float(buy_data["p2p_buy"]),
                "sell_p2p_price": float(sell_data["p2p_buy"]),
                # reference_price: official FX rate of the buy currency (local per USDT).
                # Used as the normalized price reference for ALFRED validation since
                # Type F records have no direct spot_price — the pair is synthetic.
                "reference_price": float(buy_data.get("spot_rate", 0.0)),
            }
        )

    return opportunities


def scan_cross_currency(log_to_file: bool = True) -> List[Dict[str, Any]]:
    """
    Scan P2P markets for cross-currency arbitrage opportunities.

    Args:
        log_to_file: Whether to log opportunities to JSONL

    Returns:
        List of opportunity dicts
    """
    threshold = _load_threshold()
    print(f"[scanner_cross_currency] Scanning {len(CURRENCIES)} currencies (threshold: {threshold:.2f}%)...")

    # Fetch all premiums
    premiums = fetch_all_premiums()

    # Print premium summary
    for fiat, data in premiums.items():
        if data.get("status") == "ok":
            print(f"  [scanner_cross_currency] {fiat}: Premium {data['premium_pct']:+.2f}%")
        else:
            print(f"  [scanner_cross_currency] {fiat}: {data.get('error', 'No data')}")

    # Find opportunities
    opportunities = find_cross_currency_opportunities(premiums, threshold)

    results = []
    for opp in opportunities:
        # Add metadata
        full_opp = {
            "opp_id": f"OPP-F-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "F",
            "scanner_id": SCANNER_ID,
            "asset": "USDT",
            "market": f"{opp['buy_fiat']}/{opp['sell_fiat']}",
            **opp,
            "observe_only": True,
        }

        results.append(full_opp)

        if log_to_file:
            _append_to_log(full_opp)

        viable_str = "✓" if opp["viable"] else "✗"
        print(
            f"  [scanner_cross_currency] {opp['buy_fiat']}→{opp['sell_fiat']}: "
            f"Spread {opp['cross_premium_spread']:+.2f}% | EdgeNet {opp['edge_net']:+.2f}% {viable_str} | Logged"
        )

    print(f"[scanner_cross_currency] Scan complete: {len(results)} opportunities found")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("P2P Cross-Currency Premium Scanner (Type F)")
    print("=" * 70)
    results = scan_cross_currency()
    print(f"\n✓ {len(results)} opportunities detected")
