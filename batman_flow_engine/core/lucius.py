"""
LUCIUS FOX (ATLAS) - Compliance & Jurisdiction Module

Handles jurisdiction rules, operating hours, amount limits, and AML flags
for P2P LATAM arbitrage operations.

Role: Compliance, fiscal rules, jurisdiction validation
Status: Active

Usage:
    from core.lucius import check_jurisdiction, is_operating_hours, get_daily_exposure

    result = check_jurisdiction("MXN", amount_usd=500, session=None)
    if not result["approved"]:
        print(f"Blocked by: {result['blocked_by']}")
"""

import json
import logging
from datetime import datetime, timezone, time as dt_time
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger("lucius")

BASE_DIR = Path(__file__).resolve().parent.parent
EXECUTIONS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

# ───────────────────────── JURISDICTION RULES ─────────────────────────

JURISDICTION_RULES: Dict[str, Dict[str, Any]] = {
    "MXN": {
        "name": "Mexico",
        "enabled": True,
        "timezone": "America/Mexico_City",
        # SPEI hours: 05:00-23:30 Mexico City time
        "operating_hours": {
            "start": dt_time(5, 0),
            "end": dt_time(23, 30),
            "is_24_7": False,
        },
        "limits": {
            "max_single_transfer_local": 50_000,  # MXN
            "max_single_transfer_usd": 2_500,
            "daily_limit_local": 200_000,  # MXN
            "daily_limit_usd": 10_000,
        },
        "allowed_methods": ["SPEI", "bank_transfer"],
        "aml": {
            "flag_threshold_local": 10_000,  # MXN - flag if single op exceeds
            "flag_threshold_usd": 500,
            "reporting_required_local": 50_000,  # MXN - requires reporting
        },
        "notes": "SPEI has limited hours. AML threshold is relatively low.",
    },
    "ARS": {
        "name": "Argentina",
        "enabled": True,
        "timezone": "America/Argentina/Buenos_Aires",
        # 24/7 for crypto P2P
        "operating_hours": {
            "start": dt_time(0, 0),
            "end": dt_time(23, 59),
            "is_24_7": True,
        },
        "limits": {
            "max_single_transfer_local": None,  # Use USD equivalent
            "max_single_transfer_usd": 500,
            "daily_limit_local": None,
            "daily_limit_usd": 2_000,
        },
        "allowed_methods": ["CVU", "bank_transfer"],
        "aml": {
            "flag_threshold_local": None,
            "flag_threshold_usd": 1_000,
            "reporting_required_local": None,
        },
        "notes": "High volatility. USD-denominated limits. Blue dollar rate considerations.",
    },
    "COP": {
        "name": "Colombia",
        "enabled": False,  # Disabled but rules defined
        "timezone": "America/Bogota",
        "operating_hours": {
            "start": dt_time(0, 0),
            "end": dt_time(23, 59),
            "is_24_7": True,
        },
        "limits": {
            "max_single_transfer_local": 5_000_000,  # COP (~$1,200 USD)
            "max_single_transfer_usd": 1_200,
            "daily_limit_local": 10_000_000,  # COP
            "daily_limit_usd": 2_400,
        },
        "allowed_methods": ["PSE", "bank_transfer"],
        "aml": {
            "flag_threshold_local": 10_000_000,  # COP
            "flag_threshold_usd": 2_400,
            "reporting_required_local": 50_000_000,  # COP
        },
        "notes": "Currently disabled due to negative edge_net.",
    },
    "VES": {
        "name": "Venezuela",
        "enabled": False,  # Disabled but rules defined
        "timezone": "America/Caracas",
        "operating_hours": {
            "start": dt_time(0, 0),
            "end": dt_time(23, 59),
            "is_24_7": True,
        },
        "limits": {
            "max_single_transfer_local": None,  # Use USD equivalent
            "max_single_transfer_usd": 100,  # Very low due to volatility
            "daily_limit_local": None,
            "daily_limit_usd": 500,
        },
        "allowed_methods": ["bank_transfer", "mobile_payment"],
        "aml": {
            "flag_threshold_local": None,
            "flag_threshold_usd": 200,
            "reporting_required_local": None,
        },
        "notes": "Disabled. Parallel rate market. High spread anomalies detected.",
    },
}


def _get_local_time(tz_name: str) -> datetime:
    """
    Get current time in specified timezone.

    Args:
        tz_name: Timezone name (e.g., 'America/Mexico_City')

    Returns:
        Current datetime in specified timezone
    """
    if pytz is not None:
        tz = pytz.timezone(tz_name)
        return datetime.now(tz)
    else:
        # Fallback: use UTC and log warning
        logger.warning(f"pytz not installed. Using UTC instead of {tz_name}")
        return datetime.now(timezone.utc)


