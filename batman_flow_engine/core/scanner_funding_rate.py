"""
Scanner E: Funding Rate Arbitrage Scanner

PURPOSE: Monitor funding rates across Binance, OKX, and Bybit.
         Alert when rates are high or when cross-exchange spread exists.

DATA SOURCES:
  - Binance Futures: https://fapi.binance.com/fapi/v1/fundingRate?symbol={PAIR}&limit=1
  - OKX:             https://www.okx.com/api/v5/public/funding-rate?instId={PAIR}-SWAP
  - Bybit:           https://api.bybit.com/v5/market/funding/history?category=linear&symbol={PAIR}

OUTPUT: storage/logs/opportunities.jsonl

FIELDS:
  - type: "E"
  - scanner_id: "E-FUNDING-RATE"
"""

import json
import time
import uuid
import urllib.request
import urllib.error
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

SCANNER_ID = "E-FUNDING-RATE"
TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-flow-engine/1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

# Assets to monitor
ASSETS = ["BTC", "ETH", "SOL"]

# API URLs
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
BYBIT_FUNDING_URL = "https://api.bybit.com/v5/market/funding/history"

# Symbol mappings per exchange
SYMBOL_MAP = {
    "BTC": {"binance": "BTCUSDT", "okx": "BTC-USDT-SWAP", "bybit": "BTCUSDT"},
    "ETH": {"binance": "ETHUSDT", "okx": "ETH-USDT-SWAP", "bybit": "ETHUSDT"},
    "SOL": {"binance": "SOLUSDT", "okx": "SOL-USDT-SWAP", "bybit": "SOLUSDT"},
}


def _fetch_json(url: str, params: Optional[Dict[str, str]] = None) -> Optional[Dict]:
    """Fetch JSON data from URL with retry logic."""
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)
    return None


def _load_threshold() -> float:
    """Load min_funding_rate_E threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_funding_rate_E", 0.01))
    except Exception:
        pass
    return 0.01  # Default 0.01% per 8h


def _append_to_log(opportunity: dict) -> bool:
    """Append opportunity to JSONL log file."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_funding] Log error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Exchange Funding Rate Fetchers
# ─────────────────────────────────────────────────────────────────────────────


def _fetch_binance_funding_rate(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch funding rate from Binance Futures."""
    data = _fetch_json(BINANCE_FUNDING_URL, {"symbol": symbol, "limit": "1"})

    if not data or not isinstance(data, list) or len(data) == 0:
        return None

    try:
        rate_data = data[0]
        funding_rate = float(rate_data.get("fundingRate", 0))
        funding_time = int(rate_data.get("fundingTime", 0))

        # Convert timestamp to ISO format
        if funding_time > 0:
            next_funding_time = datetime.fromtimestamp(funding_time / 1000, tz=timezone.utc).isoformat()
        else:
            next_funding_time = None

        return {
            "exchange": "binance",
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100, 6),
            "next_funding_time": next_funding_time,
        }
    except (ValueError, TypeError, KeyError):
        return None


def _fetch_okx_funding_rate(inst_id: str) -> Optional[Dict[str, Any]]:
    """Fetch funding rate from OKX perpetual swaps."""
    data = _fetch_json(OKX_FUNDING_URL, {"instId": inst_id})

    if not data or data.get("code") != "0":
        return None

    try:
        rate_data = data.get("data", [{}])[0]
        funding_rate = float(rate_data.get("fundingRate", 0))
        next_funding_ts = int(rate_data.get("nextFundingTime", 0))

        # Convert timestamp to ISO format
        if next_funding_ts > 0:
            next_funding_time = datetime.fromtimestamp(next_funding_ts / 1000, tz=timezone.utc).isoformat()
        else:
            next_funding_time = None

        return {
            "exchange": "okx",
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100, 6),
            "next_funding_time": next_funding_time,
        }
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def _fetch_bybit_funding_rate(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch funding rate from Bybit perpetual futures."""
    data = _fetch_json(BYBIT_FUNDING_URL, {"category": "linear", "symbol": symbol, "limit": "1"})

    if not data or data.get("retCode") != 0:
        return None

    try:
        result = data.get("result", {})
        rate_list = result.get("list", [])

        if not rate_list:
            return None

        rate_data = rate_list[0]
        funding_rate = float(rate_data.get("fundingRate", 0))
        funding_time_ts = int(rate_data.get("fundingRateTimestamp", 0))

        # Convert timestamp to ISO format
        if funding_time_ts > 0:
            funding_time = datetime.fromtimestamp(funding_time_ts / 1000, tz=timezone.utc).isoformat()
        else:
            funding_time = None

        return {
            "exchange": "bybit",
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100, 6),
            "next_funding_time": funding_time,
        }
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def fetch_all_funding_rates(asset: str) -> Dict[str, Dict[str, Any]]:
    """
    Fetch funding rates from all exchanges for a given asset.

    Args:
        asset: Asset symbol (BTC, ETH, SOL)

    Returns:
        Dict mapping exchange names to funding rate data
    """
    rates = {}
    symbols = SYMBOL_MAP.get(asset, {})

    # Binance
    if symbols.get("binance"):
        data = _fetch_binance_funding_rate(symbols["binance"])
        if data:
            rates["binance"] = data

    # OKX
    if symbols.get("okx"):
        data = _fetch_okx_funding_rate(symbols["okx"])
        if data:
            rates["okx"] = data

    # Bybit
    if symbols.get("bybit"):
        data = _fetch_bybit_funding_rate(symbols["bybit"])
        if data:
            rates["bybit"] = data

    return rates


