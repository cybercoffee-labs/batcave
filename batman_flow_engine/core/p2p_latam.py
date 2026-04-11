import ccxt
import requests
import numpy as np
import json
import uuid
import yaml
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from time import time
from datetime import time as dt_time

logger = logging.getLogger("scanner_p2p")

SCANNER_ID = "C-P2P-LATAM"
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
CONFIG_FILE = BASE_DIR / "config.yaml"

# ───────────────────────── SPOT RATE CACHE ─────────────────────────
# Cache fiat spot rates for 10 minutes to avoid redundant API calls
_SPOT_RATE_CACHE: Dict[str, float] = {}
_CACHE_TIMESTAMP: float = 0
_CACHE_DURATION: int = 600  # 10 minutes in seconds


def _is_operating_hours(fiat: str) -> bool:
    """
    Check if current time is within operating hours for fiat currency.
    MXN: SPEI hours 05:00-23:30 Mexico City time
    Others: 24/7
    """
    if fiat.upper() != "MXN":
        return True  # ARS, COP, VES are 24/7

    try:
        import pytz

        tz = pytz.timezone("America/Mexico_City")
        local_now = datetime.now(tz)
        current_time = local_now.time()
        spei_start = dt_time(5, 0)
        spei_end = dt_time(23, 30)
        return spei_start <= current_time <= spei_end
    except ImportError:
        # Fallback: assume open if pytz not available
        logger.warning("pytz not installed, assuming MXN operating hours open")
        return True


def _load_threshold() -> float:
    """Load min_edge_pct_C threshold from config.yaml."""
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return float(cfg.get("thresholds", {}).get("min_edge_pct_C", 0.0))
    except Exception:
        pass
    return 0.0


def _load_fees() -> Dict[str, float]:
    """
    Load fee configuration from config.yaml.

    Returns dict with keys:
        - bank_transfer_mxn, bank_transfer_cop, bank_transfer_ves, bank_transfer_ars (in %)
        - exchange_fee (in %)
        - slippage_estimate (in %)
    """
    defaults = {
        "bank_transfer_mxn": 0.10,
        "bank_transfer_cop": 0.15,
        "bank_transfer_ves": 0.20,
        "bank_transfer_ars": 0.25,
        "exchange_fee": 0.10,
        "slippage_estimate": 0.05,
    }
    try:
        if CONFIG_FILE.exists():
            cfg = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            fees_cfg = cfg.get("thresholds", {}).get("fees", {})
            for key in defaults:
                if key in fees_cfg:
                    defaults[key] = float(fees_cfg[key])
    except Exception:
        pass
    return defaults


def _calculate_total_friction(fiat: str, fees: Dict[str, float]) -> float:
    """
    Calculate total friction percentage for a given fiat currency.

    Args:
        fiat: Currency code (MXN, COP, VES, ARS)
        fees: Fee configuration dict from _load_fees()

    Returns:
        Total friction as percentage (e.g., 0.25 for 0.25%)
    """
    bank_fee_key = f"bank_transfer_{fiat.lower()}"
    bank_fee = fees.get(bank_fee_key, 0.15)  # Default 0.15% if unknown currency
    exchange_fee = fees.get("exchange_fee", 0.10)
    slippage = fees.get("slippage_estimate", 0.05)
    return round(bank_fee + exchange_fee + slippage, 4)


def _append_to_log(opportunity: dict) -> bool:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(opportunity) + "\n")
        return True
    except Exception as e:
        print(f"  [scanner_p2p] Log error: {e}")
        return False


