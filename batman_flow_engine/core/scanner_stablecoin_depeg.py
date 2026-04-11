"""
Scanner H: Stablecoin Depeg Scanner

PURPOSE: Monitor USDT, USDC, DAI prices across exchanges.
         Alert on depeg events (price < 0.995 or > 1.005).
         Alert on cross-exchange arbitrage (spread > 0.2%).

DATA SOURCES:
  - Binance: via scanner_multi_exchange
  - OKX: via scanner_multi_exchange
  - Bybit: via scanner_multi_exchange

OUTPUT: storage/logs/opportunities.jsonl

FIELDS:
  - type: "H"
  - scanner_id: "H-STABLECOIN-DEPEG"
"""

import json
import uuid
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Import from existing multi-exchange scanner (internal functions)
from .scanner_multi_exchange import (
    _fetch_binance_price as fetch_binance_price,
    _fetch_okx_price as fetch_okx_price,
    _fetch_bybit_price as fetch_bybit_price,
)

SCANNER_ID = "H-STABLECOIN-DEPEG"
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

# Stablecoins to monitor
STABLECOINS = ["USDT", "USDC", "DAI"]

# Trading pairs per exchange
STABLECOIN_PAIRS = {
    "binance": {
        "USDT": "USDTDAI",  # USDT priced in DAI (proxy for USD)
        "USDC": "USDCUSDT",
        "DAI": "DAIUSDT",
    },
    "okx": {
        "USDT": "USDT-DAI",
        "USDC": "USDC-USDT",
        "DAI": "DAI-USDT",
    },
    "bybit": {
        "USDC": "USDCUSDT",
        "DAI": "DAIUSDT",
    },
}

# Depeg thresholds
DEPEG_LOW = 0.995
DEPEG_HIGH = 1.005


def _load_threshold() -> float:
    """Load min_depeg_H threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_depeg_H", 0.2))
    except Exception:
        pass
    return 0.2  # Default 0.2%


def _append_to_log(opportunity: dict) -> bool:
    """Append opportunity to JSONL log file."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_stablecoin_depeg] Log error: {e}")
        return False


def fetch_stablecoin_price(exchange: str, stablecoin: str) -> Optional[float]:
    """
    Fetch stablecoin price from an exchange.

    Args:
        exchange: Exchange name (binance, okx, bybit)
        stablecoin: Stablecoin (USDT, USDC, DAI)

    Returns:
        Price in USD (or None on error)
    """
    pairs = STABLECOIN_PAIRS.get(exchange, {})
    pair = pairs.get(stablecoin)

    if not pair:
        return None

    try:
        if exchange == "binance":
            result = fetch_binance_price(pair)
        elif exchange == "okx":
            result = fetch_okx_price(pair)
        elif exchange == "bybit":
            result = fetch_bybit_price(pair)
        else:
            return None

        if result and result.get("price"):
            price = result["price"]
            # Handle inverse pairs (e.g., USDCUSDT means 1 USDC = X USDT)
            # For USDT priced in DAI, we need to invert
            if stablecoin == "USDT" and "DAI" in pair:
                return 1 / price if price > 0 else None
            return price
        return None

    except Exception:
        return None


def fetch_all_stablecoin_prices() -> Dict[str, Dict[str, Optional[float]]]:
    """
    Fetch all stablecoin prices from all exchanges.

    Returns:
        Dict mapping stablecoin -> exchange -> price
    """
    results = {}
    exchanges = ["binance", "okx", "bybit"]

    for stablecoin in STABLECOINS:
        results[stablecoin] = {}
        for exchange in exchanges:
            price = fetch_stablecoin_price(exchange, stablecoin)
            if price is not None:
                results[stablecoin][exchange] = price

    return results


def check_depeg(price: float) -> Optional[str]:
    """
    Check if a price indicates a depeg event.

    Args:
        price: Stablecoin price

    Returns:
        "low" if < 0.995, "high" if > 1.005, None otherwise
    """
    if price < DEPEG_LOW:
        return "low"
    elif price > DEPEG_HIGH:
        return "high"
    return None


