"""
Scanner: Binance Spot vs Futures Basis Detection

Detects basis inefficiency between Binance spot and perpetual futures.

DATA SOURCES:
  - Spot:    https://api.binance.com/api/v3/ticker/price
  - Futures: https://fapi.binance.com/fapi/v1/ticker/price

SYMBOL: BTCUSDT

OUTPUT: storage/logs/opportunities.jsonl

FIELDS:
  - type: "B"
  - asset: "BTC"
  - venue: "binance_spot_vs_futures"
  - spot_price: float
  - futures_price: float
  - basis_pct: float (percentage difference)
  - scanner_id: "B-FUNDING-BASIS"
  - observe_only: true
  - ts: ISO timestamp
  - opp_id: unique identifier

USAGE:
    from core.scanner_basis import scan_basis

    result = scan_basis()
    # Returns dict with basis data or None on error
"""

import json
import time
import uuid
import urllib.request
import urllib.error
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────────────
SYMBOL = "BTCUSDT"
ASSET = "BTC"
SCANNER_ID = "B-FUNDING-BASIS"
VENUE = "binance_spot_vs_futures"

# API endpoints
SPOT_URL = "https://api.binance.com/api/v3/ticker/price"
FUTURES_URL = "https://fapi.binance.com/fapi/v1/ticker/price"

# Request settings
TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-p2p-lab/1.0"

# Path detection
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"


# ── HTTP Utilities ───────────────────────────────────────────────────────────
def _fetch_json(url: str, params: Optional[dict] = None) -> Optional[dict]:
    """
    Fetch JSON from URL with retry logic and timeout.

    Args:
        url: API endpoint URL
        params: Optional query parameters

    Returns:
        Parsed JSON response or None on error
    """
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query_string}"

    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)

        except urllib.error.HTTPError as e:
            print(f"  [scanner_basis] HTTP {e.code} on attempt {attempt + 1}/{RETRIES}")
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)

        except urllib.error.URLError as e:
            print(f"  [scanner_basis] Network error on attempt {attempt + 1}/{RETRIES}: {e}")
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)

        except json.JSONDecodeError as e:
            print(f"  [scanner_basis] JSON decode error: {e}")
            return None

        except Exception as e:
            print(f"  [scanner_basis] Unexpected error on attempt {attempt + 1}/{RETRIES}: {e}")
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)

    return None


def _fetch_spot_price(symbol: str = SYMBOL) -> Optional[float]:
    """
    Fetch spot price for given symbol from Binance spot API.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)

    Returns:
        Spot price as float or None on error
    """
    data = _fetch_json(SPOT_URL, params={"symbol": symbol})

    if data and "price" in data:
        try:
            return float(data["price"])
        except (ValueError, TypeError):
            print(f"  [scanner_basis] Invalid spot price format: {data.get('price')}")
            return None

    print(f"  [scanner_basis] Missing price in spot response: {data}")
    return None


def _fetch_futures_price(symbol: str = SYMBOL) -> Optional[float]:
    """
    Fetch futures price for given symbol from Binance futures API.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)

    Returns:
        Futures price as float or None on error
    """
    data = _fetch_json(FUTURES_URL, params={"symbol": symbol})

    if data and "price" in data:
        try:
            return float(data["price"])
        except (ValueError, TypeError):
            print(f"  [scanner_basis] Invalid futures price format: {data.get('price')}")
            return None

    print(f"  [scanner_basis] Missing price in futures response: {data}")
    return None


# ── Basis Calculation ────────────────────────────────────────────────────────
def calculate_basis(spot_price: float, futures_price: float) -> float:
    """
    Calculate basis percentage between futures and spot.

    Basis = ((futures_price - spot_price) / spot_price) * 100

    Positive basis = contango (futures > spot)
    Negative basis = backwardation (futures < spot)

    Args:
        spot_price: Spot market price
        futures_price: Futures market price

    Returns:
        Basis as percentage
    """
    if spot_price <= 0:
        raise ValueError(f"Invalid spot price: {spot_price}")

    basis_decimal = (futures_price - spot_price) / spot_price
    return basis_decimal * 100.0