def analyze_funding_rates(
    asset: str, rates: Dict[str, Dict[str, Any]], threshold: float = 0.01
) -> List[Dict[str, Any]]:
    """
    Analyze funding rates and detect opportunities.

    Args:
        asset: Asset symbol
        rates: Dict of exchange -> funding rate data
        threshold: Minimum funding rate percentage to consider (per 8h)

    Returns:
        List of opportunity dicts
    """
    opportunities = []

    if not rates:
        return opportunities

    # Find high funding rates
    for exchange, data in rates.items():
        rate_pct = data.get("funding_rate_pct", 0)

        if abs(rate_pct) >= threshold:
            # Annualize: rate per 8h * 3 * 365 = APY
            annualized_pct = rate_pct * 3 * 365

            opportunities.append(
                {
                    "opportunity_type": "high_funding",
                    "asset": asset,
                    "exchange": exchange,
                    "funding_rate": data["funding_rate"],
                    "funding_rate_pct": rate_pct,
                    "annualized_pct": round(annualized_pct, 2),
                    "next_funding_time": data.get("next_funding_time"),
                    "direction": "short" if rate_pct > 0 else "long",
                }
            )

    # Find cross-exchange funding rate arbitrage
    if len(rates) >= 2:
        all_rates = [(ex, data.get("funding_rate_pct", 0)) for ex, data in rates.items()]
        all_rates.sort(key=lambda x: x[1])

        lowest_ex, lowest_rate = all_rates[0]
        highest_ex, highest_rate = all_rates[-1]

        cross_spread = highest_rate - lowest_rate

        # Log cross-exchange opportunity if spread > threshold * 2
        if cross_spread >= threshold * 2:
            opportunities.append(
                {
                    "opportunity_type": "cross_exchange_funding",
                    "asset": asset,
                    "high_exchange": highest_ex,
                    "low_exchange": lowest_ex,
                    "high_rate_pct": highest_rate,
                    "low_rate_pct": lowest_rate,
                    "cross_exchange_spread": round(cross_spread, 4),
                    "annualized_spread_pct": round(cross_spread * 3 * 365, 2),
                    "strategy": f"Long {lowest_ex} + Short {highest_ex}",
                }
            )

    return opportunities


def scan_funding_rates(log_to_file: bool = True) -> List[Dict[str, Any]]:
    """
    Scan funding rates across all assets and exchanges.

    Args:
        log_to_file: Whether to log opportunities to JSONL

    Returns:
        List of opportunity dicts
    """
    all_opportunities = []
    threshold = _load_threshold()

    print(f"[scanner_funding] Scanning funding rates for {len(ASSETS)} assets (threshold: {threshold:.4f}%)...")

    for asset in ASSETS:
        # Fetch rates from all exchanges
        rates = fetch_all_funding_rates(asset)

        if not rates:
            print(f"  [scanner_funding] {asset}: No data available")
            continue

        # Print rates
        rate_strs = [f"{ex}={data['funding_rate_pct']:+.4f}%" for ex, data in rates.items()]
        print(f"  [scanner_funding] {asset}: {' | '.join(rate_strs)}")

        # Analyze for opportunities
        opportunities = analyze_funding_rates(asset, rates, threshold)

        for opp in opportunities:
            # Add metadata
            full_opp = {
                "opp_id": f"OPP-E-{uuid.uuid4().hex[:10].upper()}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "E",
                "scanner_id": SCANNER_ID,
                **opp,
                "observe_only": True,
            }

            all_opportunities.append(full_opp)

            if log_to_file:
                _append_to_log(full_opp)

            if opp["opportunity_type"] == "high_funding":
                print(
                    f"    → HIGH FUNDING: {asset}@{opp['exchange']} {opp['funding_rate_pct']:+.4f}% "
                    f"(~{opp['annualized_pct']:+.1f}% APY) | Logged"
                )
            elif opp["opportunity_type"] == "cross_exchange_funding":
                print(
                    f"    → CROSS-EXCHANGE: {opp['strategy']} | Spread: {opp['cross_exchange_spread']:+.4f}% "
                    f"(~{opp['annualized_spread_pct']:+.1f}% APY) | Logged"
                )

    print(f"[scanner_funding] Scan complete: {len(all_opportunities)} opportunities found")
    return all_opportunities


if __name__ == "__main__":
    print("=" * 70)
    print("Funding Rate Arbitrage Scanner (Type E)")
    print("=" * 70)
    results = scan_funding_rates()
    print(f"\n✓ {len(results)} opportunities detected")