def get_fiat_spot_rates(currencies: List[str]) -> Dict[str, Dict[str, any]]:
    """
    Fetch spot exchange rates for multiple fiat currencies against USD.

    Uses a two-tier fallback strategy:
        1. Primary: https://open.er-api.com/v6/latest/USD (free, no API key)
        2. Fallback: https://api.frankfurter.app/latest?from=USD

    Rates are cached in memory for 10 minutes to minimize API calls.

    Args:
        currencies: List of currency codes (e.g., ['MXN', 'COP', 'VES', 'ARS'])

    Returns:
        Dictionary mapping currency codes to rate info:
        {
            'MXN': {
                'rate': 20.45,
                'source': 'open.er-api.com' | 'frankfurter.app' | 'unavailable',
                'rate_type': 'official' | 'parallel',  # VES only
                'cached': True | False
            },
            ...
        }

    Example:
        >>> rates = get_fiat_spot_rates(['MXN', 'COP', 'VES', 'ARS'])
        >>> print(rates['MXN']['rate'])
        20.45
    """
    global _SPOT_RATE_CACHE, _CACHE_TIMESTAMP

    current_time = time()
    cache_valid = (current_time - _CACHE_TIMESTAMP) < _CACHE_DURATION

    # Return cached rates if valid
    if cache_valid and _SPOT_RATE_CACHE:
        logger.info("Using cached spot rates (age: {:.0f}s)".format(current_time - _CACHE_TIMESTAMP))
        # Return ALL requested currencies, marking missing ones as unavailable
        result = {}
        for currency in currencies:
            if currency == "VES":
                continue  # VES always fetches fresh parallel rate
            if currency in _SPOT_RATE_CACHE:
                result[currency] = {
                    "rate": _SPOT_RATE_CACHE[currency],
                    "source": "cache",
                    "rate_type": "official",
                    "cached": True,
                }
            else:
                # Currency not in cache - mark as unavailable (don't silently omit)
                result[currency] = {
                    "rate": None,
                    "source": "unavailable",
                    "rate_type": "official",
                    "cached": False,
                }
        # VES always needs fresh parallel rate from dolarapi.com
        if "VES" in currencies:
            try:
                import requests as _req

                resp = _req.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
                resp.raise_for_status()
                for item in resp.json():
                    if item.get("fuente") == "paralelo" and item.get("promedio"):
                        result["VES"] = {
                            "rate": float(item["promedio"]),
                            "source": "dolarapi.com",
                            "rate_type": "parallel",
                            "cached": False,
                        }
                        break
            except Exception as e:
                logger.warning(f"VES parallel rate fetch failed in cache path: {e}")
                result["VES"] = {"rate": None, "source": "unavailable", "rate_type": "parallel", "cached": False}
        return result

    # Fetch fresh rates
    logger.info("Fetching fresh spot rates for: {}".format(", ".join(currencies)))
    results = {}

    # Try primary source: open.er-api.com
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("result") == "success":
            rates_data = data.get("rates", {})

            for currency in currencies:
                if currency == "VES":
                    continue  # VES uses parallel rate from dolarapi.com
                if currency in rates_data:
                    rate = float(rates_data[currency])
                    results[currency] = {
                        "rate": rate,
                        "source": "open.er-api.com",
                        "rate_type": "official",
                        "cached": False,
                    }
                    _SPOT_RATE_CACHE[currency] = rate

            _CACHE_TIMESTAMP = current_time
            logger.info(f"Fetched {len(results)}/{len(currencies)} rates from open.er-api.com")

            # Return if we got all currencies
            if len(results) == len(currencies):
                return results

    except requests.exceptions.RequestException as e:
        logger.warning(f"Primary source (open.er-api.com) failed: {e}")

    # Try fallback source: frankfurter.app (doesn't support VES)
    missing = [c for c in currencies if c not in results]
    if missing:
        try:
            # Frankfurter doesn't support VES, so exclude it
            frankfurter_currencies = [c for c in missing if c != "VES"]

            if frankfurter_currencies:
                url = "https://api.frankfurter.app/latest?from=USD"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                rates_data = data.get("rates", {})

                for currency in frankfurter_currencies:
                    if currency in rates_data:
                        rate = float(rates_data[currency])
                        results[currency] = {
                            "rate": rate,
                            "source": "frankfurter.app",
                            "rate_type": "official",
                            "cached": False,
                        }
                        _SPOT_RATE_CACHE[currency] = rate

                _CACHE_TIMESTAMP = current_time
                logger.info(f"Fetched {len(results)}/{len(currencies)} rates from frankfurter.app")

        except requests.exceptions.RequestException as e:
            logger.warning(f"Fallback source (frankfurter.app) failed: {e}")

    # Handle VES separately — ALWAYS use parallel rate from dolarapi.com
    # Override any official rate from er-api (official != P2P market rate)
    if "VES" in currencies:
        results.pop("VES", None)  # Remove official rate if present
    if "VES" in currencies:
        try:
            resp = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
            resp.raise_for_status()
            for item in resp.json():
                if item.get("fuente") == "paralelo" and item.get("promedio"):
                    results["VES"] = {
                        "rate": float(item["promedio"]),
                        "source": "dolarapi.com",
                        "rate_type": "parallel",
                        "cached": False,
                    }
                    logger.info(f"VES parallel rate: {item['promedio']} (dolarapi.com)")
                    break
        except Exception as e:
            logger.warning(f"VES parallel rate fetch failed: {e}")
            results["VES"] = {
                "rate": None,
                "source": "unavailable",
                "rate_type": "parallel",
                "cached": False,
            }

    # Mark any remaining missing currencies as unavailable
    for currency in currencies:
        if currency not in results:
            results[currency] = {
                "rate": None,
                "source": "unavailable",
                "rate_type": "official",
                "cached": False,
            }

    return results