# ── Opportunity Generation ───────────────────────────────────────────────────
def _generate_opportunity(spot_price: float, futures_price: float, basis_pct: float) -> dict:
    """
    Generate opportunity record with all required fields.

    Args:
        spot_price: Spot market price
        futures_price: Futures market price
        basis_pct: Calculated basis percentage

    Returns:
        Dictionary with opportunity data
    """
    now = datetime.now(timezone.utc)
    opp_id = f"OPP-B-{uuid.uuid4().hex[:10].upper()}"

    return {
        "opp_id": opp_id,
        "ts": now.isoformat(),
        "type": "B",
        "asset": ASSET,
        "venue": VENUE,
        "spot_price": round(spot_price, 6),
        "futures_price": round(futures_price, 6),
        "basis_pct": round(basis_pct, 6),
        # Step 8 (audit plan): canonical edge field used by Clark Kent publisher.
        # Magnitude of dislocation — backwardation (negative basis) is still a
        # tradeable edge.
        "edge_net": round(abs(basis_pct), 6),
        "scanner_id": SCANNER_ID,
        "observe_only": True,
    }


# ── Logging ──────────────────────────────────────────────────────────────────
def _load_threshold() -> float:
    """Load min_basis_pct_B threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_basis_pct_B", 0.0))
    except Exception:
        pass
    return 0.0


def _append_to_log(opportunity: dict) -> bool:
    """
    Append opportunity to JSONL log file.

    Args:
        opportunity: Opportunity dictionary to log

    Returns:
        True if successfully logged, False otherwise
    """
    try:
        # Ensure parent directory exists
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Append JSONL record
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")

        return True

    except IOError as e:
        print(f"  [scanner_basis] Failed to write log: {e}")
        return False
    except Exception as e:
        print(f"  [scanner_basis] Unexpected logging error: {e}")
        return False


# ── Main Scan Function ───────────────────────────────────────────────────────
def scan_basis(symbol: str = SYMBOL, log_to_file: bool = True) -> Optional[dict]:
    """
    Scan for basis inefficiency between Binance spot and futures.

    Fetches current prices, calculates basis, and optionally logs to file.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
        log_to_file: Whether to append result to opportunities.jsonl (default: True)

    Returns:
        Opportunity dict if successful, None on error

    Example:
        >>> result = scan_basis()
        >>> if result:
        ...     print(f"Basis: {result['basis_pct']:.2f}%")
    """
    print(f"[scanner_basis] Scanning {symbol}...")

    # Fetch spot price
    spot_price = _fetch_spot_price(symbol)
    if spot_price is None:
        print("  [scanner_basis] Failed to fetch spot price")
        return None

    # Fetch futures price
    futures_price = _fetch_futures_price(symbol)
    if futures_price is None:
        print("  [scanner_basis] Failed to fetch futures price")
        return None

    # Calculate basis
    try:
        basis_pct = calculate_basis(spot_price, futures_price)
    except ValueError as e:
        print(f"  [scanner_basis] Basis calculation error: {e}")
        return None

    # Generate opportunity record
    opportunity = _generate_opportunity(spot_price, futures_price, basis_pct)

    # Log result
    print(
        f"  [scanner_basis] Spot: ${spot_price:.2f} | " f"Futures: ${futures_price:.2f} | " f"Basis: {basis_pct:+.4f}%"
    )

    # Append to log file if requested and above threshold
    if log_to_file:
        threshold = _load_threshold()
        if abs(basis_pct) >= threshold:
            if _append_to_log(opportunity):
                print(f"  [scanner_basis] Logged (basis {abs(basis_pct):.4f}% >= threshold {threshold:.2f}%)")
            else:
                print(f"  [scanner_basis] Skipped (basis {abs(basis_pct):.4f}% < threshold {threshold:.2f}%)")
        else:
            print(f"  [scanner_basis] Skipped (basis {abs(basis_pct):.4f}% < threshold {threshold:.2f}%)")

    return opportunity


# ── CLI Entry Point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    """Run basis scanner as standalone script."""
    print("=" * 70)
    print("Binance Spot vs Futures Basis Scanner")
    print("=" * 70)

    result = scan_basis()

    if result:
        print("\n✓ Scan completed successfully")
        print(f"\nOpportunity ID: {result['opp_id']}")
        print(f"Timestamp:      {result['ts']}")
        print(f"Basis:          {result['basis_pct']:+.4f}%")
    else:
        print("\n✗ Scan failed")
        exit(1)