def find_depeg_opportunities(prices: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    """
    Find depeg events and arbitrage opportunities.

    Args:
        prices: Dict mapping stablecoin -> exchange -> price

    Returns:
        List of opportunity dicts
    """
    opportunities = []
    threshold = _load_threshold()

    for stablecoin, exchange_prices in prices.items():
        if not exchange_prices:
            continue

        # Check for depeg events
        for exchange, price in exchange_prices.items():
            depeg_type = check_depeg(price)
            if depeg_type:
                opportunities.append(
                    {
                        "event_type": "depeg",
                        "stablecoin": stablecoin,
                        "exchange": exchange,
                        "price": price,
                        "depeg_direction": depeg_type,
                        "deviation_pct": abs(price - 1.0) * 100,
                    }
                )

        # Check for cross-exchange arbitrage
        if len(exchange_prices) >= 2:
            prices_list = list(exchange_prices.items())
            min_exchange, min_price = min(prices_list, key=lambda x: x[1])
            max_exchange, max_price = max(prices_list, key=lambda x: x[1])

            if min_price > 0:
                spread_pct = ((max_price - min_price) / min_price) * 100

                if spread_pct >= threshold:
                    opportunities.append(
                        {
                            "event_type": "arbitrage",
                            "stablecoin": stablecoin,
                            "buy_exchange": min_exchange,
                            "sell_exchange": max_exchange,
                            "buy_price": min_price,
                            "sell_price": max_price,
                            "spread_pct": round(spread_pct, 4),
                        }
                    )

    return opportunities


def scan_stablecoin_depeg(log_to_file: bool = True) -> List[Dict[str, Any]]:
    """
    Scan for stablecoin depeg events and arbitrage opportunities.

    Args:
        log_to_file: Whether to log opportunities to JSONL

    Returns:
        List of opportunity dicts
    """
    threshold = _load_threshold()
    print(f"[scanner_stablecoin_depeg] Scanning {len(STABLECOINS)} stablecoins (arb threshold: {threshold:.2f}%)...")

    # Fetch all prices
    prices = fetch_all_stablecoin_prices()

    # Print price summary
    for stablecoin, exchange_prices in prices.items():
        if exchange_prices:
            prices_str = ", ".join(f"{ex}={p:.4f}" for ex, p in exchange_prices.items())
            print(f"  [scanner_stablecoin_depeg] {stablecoin}: {prices_str}")
        else:
            print(f"  [scanner_stablecoin_depeg] {stablecoin}: No data")

    # Find opportunities
    raw_opps = find_depeg_opportunities(prices)

    results = []
    for opp in raw_opps:
        event_type = opp["event_type"]

        # Create full opportunity record
        full_opp = {
            "opp_id": f"OPP-H-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "H",
            "scanner_id": SCANNER_ID,
            "event_type": event_type,
            "stablecoin": opp["stablecoin"],
            "observe_only": True,
        }

        if event_type == "depeg":
            full_opp.update(
                {
                    "exchange": opp["exchange"],
                    "price": opp["price"],
                    "depeg_direction": opp["depeg_direction"],
                    "deviation_pct": round(opp["deviation_pct"], 4),
                    "viable": True,  # Depeg events are always notable
                }
            )
            print(
                f"  [scanner_stablecoin_depeg] DEPEG: {opp['stablecoin']} on {opp['exchange']} "
                f"at {opp['price']:.4f} ({opp['depeg_direction']})"
            )

        elif event_type == "arbitrage":
            edge_net = opp["spread_pct"] - 0.20  # Assume 0.2% fees
            full_opp.update(
                {
                    "buy_exchange": opp["buy_exchange"],
                    "sell_exchange": opp["sell_exchange"],
                    "buy_price": opp["buy_price"],
                    "sell_price": opp["sell_price"],
                    "spread_pct": opp["spread_pct"],
                    "edge_net": round(edge_net, 4),
                    "viable": edge_net > 0,
                }
            )
            viable_str = "✓" if edge_net > 0 else "✗"
            print(
                f"  [scanner_stablecoin_depeg] ARB: {opp['stablecoin']} "
                f"{opp['buy_exchange']}→{opp['sell_exchange']} | "
                f"Spread {opp['spread_pct']:.2f}% {viable_str}"
            )

        results.append(full_opp)

        if log_to_file:
            _append_to_log(full_opp)

    print(f"[scanner_stablecoin_depeg] Scan complete: {len(results)} events found")
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Stablecoin Depeg Scanner (Type H)")
    print("=" * 70)
    results = scan_stablecoin_depeg()
    print(f"\n✓ {len(results)} events detected")