def get_spot_price(pair="USDT/MXN"):
    """
    Legacy function for backward compatibility.

    Fetches USDT/MXN spot price from Binance via ccxt.
    Deprecated: Use get_fiat_spot_rates() instead.
    """
    try:
        b = ccxt.binance()
        ticker = b.fetch_ticker("USDT/MXN" if "USDT/MXN" in b.load_markets() else "BTC/USDT")
        return ticker["last"]
    except Exception:
        return None


def get_p2p_announcements_binance(fiat="MXN", crypto="USDT", trade_type="BUY", top_n=5):
    """
    Fetch top-N P2P announcements from Binance.

    Returns list of dicts with price, available amount, and order limits.
    """
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        payload = {
            "fiat": fiat,
            "page": 1,
            "rows": 20,
            "tradeType": trade_type,
            "asset": crypto,
            "countries": [],
            "proMerchantAds": False,
            "publisherType": None,
            "payTypes": [],
            "classifies": ["mass", "profession"],
        }
        r = requests.post(url, json=payload, timeout=10)
        raw_data = r.json().get("data", [])

        announcements = []
        for item in raw_data[:top_n]:
            adv = item.get("adv")
            advertiser = item.get("advertiser", {})

            if not adv:
                continue

            announcements.append(
                {
                    "price": float(adv.get("price", 0)),
                    "available_amount": float(adv.get("surplusAmount", 0)),
                    "min_order_limit": float(adv.get("minSingleTransAmount", 0)),
                    "max_order_limit": float(adv.get("maxSingleTransAmount", 0)),
                    "merchant_name": advertiser.get("nickName", "Unknown"),
                }
            )

        return announcements

    except Exception as e:
        print(f"  [scanner_p2p] Error fetching {crypto}/{fiat} {trade_type}: {e}")
        return []


def get_p2p_price_binance(fiat="MXN", crypto="USDT", trade_type="BUY"):
    """Legacy function - returns average price of top-5 announcements."""
    announcements = get_p2p_announcements_binance(fiat, crypto, trade_type, top_n=5)
    if not announcements:
        return None
    prices = [a["price"] for a in announcements if a["price"] > 0]
    return round(np.mean(prices), 4) if prices else None