def is_operating_hours(fiat: str) -> bool:
    """
    Check if current time is within allowed operating hours for fiat currency.

    Args:
        fiat: Currency code (MXN, COP, VES, ARS)

    Returns:
        True if current time is within operating hours, False otherwise

    Example:
        >>> is_operating_hours("MXN")  # During SPEI hours
        True
        >>> is_operating_hours("MXN")  # At 3am Mexico City
        False
    """
    rules = JURISDICTION_RULES.get(fiat.upper())
    if not rules:
        logger.warning(f"No jurisdiction rules for {fiat}")
        return False

    hours = rules.get("operating_hours", {})

    # 24/7 markets are always open
    if hours.get("is_24_7", False):
        return True

    tz_name = rules.get("timezone", "UTC")
    local_now = _get_local_time(tz_name)
    current_time = local_now.time()

    start = hours.get("start", dt_time(0, 0))
    end = hours.get("end", dt_time(23, 59))

    # Handle same-day range (e.g., 05:00 - 23:30)
    if start <= end:
        return start <= current_time <= end
    else:
        # Handle overnight range (e.g., 22:00 - 06:00) - unlikely but covered
        return current_time >= start or current_time <= end


def _get_daily_exposure_jsonl(fiat: str) -> float:
    """
    Read daily USD exposure from opportunities.jsonl (JSONL path).

    Used internally as a divergence-check reference against batman.db.
    Not intended as a primary source of truth.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    total_usd = 0.0

    if not EXECUTIONS_FILE.exists():
        return 0.0

    try:
        with open(EXECUTIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    opp = json.loads(line)
                    market = opp.get("market", "")
                    if market.upper() != fiat.upper():
                        continue
                    ts = opp.get("ts", "")
                    if not ts.startswith(today):
                        continue
                    depth = opp.get("depth_estimate", 0)
                    if depth and depth > 0:
                        total_usd += min(depth, 1000)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error("Error reading executions file: %s", e)

    return round(total_usd, 2)


def get_daily_exposure(fiat: str, session: Optional[Any] = None) -> float:
    """
    Return daily USD exposure for the given fiat market.

    Uses HARVEY (batman.db) as single source of truth.
    Compares against JSONL and logs a warning if sources diverge by more than $1.
    Falls back to JSONL if HARVEY is unavailable.

    Args:
        fiat: Currency code (MXN, COP, VES, ARS)
        session: Reserved for future database integration (currently unused).

    Returns:
        Total USD equivalent exposure today for this pair.

    Example:
        >>> get_daily_exposure("MXN")
        800.0
    """
    db_exposure: Optional[float] = None
    try:
        from core.harvey import daily_exposure as _harvey_daily_exposure

        db_exposure = _harvey_daily_exposure(fiat)
    except Exception as exc:
        logger.warning("HARVEY daily_exposure unavailable (%s) — falling back to JSONL", exc)

    jsonl_exposure = _get_daily_exposure_jsonl(fiat)

    if db_exposure is not None:
        if abs(db_exposure - jsonl_exposure) > 1.0:
            logger.warning(
                "EXPOSURE DIVERGENCE [%s]: harvey_db=%.2f jsonl=%.2f — using harvey_db as source of truth",
                fiat.upper(),
                db_exposure,
                jsonl_exposure,
            )
        return db_exposure

    return jsonl_exposure


def check_jurisdiction(
    fiat: str,
    amount_usd: float,
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Check jurisdiction compliance for a proposed transaction.

    Args:
        fiat: Currency code (MXN, COP, VES, ARS)
        amount_usd: Transaction amount in USD
        session: Optional session object (for future database integration)

    Returns:
        Dictionary with:
            - approved: bool - True if transaction is approved
            - blocked_by: str|None - Reason for blocking
            - warnings: list - List of warning messages
            - jurisdiction: dict - Applied jurisdiction rules
            - checks: dict - Results of individual checks

    Example:
        >>> result = check_jurisdiction("MXN", amount_usd=500)
        >>> if not result["approved"]:
        ...     print(f"Blocked: {result['blocked_by']}")
    """
    fiat = fiat.upper()
    result = {
        "approved": True,
        "blocked_by": None,
        "warnings": [],
        "jurisdiction": None,
        "checks": {
            "jurisdiction_enabled": None,
            "operating_hours": None,
            "single_amount_limit": None,
            "daily_exposure_limit": None,
            "aml_flag": None,
        },
        "daily_exposure_usd": 0.0,
    }

    # Get jurisdiction rules
    rules = JURISDICTION_RULES.get(fiat)
    if not rules:
        result["approved"] = False
        result["blocked_by"] = f"UNKNOWN_JURISDICTION: {fiat}"
        result["checks"]["jurisdiction_enabled"] = False
        return result

    result["jurisdiction"] = {
        "fiat": fiat,
        "name": rules["name"],
        "enabled": rules["enabled"],
        "timezone": rules.get("timezone"),
    }

    # Check 1: Jurisdiction enabled
    if not rules.get("enabled", False):
        result["approved"] = False
        result["blocked_by"] = f"JURISDICTION_DISABLED: {fiat} ({rules['name']})"
        result["checks"]["jurisdiction_enabled"] = False
        return result
    result["checks"]["jurisdiction_enabled"] = True

    # Check 2: Operating hours
    in_hours = is_operating_hours(fiat)
    result["checks"]["operating_hours"] = in_hours
    if not in_hours:
        result["approved"] = False
        hours = rules.get("operating_hours", {})
        start = hours.get("start", dt_time(0, 0))
        end = hours.get("end", dt_time(23, 59))
        result["blocked_by"] = (
            f"OUTSIDE_OPERATING_HOURS: {fiat} "
            f"(allowed: {start.strftime('%H:%M')}-{end.strftime('%H:%M')} {rules.get('timezone', 'local')})"
        )
        return result

    # Check 3: Single amount limit
    limits = rules.get("limits", {})
    max_single_usd = limits.get("max_single_transfer_usd", float("inf"))
    if amount_usd > max_single_usd:
        result["approved"] = False
        result["blocked_by"] = f"EXCEEDS_SINGLE_LIMIT: ${amount_usd:.2f} > ${max_single_usd:.2f} USD"
        result["checks"]["single_amount_limit"] = False
        return result
    result["checks"]["single_amount_limit"] = True

    # Check 4: Daily exposure limit
    daily_limit_usd = limits.get("daily_limit_usd", float("inf"))
    current_exposure = get_daily_exposure(fiat, session)
    result["daily_exposure_usd"] = current_exposure

    if current_exposure + amount_usd > daily_limit_usd:
        result["approved"] = False
        remaining = max(0, daily_limit_usd - current_exposure)
        result["blocked_by"] = (
            f"EXCEEDS_DAILY_LIMIT: "
            f"current ${current_exposure:.2f} + ${amount_usd:.2f} > ${daily_limit_usd:.2f} USD limit "
            f"(remaining: ${remaining:.2f})"
        )
        result["checks"]["daily_exposure_limit"] = False
        return result
    result["checks"]["daily_exposure_limit"] = True

    # Check 5: AML flags (warnings, not blocking)
    aml = rules.get("aml", {})
    aml_threshold_usd = aml.get("flag_threshold_usd", float("inf"))
    if amount_usd > aml_threshold_usd:
        result["warnings"].append(
            f"AML_FLAG: Amount ${amount_usd:.2f} exceeds flag threshold ${aml_threshold_usd:.2f} USD"
        )
        result["checks"]["aml_flag"] = "FLAGGED"
    else:
        result["checks"]["aml_flag"] = "CLEAR"

    # Add method warnings
    allowed_methods = rules.get("allowed_methods", [])
    if allowed_methods:
        result["warnings"].append(f"ALLOWED_METHODS: {', '.join(allowed_methods)}")

    # Add notes as info
    notes = rules.get("notes")
    if notes:
        result["warnings"].append(f"INFO: {notes}")

    return result


