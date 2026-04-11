"""
Network Status Checker

Before recommending cross-platform transfers, verify:
- Is USDT withdrawal open on source exchange?
- Which network is cheapest? (TRC20 vs ERC20 vs BEP20)
- Current withdrawal fee
- Estimated arrival time

Sources (public endpoints, no API key needed):
- Binance: System status only (detailed needs API key)
- OKX: GET /api/v5/asset/currencies
- Bybit: GET /v5/asset/coin/query-info (needs API key)

For now, uses hardcoded typical values + live status check where possible.
"""

import json
import urllib.request
import ssl
from datetime import datetime, timezone
from typing import Dict, Any

TIMEOUT = 10
USER_AGENT = "batman-flow-engine/1.0"

# Typical withdrawal fees (USDT) — updated periodically
TYPICAL_FEES = {
    "binance": {
        "TRC20": {"fee_usdt": 1.0, "min_withdrawal": 10.0, "est_time_min": 5},
        "ERC20": {"fee_usdt": 3.5, "min_withdrawal": 10.0, "est_time_min": 15},
        "BEP20": {"fee_usdt": 0.29, "min_withdrawal": 10.0, "est_time_min": 5},
        "SOL": {"fee_usdt": 1.0, "min_withdrawal": 10.0, "est_time_min": 2},
        "MATIC": {"fee_usdt": 1.0, "min_withdrawal": 10.0, "est_time_min": 5},
    },
    "okx": {
        "TRC20": {"fee_usdt": 0.0, "min_withdrawal": 0.1, "est_time_min": 5},
        "ERC20": {"fee_usdt": 0.0, "min_withdrawal": 0.1, "est_time_min": 15},
        "Arbitrum": {"fee_usdt": 0.1, "min_withdrawal": 0.1, "est_time_min": 3},
        "Optimism": {"fee_usdt": 0.1, "min_withdrawal": 0.1, "est_time_min": 3},
        "SOL": {"fee_usdt": 0.0, "min_withdrawal": 0.1, "est_time_min": 2},
    },
    "bybit": {
        "TRC20": {"fee_usdt": 1.0, "min_withdrawal": 10.0, "est_time_min": 5},
        "ERC20": {"fee_usdt": 3.0, "min_withdrawal": 10.0, "est_time_min": 15},
        "BEP20": {"fee_usdt": 0.3, "min_withdrawal": 10.0, "est_time_min": 5},
        "Arbitrum": {"fee_usdt": 0.5, "min_withdrawal": 10.0, "est_time_min": 3},
    },
    "bitso": {
        "TRC20": {"fee_usdt": 2.5, "min_withdrawal": 10.0, "est_time_min": 10},
        "ERC20": {"fee_usdt": 5.0, "min_withdrawal": 10.0, "est_time_min": 20},
    },
}


def _fetch_json(url, params=None):
    if params:
        url = f"{url}?{'&'.join(f'{k}={v}' for k,v in params.items())}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def check_binance_system():
    """Check Binance system status."""
    data = _fetch_json("https://api.binance.com/sapi/v1/system/status")
    if data:
        return {"status": "ok" if data.get("status") == 0 else "maintenance"}
    return {"status": "unknown"}


def check_okx_currencies():
    """Check OKX currency withdrawal status for USDT."""
    data = _fetch_json("https://www.okx.com/api/v5/asset/currencies", {"ccy": "USDT"})
    if data and data.get("code") == "0":
        networks = {}
        for item in data.get("data", []):
            chain = item.get("chain", "unknown")
            networks[chain] = {
                "can_withdraw": item.get("canWd", False),
                "can_deposit": item.get("canDep", False),
                "fee": float(item.get("minFee", 0)),
                "min_wd": float(item.get("minWd", 0)),
            }
        return {"status": "ok", "networks": networks}
    return {"status": "error"}


def get_cheapest_route(source: str, destination: str) -> Dict[str, Any]:
    """Find the cheapest USDT transfer route between two exchanges."""
    source_fees = TYPICAL_FEES.get(source, {})
    dest_fees = TYPICAL_FEES.get(destination, {})

    # Find common networks
    common_networks = set(source_fees.keys()) & set(dest_fees.keys())

    if not common_networks:
        return {"status": "no_common_network", "source": source, "destination": destination}

    routes = []
    for network in common_networks:
        src = source_fees[network]
        routes.append(
            {
                "network": network,
                "fee_usdt": src["fee_usdt"],
                "min_withdrawal": src["min_withdrawal"],
                "est_time_min": src["est_time_min"],
            }
        )

    routes.sort(key=lambda x: x["fee_usdt"])

    return {
        "status": "ok",
        "source": source,
        "destination": destination,
        "cheapest": routes[0],
        "all_routes": routes,
    }


def full_network_check() -> Dict[str, Any]:
    """Run full network status check."""
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exchanges": {},
    }

    # Binance
    result["exchanges"]["binance"] = check_binance_system()

    # OKX
    result["exchanges"]["okx"] = check_okx_currencies()

    # Cheapest routes
    result["cheapest_routes"] = {}
    pairs = [
        ("binance", "okx"),
        ("okx", "binance"),
        ("binance", "bybit"),
        ("bybit", "binance"),
        ("binance", "bitso"),
        ("bitso", "binance"),
    ]
    for src, dst in pairs:
        key = f"{src}_to_{dst}"
        result["cheapest_routes"][key] = get_cheapest_route(src, dst)

    return result


if __name__ == "__main__":
    print("=" * 70)
    print("Network Status Checker")
    print("=" * 70)

    result = full_network_check()

    print("\nExchange Status:")
    for ex, status in result["exchanges"].items():
        print(f"  {ex}: {status.get('status', 'unknown')}")

    print("\nCheapest Transfer Routes:")
    for key, route in result["cheapest_routes"].items():
        if route["status"] == "ok":
            c = route["cheapest"]
            print(f"  {key}: {c['network']} — ${c['fee_usdt']} USDT, ~{c['est_time_min']} min")
