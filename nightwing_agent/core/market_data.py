"""
NIGHTWING Market Data Module

Fetches market prices based on operating mode:
- SIMULATED: Fake/seeded data for testing
- PAPER: Real spot prices from Binance public API
- LIVE: Real ingestion with graceful simulated fallback
"""

import logging
import random
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from core.live_market import fetch_binance_p2p_offers, fetch_binance_spot_prices, fetch_exchange_rate

logger = logging.getLogger("nightwing.market_data")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "settings.yaml"

# Seeded prices for SIMULATED mode
SIMULATED_PRICES = {
    "BTCUSDT": 68000.00,
    "ETHUSDT": 1980.00,
    "SOLUSDT": 145.00,
    "BNBUSDT": 580.00,
}


def _load_config() -> Dict[str, Any]:
    """Load settings from config/settings.yaml."""
    try:
        if CONFIG_FILE.exists():
            return yaml.safe_load(CONFIG_FILE.read_text()) or {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return {}


def _get_mode() -> str:
    """Get operating mode from config."""
    config = _load_config()
    return config.get("mode", "SIMULATED").upper()


def fetch_simulated_prices() -> Dict[str, Any]:
    """
    Return fake/seeded prices for testing.

    Adds small random variation to make it look realistic.
    """
    logger.info("Fetching prices in SIMULATED mode (fake data)")

    prices = {}
    for symbol, base_price in SIMULATED_PRICES.items():
        variation = random.uniform(-0.005, 0.005)
        prices[symbol] = round(base_price * (1 + variation), 2)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "SIMULATED",
        "prices": prices,
        "source": "seeded_data",
    }


def fetch_real_prices() -> Dict[str, Any]:
    """Fetch real spot prices from Binance for PAPER mode."""
    logger.info("Fetching prices in PAPER mode (real Binance API)")
    try:
        result = fetch_binance_spot_prices()
        return {
            "ts": result["ts"],
            "mode": "PAPER",
            "prices": result["prices"],
            "source": result["source"],
        }
    except Exception as e:
        logger.error(f"Binance API error: {e}")
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": "PAPER",
            "prices": {},
            "source": "binance_spot",
            "error": str(e),
        }


def fetch_live_prices() -> Dict[str, Any]:
    """Fetch live market inputs with safe fallback to simulated prices."""
    logger.info("Fetching prices in LIVE market mode")
    try:
        spot = fetch_binance_spot_prices()
        p2p = fetch_binance_p2p_offers()
        fx = fetch_exchange_rate()
        return {
            "ts": spot["ts"],
            "mode": "LIVE",
            "prices": spot["prices"],
            "source": "live_market",
            "p2p_offers": p2p["offers"],
            "exchange_rate": fx["rate"],
            "exchange_rate_quote": fx["quote"],
        }
    except Exception as e:
        logger.error(f"Live market ingestion error: {e}")
        fallback = fetch_simulated_prices()
        fallback["mode"] = "LIVE"
        fallback["source"] = "seeded_data_fallback"
        fallback["fallback_reason"] = str(e)
        return fallback


def fetch_prices(mode: str = None) -> Dict[str, Any]:
    """
    Fetch prices based on operating mode.

    Args:
        mode: Operating mode (SIMULATED, PAPER, LIVE)
              If None, uses config setting.

    Returns:
        Dict with prices and metadata

    Raises:
    """
    if mode is None:
        mode = _get_mode()

    mode = mode.upper()

    if mode == "SIMULATED":
        return fetch_simulated_prices()
    elif mode == "PAPER":
        return fetch_real_prices()
    elif mode == "LIVE":
        return fetch_live_prices()
    else:
        logger.warning(f"Unknown mode '{mode}', defaulting to SIMULATED")
        return fetch_simulated_prices()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing market_data module...")

    print("\n1. SIMULATED mode:")
    result = fetch_prices("SIMULATED")
    for sym, price in result["prices"].items():
        print(f"   {sym}: ${price:,.2f}")

    print("\n2. PAPER mode:")
    result = fetch_prices("PAPER")
    for sym, price in result["prices"].items():
        print(f"   {sym}: ${price:,.2f}")
