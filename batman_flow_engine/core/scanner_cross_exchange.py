"""
Scanner A: Cross-Exchange Price Detection (Binance vs OKX)

DATA SOURCES:
  - Binance: https://api.binance.com/api/v3/ticker/price
  - OKX:     https://www.okx.com/api/v5/market/ticker

OUTPUT: storage/logs/opportunities.jsonl

FIELDS:
  - type: "A"
  - scanner_id: "A-CROSS-EXCHANGE"
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

SCANNER_ID = "A-CROSS-EXCHANGE"
TIMEOUT = 10
RETRIES = 3
USER_AGENT = "batman-p2p-lab/1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

SYMBOLS = [
    {"asset": "BTC", "binance": "BTCUSDT", "okx": "BTC-USDT"},
    {"asset": "ETH", "binance": "ETHUSDT", "okx": "ETH-USDT"},
    {"asset": "SOL", "binance": "SOLUSDT", "okx": "SOL-USDT"},
]

BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
OKX_URL = "https://www.okx.com/api/v5/market/ticker"


def _fetch_json(url: str, params: Optional[dict] = None) -> Optional[dict]:
    if params:
        url = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt)
    return None


def _fetch_binance_price(symbol: str) -> Optional[float]:
    data = _fetch_json(BINANCE_URL, {"symbol": symbol})
    if data and "price" in data:
        try:
            return float(data["price"])
        except (ValueError, TypeError):
            return None
    return None


def _fetch_okx_price(inst_id: str) -> Optional[float]:
    data = _fetch_json(OKX_URL, {"instId": inst_id})
    if data and data.get("code") == "0":
        try:
            return float(data["data"][0]["last"])
        except (KeyError, IndexError, ValueError, TypeError):
            return None
    return None


def _load_threshold() -> float:
    """Load min_spread_pct_A threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_spread_pct_A", 0.0))
    except Exception:
        pass
    return 0.0


def _append_to_log(opportunity: dict) -> bool:
    try:
        # Audit Section C #9: stamp cycle_id from process-global context if absent.
        from core.cycle_context import stamp_cycle_id

        stamp_cycle_id(opportunity)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_cross] Log error: {e}")
        return False


def scan_cross_exchange(log_to_file: bool = True) -> list[dict]:
    results = []
    threshold = _load_threshold()
    print(f"[scanner_cross] Scanning {len(SYMBOLS)} pairs (threshold: {threshold:.2f}%)...")

    for sym in SYMBOLS:
        asset = sym["asset"]
        binance_px = _fetch_binance_price(sym["binance"])
        okx_px = _fetch_okx_price(sym["okx"])

        if binance_px is None or okx_px is None:
            print(f"  [scanner_cross] {asset}: fetch failed")
            continue

        spread_pct = ((okx_px - binance_px) / binance_px) * 100

        opp = {
            "opp_id": f"OPP-A-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "A",
            "asset": asset,
            "venue": "binance_vs_okx",
            "binance_px": round(binance_px, 6),
            "okx_px": round(okx_px, 6),
            "spread_pct": round(spread_pct, 6),
            # Step 8 (audit plan): canonical edge field used by Clark Kent publisher.
            # Same magnitude as spread_pct; sign-stripped because the publisher
            # treats edge as a positive scalar.
            "edge_net": round(abs(spread_pct), 6),
            "scanner_id": SCANNER_ID,
            "observe_only": True,
        }

        print(f"  [scanner_cross] {asset}: Binance ${binance_px:.2f} | OKX ${okx_px:.2f} | spread {spread_pct:+.4f}%")

        # Only log if spread exceeds threshold
        if log_to_file and abs(spread_pct) >= threshold:
            _append_to_log(opp)
            print(f"  [scanner_cross] {asset}: Logged (spread {spread_pct:+.4f}% >= threshold {threshold:.2f}%)")
        elif log_to_file:
            print(f"  [scanner_cross] {asset}: Skipped (spread {abs(spread_pct):.4f}% < threshold {threshold:.2f}%)")

        results.append(opp)

    return results


if __name__ == "__main__":
    print("=" * 70)
    print("Cross-Exchange Scanner (Binance vs OKX)")
    print("=" * 70)
    results = scan_cross_exchange()
    print(f"\n✓ {len(results)} pairs scanned")