def scan_p2p_pair(fiat: str, crypto: str = "USDT", log_to_file: bool = True) -> dict:
    """
    Scan a single P2P pair with depth analysis.

    Args:
        fiat: Fiat currency code (MXN, COP, VES, ARS)
        crypto: Crypto asset (default: USDT)
        log_to_file: Whether to log opportunities above threshold

    Returns:
        Dictionary with analysis results and depth data
    """
    print(f"  [scanner_p2p] Scanning {crypto}/{fiat}...")

    # Fetch top-5 buy and sell announcements
    buy_ads = get_p2p_announcements_binance(fiat, crypto, "BUY", top_n=5)
    sell_ads = get_p2p_announcements_binance(fiat, crypto, "SELL", top_n=5)

    if not buy_ads or not sell_ads:
        print(f"  [scanner_p2p] {crypto}/{fiat}: No data available")
        return {
            "market": f"{crypto}/{fiat}",
            "status": "no_data",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    # Calculate average prices
    p2p_buy = round(np.mean([a["price"] for a in buy_ads]), 4)
    p2p_sell = round(np.mean([a["price"] for a in sell_ads]), 4)

    # Calculate merchant spread
    # Formula: (sell_price - buy_price) / buy_price
    # In P2P: buy_ads = users buying (merchant selling) = higher price
    #         sell_ads = users selling (merchant buying) = lower price
    # So: merchant_spread = (p2p_buy - p2p_sell) / p2p_sell

    # Defensive check: ensure p2p_sell > 0
    if p2p_sell <= 0:
        logger.error(f"Invalid p2p_sell price for {crypto}/{fiat}: {p2p_sell}")
        return {
            "market": f"{crypto}/{fiat}",
            "status": "error",
            "error": "Invalid sell price (zero or negative)",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    merchant_spread = round((p2p_buy - p2p_sell) / p2p_sell, 5)

    # Defensive check: detect anomalous spreads
    # Negative spreads indicate inverted buy/sell data or market inefficiency
    # Spreads > 15% are highly anomalous
    spread_abs = abs(merchant_spread)

    if spread_abs > 0.15:
        logger.warning(
            f"⚠️  ANOMALOUS spread detected for {crypto}/{fiat}: "
            f"{merchant_spread*100:.2f}% (buy={p2p_buy}, sell={p2p_sell})"
        )

    # Classify spread
    if spread_abs < 0.02:
        spread_flag = "NORMAL"
    elif spread_abs < 0.10:
        spread_flag = "HIGH"
    else:
        spread_flag = "ANOMALOUS"

    # Calculate depth estimates (total available liquidity)
    buy_depth = sum(a["available_amount"] for a in buy_ads)
    sell_depth = sum(a["available_amount"] for a in sell_ads)
    depth_estimate = round((buy_depth + sell_depth) / 2, 2)

    # Calculate order limits
    buy_min_limits = [a["min_order_limit"] for a in buy_ads if a["min_order_limit"] > 0]
    buy_max_limits = [a["max_order_limit"] for a in buy_ads if a["max_order_limit"] > 0]

    min_order_limit = round(min(buy_min_limits), 2) if buy_min_limits else None
    max_order_limit = round(max(buy_max_limits), 2) if buy_max_limits else None

    # Count unique merchants
    merchant_count = len(set(a["merchant_name"] for a in buy_ads + sell_ads))

    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market": f"{crypto}/{fiat}",
        "p2p_buy_price": p2p_buy,
        "p2p_sell_price": p2p_sell,
        "merchant_spread": merchant_spread,
        "merchant_spread_pct": f"{merchant_spread*100:.3f}%",
        "spread_flag": spread_flag,
        "depth_estimate": depth_estimate,
        "min_order_limit": min_order_limit,
        "max_order_limit": max_order_limit,
        "merchant_count": merchant_count,
        "status": "ok",
    }

    # Get spot price for premium calculation (all LATAM pairs)
    spot_rates = get_fiat_spot_rates([fiat])
    fiat_data = spot_rates.get(fiat, {})
    spot_rate = fiat_data.get("rate")
    rate_source = fiat_data.get("source", "unavailable")

    if spot_rate:
        # Calculate USDT price in local currency using spot rate
        # spot_rate is how many local currency units per 1 USD
        # Assuming USDT ≈ 1 USD, spot_price for USDT/FIAT ≈ spot_rate
        spot_price = spot_rate

        # Calculate P2P premium: (p2p_buy - spot) / spot
        premium = round((p2p_buy - spot_price) / spot_price, 5)

        result["spot_price"] = spot_price
        result["p2p_premium"] = premium
        result["p2p_premium_pct"] = f"{premium*100:.3f}%"
        result["rate_source"] = fiat_data.get("rate_type", "official")
        result["premium_quality"] = (
            "VERIFIED"
            if rate_source in ["open.er-api.com", "frankfurter.app", "cache", "dolarapi.com"]
            else "ESTIMATED"
        )
    else:
        result["spot_price"] = None
        result["p2p_premium"] = None
        result["p2p_premium_pct"] = None
        result["rate_source"] = "unavailable"
        result["premium_quality"] = "UNAVAILABLE"

    # Log to opportunities.jsonl with type "C"
    if log_to_file:
        threshold = _load_threshold()
        edge_pct = abs(merchant_spread * 100)

        # Load fees and calculate friction
        fees = _load_fees()
        total_friction_pct = _calculate_total_friction(fiat, fees)

        # Calculate edge_net: p2p_premium (as %) - total_friction (as %)
        # p2p_premium is stored as decimal (e.g., 0.025 for 2.5%)
        # total_friction_pct is in % (e.g., 0.25 for 0.25%)
        p2p_premium = result.get("p2p_premium")
        if p2p_premium is not None:
            # Convert p2p_premium from decimal to % for calculation
            p2p_premium_pct = float(p2p_premium) * 100
            edge_net_pct = round(p2p_premium_pct - total_friction_pct, 4)
            viable = bool(edge_net_pct > 0)
        else:
            edge_net_pct = None
            viable = False

        opp = {
            "opp_id": f"OPP-C-{uuid.uuid4().hex[:10].upper()}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "C",
            "asset": crypto,
            "market": fiat,
            "venue": "binance_p2p",
            "p2p_buy_price": p2p_buy,
            "p2p_sell_price": p2p_sell,
            "spot_price": result.get("spot_price"),
            "merchant_spread": merchant_spread,
            "spread_flag": spread_flag,
            "p2p_premium": result.get("p2p_premium"),
            "premium_quality": result.get("premium_quality"),
            "rate_source": result.get("rate_source"),
            "total_friction_pct": total_friction_pct,
            "edge_net": edge_net_pct,
            "viable": viable,
            "depth_estimate": depth_estimate,
            "min_order_limit": min_order_limit,
            "max_order_limit": max_order_limit,
            "merchant_count": merchant_count,
            "scanner_id": SCANNER_ID,
            "observe_only": True,
            "operating_hours": _is_operating_hours(fiat),
        }

        # Also add to result dict for return value
        result["total_friction_pct"] = total_friction_pct
        result["edge_net"] = edge_net_pct
        result["viable"] = viable
        result["operating_hours"] = _is_operating_hours(fiat)

        # Always log all pairs — threshold only affects console output
        _append_to_log(opp)
        edge_net_str = f"{edge_net_pct:+.3f}%" if edge_net_pct is not None else "N/A"
        viable_str = "✓" if viable else "✗"
        if edge_pct >= threshold:
            print(
                f"  [scanner_p2p] {crypto}/{fiat}: Buy ${p2p_buy:.4f} | Spread {merchant_spread*100:+.3f}% | EdgeNet {edge_net_str} {viable_str} | Logged"
            )
        else:
            print(
                f"  [scanner_p2p] {crypto}/{fiat}: Buy ${p2p_buy:.4f} | Spread {merchant_spread*100:+.3f}% | EdgeNet {edge_net_str} {viable_str} | Logged (below threshold)"
            )

    return result


def p2p_premium_analysis(log_to_file: bool = True) -> dict:
    """
    Scan P2P markets across multiple LATAM currencies.

    Scans USDT/MXN, USDT/COP, USDT/VES, USDT/ARS with depth analysis.

    Args:
        log_to_file: Whether to log opportunities above threshold

    Returns:
        Dictionary with results for all scanned pairs
    """
    print("📡 Scanning P2P markets across LATAM...")

    pairs = ["MXN", "COP", "VES", "ARS"]
    results = {}

    # Pre-fetch all spot rates to populate cache before scanning individual pairs
    # This ensures all currencies are available in cache for scan_p2p_pair()
    logger.info("Pre-fetching spot rates for all LATAM currencies...")
    get_fiat_spot_rates(pairs)

    for fiat in pairs:
        try:
            pair_result = scan_p2p_pair(fiat, "USDT", log_to_file)
            results[f"USDT/{fiat}"] = pair_result
        except Exception as e:
            print(f"  [scanner_p2p] USDT/{fiat}: Error - {e}")
            results[f"USDT/{fiat}"] = {
                "market": f"USDT/{fiat}",
                "status": "error",
                "error": str(e),
                "ts": datetime.now(timezone.utc).isoformat(),
            }

    # Summary
    successful = sum(1 for r in results.values() if r.get("status") == "ok")
    print(f"📡 P2P scan complete: {successful}/{len(pairs)} pairs successful")

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "scanner_id": SCANNER_ID,
        "pairs_scanned": len(pairs),
        "pairs_successful": successful,
        "results": results,
    }