def get_jurisdiction_summary(fiat: str) -> Dict[str, Any]:
    """
    Get a summary of jurisdiction rules for a fiat currency.

    Args:
        fiat: Currency code (MXN, COP, VES, ARS)

    Returns:
        Dictionary with jurisdiction summary
    """
    fiat = fiat.upper()
    rules = JURISDICTION_RULES.get(fiat)
    if not rules:
        return {"fiat": fiat, "status": "UNKNOWN"}

    hours = rules.get("operating_hours", {})
    limits = rules.get("limits", {})

    return {
        "fiat": fiat,
        "name": rules["name"],
        "enabled": rules["enabled"],
        "is_24_7": hours.get("is_24_7", False),
        "operating_hours": (
            "24/7"
            if hours.get("is_24_7")
            else f"{hours.get('start', dt_time(0,0)).strftime('%H:%M')}-{hours.get('end', dt_time(23,59)).strftime('%H:%M')}"
        ),
        "timezone": rules.get("timezone"),
        "max_single_usd": limits.get("max_single_transfer_usd"),
        "daily_limit_usd": limits.get("daily_limit_usd"),
        "allowed_methods": rules.get("allowed_methods", []),
        "currently_open": is_operating_hours(fiat),
    }


def check_all_jurisdictions() -> Dict[str, Dict[str, Any]]:
    """
    Get status of all configured jurisdictions.

    Returns:
        Dictionary mapping fiat codes to their current status
    """
    return {fiat: get_jurisdiction_summary(fiat) for fiat in JURISDICTION_RULES.keys()}


# ───────────────────────── CLI TEST ─────────────────────────

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("LUCIUS FOX (ATLAS) - Jurisdiction Status")
    print("=" * 60)

    for fiat, summary in check_all_jurisdictions().items():
        status = "ENABLED" if summary["enabled"] else "DISABLED"
        open_status = "OPEN" if summary["currently_open"] else "CLOSED"
        print(f"\n{fiat} ({summary['name']}):")
        print(f"  Status: {status}")
        print(f"  Hours: {summary['operating_hours']} ({open_status})")
        print(f"  Max Single: ${summary['max_single_usd']} USD")
        print(f"  Daily Limit: ${summary['daily_limit_usd']} USD")
        print(f"  Methods: {', '.join(summary['allowed_methods'])}")

    print("\n" + "=" * 60)
    print("Testing check_jurisdiction('MXN', 500)")
    print("=" * 60)
    result = check_jurisdiction("MXN", 500)
    print(json.dumps(result, indent=2, default=str))
