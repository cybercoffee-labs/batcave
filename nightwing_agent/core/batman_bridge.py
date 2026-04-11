"""
BATMAN BRIDGE — Reads latest verified data from Batman Flow Engine.

Source: batman_flow_engine/storage/logs/opportunities.jsonl
Rule: Bridge is PRIMARY source. market_data.py is FALLBACK only.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("nightwing.batman_bridge")

BATMAN_OPPS = Path.home() / "Projects" / "batcave" / "batman_flow_engine" / "storage" / "logs" / "opportunities.jsonl"
BATMAN_LATEST = Path.home() / "Projects" / "batcave" / "batman_flow_engine" / "storage" / "latest.json"
MAX_STALENESS_SECONDS = 1200  # 20 minutes


def fetch_from_batman(pair: str = "MXN") -> dict:
    """
    Read the latest P2P opportunity for a given fiat pair from Batman.

    Args:
        pair: Fiat currency code (MXN, ARS, COP, VES)

    Returns:
        dict with opportunity data or error status
    """
    if not BATMAN_OPPS.exists():
        logger.warning(f"Batman opportunities file not found: {BATMAN_OPPS}")
        return {"status": "error", "error": "batman_opps_not_found"}

    # Read last 50 lines and find latest match for this pair
    try:
        lines = BATMAN_OPPS.read_text().strip().split("\n")
        recent = lines[-50:] if len(lines) > 50 else lines

        match = None
        for line in reversed(recent):
            try:
                record = json.loads(line)
                if record.get("market") == pair and record.get("type") == "C":
                    match = record
                    break
            except json.JSONDecodeError:
                continue

        if not match:
            logger.warning(f"No P2P record found for {pair}")
            return {"status": "error", "error": f"no_record_for_{pair}"}

        # Check staleness
        ts = datetime.fromisoformat(match["ts"])
        age = (datetime.now(timezone.utc) - ts).total_seconds()

        if age > MAX_STALENESS_SECONDS:
            logger.warning(f"Batman data stale: {pair} is {age:.0f}s old (max {MAX_STALENESS_SECONDS}s)")
            return {
                "status": "stale",
                "error": f"data_age_{age:.0f}s",
                "age_seconds": age,
                "data": match,
            }

        logger.info(
            f"Batman bridge: {pair} edge_net={match.get('edge_net')}% viable={match.get('viable')} age={age:.0f}s"
        )

        payload = {
            "status": "ok",
            "fiat": pair,
            "market": f"USDT/{pair}",
            "p2p_premium": match.get("p2p_premium"),
            "edge_net": match.get("edge_net"),
            "viable": match.get("viable", False),
            "total_friction_pct": match.get("total_friction_pct"),
            "spot_price": match.get("spot_price"),
            "p2p_buy_price": match.get("p2p_buy_price"),
            "p2p_sell_price": match.get("p2p_sell_price"),
            "depth_estimate": match.get("depth_estimate"),
            "merchant_count": match.get("merchant_count"),
            "premium_quality": match.get("premium_quality"),
            "rate_source": match.get("rate_source"),
            "spread_flag": match.get("spread_flag"),
            "age_seconds": age,
            "batman_ts": match["ts"],
            "opp_id": match.get("opp_id"),
        }

        # Preserve richer Batman depth fields when they are present in the source record.
        for field in (
            "buy_offers",
            "sell_offers",
            "best_buy",
            "best_sell",
            "min_order_limit",
            "max_order_limit",
            "merchant_count",
        ):
            if field in match:
                payload[field] = match[field]

        return payload

    except Exception as e:
        logger.error(f"Batman bridge error: {e}")
        return {"status": "error", "error": str(e)}


def is_batman_alive() -> bool:
    """Check if Batman has recent data (latest.json < 20 min old)."""
    if not BATMAN_LATEST.exists():
        return False
    try:
        data = json.loads(BATMAN_LATEST.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age < MAX_STALENESS_SECONDS
    except Exception:
        return False


def fetch_best_opportunity(
    fiats: list = None,
    types: list = None,
) -> dict:
    """
    Read last 100 lines of opportunities.jsonl.
    Filter by fiat/types. Return highest edge_net that is fresh (<1200s).

    Args:
        fiats: List of fiat codes to filter (e.g., ["MXN", "ARS"]).
               If None, accepts all fiats.
        types: List of opportunity types to filter (e.g., ["C", "D", "F"]).
               If None, accepts all types.

    Returns:
        dict with best opportunity data or error status:
        {
            "status": "ok" | "error" | "no_match",
            "opp_id": str,
            "type": str,
            "edge_net": float,
            "fiat": str,
            "age_seconds": float,
            ...
        }
    """
    if fiats is None:
        fiats = ["MXN"]

    if not BATMAN_OPPS.exists():
        logger.warning(f"Batman opportunities file not found: {BATMAN_OPPS}")
        return {"status": "error", "error": "batman_opps_not_found"}

    try:
        lines = BATMAN_OPPS.read_text().strip().split("\n")
        recent = lines[-100:] if len(lines) > 100 else lines

        candidates = []
        now = datetime.now(timezone.utc)

        for line in recent:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Filter by type
            if types is not None:
                if record.get("type") not in types:
                    continue

            # Filter by fiat (check market, fiat, buy_fiat fields)
            fiat_match = False
            for fiat_field in ("market", "fiat", "buy_fiat"):
                field_val = record.get(fiat_field)
                if field_val and field_val in fiats:
                    fiat_match = True
                    break
            if not fiat_match:
                continue

            # Check freshness
            ts_str = record.get("ts")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                age = (now - ts).total_seconds()
            except Exception:
                continue

            if age > MAX_STALENESS_SECONDS:
                continue

            # Get edge_net
            edge_net = record.get("edge_net")
            if edge_net is None:
                # Try alternative edge fields
                for alt in ("spread_pct", "p2p_premium", "merchant_spread_pct", "cross_premium_spread"):
                    if record.get(alt) is not None:
                        edge_net = record[alt]
                        break

            if edge_net is None:
                continue

            candidates.append(
                {
                    "record": record,
                    "edge_net": float(edge_net),
                    "age_seconds": age,
                }
            )

        if not candidates:
            logger.info("No fresh opportunities match fiats=%s types=%s", fiats, types)
            return {"status": "no_match", "fiats": fiats, "types": types}

        # Find best by edge_net
        best = max(candidates, key=lambda x: x["edge_net"])
        record = best["record"]
        age = best["age_seconds"]

        # Determine fiat
        detected_fiat = record.get("market") or record.get("fiat") or record.get("buy_fiat") or "UNKNOWN"

        logger.info(
            "Best opportunity: type=%s fiat=%s edge_net=%.2f%% age=%.0fs opp_id=%s",
            record.get("type"),
            detected_fiat,
            best["edge_net"],
            age,
            record.get("opp_id"),
        )

        return {
            "status": "ok",
            "opp_id": record.get("opp_id"),
            "type": record.get("type"),
            "scanner_id": record.get("scanner_id"),
            "fiat": detected_fiat,
            "edge_net": best["edge_net"],
            "viable": record.get("viable", False),
            "age_seconds": age,
            "batman_ts": record.get("ts"),
            "raw_record": record,
        }

    except Exception as e:
        logger.error(f"fetch_best_opportunity error: {e}")
        return {"status": "error", "error": str(e)}
