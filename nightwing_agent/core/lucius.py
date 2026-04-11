"""
LUCIUS FOX (ATLAS) - Compliance & Jurisdiction Module

Handles jurisdiction rules, operating hours, amount limits, and AML flags
for P2P LATAM arbitrage operations.

Role: Compliance, fiscal rules, jurisdiction validation
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
EXECUTIONS_FILE = BASE_DIR / "storage" / "logs" / "executions.jsonl"
LEDGER_FILE = BASE_DIR / "storage" / "ledger" / "trades.jsonl"

# ───────────────────────── JURISDICTION RULES ─────────────────────────

JURISDICTION_RULES: Dict[str, Dict[str, Any]] = {
    "MXN": {
        "name": "Mexico",
        "enabled": True,
        "timezone": "America/Mexico_City",
        "operating_hours": {
            "start": dt_time(5, 0),
            "end": dt_time(23, 30),
            "is_24_7": False,
        },
        "limits": {
            "max_single_transfer_local": 50_000,
            "max_single_transfer_usd": 2_500,
            "daily_limit_local": 200_000,
            "daily_limit_usd": 10_000,
        },
        "allowed_methods": ["SPEI", "bank_transfer"],
        "aml": {
            "flag_threshold_local": 10_000,
            "flag_threshold_usd": 500,
        },
    },
    "ARS": {
        "name": "Argentina",
        "enabled": True,
        "timezone": "America/Argentina/Buenos_Aires",
        "operating_hours": {
            "start": dt_time(0, 0),
            "end": dt_time(23, 59),
            "is_24_7": True,
        },
        "limits": {
            "max_single_transfer_local": None,
            "max_single_transfer_usd": 500,
            "daily_limit_local": None,
            "daily_limit_usd": 2_000,
        },
        "allowed_methods": ["CVU", "bank_transfer"],
        "aml": {
            "flag_threshold_local": None,
            "flag_threshold_usd": 1_000,
        },
    },
    "COP": {
        "name": "Colombia",
        "enabled": False,
        "timezone": "America/Bogota",
        "operating_hours": {
            "start": dt_time(0, 0),
            "end": dt_time(23, 59),
            "is_24_7": True,
        },
        "limits": {
            "max_single_transfer_local": 5_000_000,
            "max_single_transfer_usd": 1_200,
            "daily_limit_local": 10_000_000,
            "daily_limit_usd": 2_400,
        },
        "allowed_methods": ["PSE", "bank_transfer"],
        "aml": {
            "flag_threshold_local": 10_000_000,
            "flag_threshold_usd": 2_400,
        },
    },
    "VES": {
        "name": "Venezuela",
        "enabled": False,
        "timezone": "America/Caracas",
        "operating_hours": {
            "start": dt_time(0, 0),
            "end": dt_time(23, 59),
            "is_24_7": True,
        },
        "limits": {
            "max_single_transfer_local": None,
            "max_single_transfer_usd": 100,
            "daily_limit_local": None,
            "daily_limit_usd": 500,
        },
        "allowed_methods": ["bank_transfer", "mobile_payment"],
        "aml": {
            "flag_threshold_local": None,
            "flag_threshold_usd": 200,
        },
    },
}


def _get_local_time(tz_name: str) -> datetime:
    if pytz is not None:
        tz = pytz.timezone(tz_name)
        return datetime.now(tz)
    else:
        logger.warning(f"pytz not installed. Using UTC instead of {tz_name}")
        return datetime.now(timezone.utc)


def is_operating_hours(fiat: str) -> bool:
    rules = JURISDICTION_RULES.get(fiat.upper())
    if not rules:
        logger.warning(f"No jurisdiction rules for {fiat}")
        return False

    hours = rules.get("operating_hours", {})
    if hours.get("is_24_7", False):
        return True

    tz_name = rules.get("timezone", "UTC")
    local_now = _get_local_time(tz_name)
    current_time = local_now.time()

    start = hours.get("start", dt_time(0, 0))
    end = hours.get("end", dt_time(23, 59))

    if start <= end:
        return start <= current_time <= end
    else:
        return current_time >= start or current_time <= end


def _read_exposure_from_file(filepath: Path, fiat: str, today: str) -> float:
    """Read daily exposure from a JSONL file."""
    if not filepath.exists():
        return 0.0

    total = 0.0
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)

                    record_fiat = record.get("fiat", "")
                    if record_fiat.upper() != fiat.upper():
                        continue

                    ts = record.get("ts") or record.get("timestamp", "")
                    if not ts[:10] == today:
                        continue

                    amount = record.get("executed_amount_usd")
                    if amount is None:
                        if record.get("action") in ("SIMULATED_TRADE", "MANUAL_TRADE", "EXECUTED"):
                            amount = record.get("amount_usd", 0)
                        else:
                            amount = 0
                    if amount and amount > 0:
                        total += amount

                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")

    return total


def get_daily_exposure(fiat: str, session: Optional[Any] = None) -> float:
    """
    Calculate total USD traded today for a specific fiat pair.
    Reads from BOTH executions.jsonl AND HARVEY ledger, takes the max.
    """
    today = datetime.now(timezone.utc).date().isoformat()

    exposure_executions = _read_exposure_from_file(EXECUTIONS_FILE, fiat, today)
    exposure_ledger = _read_exposure_from_file(LEDGER_FILE, fiat, today)

    # Take the max to be conservative — never undercount exposure
    total = max(exposure_executions, exposure_ledger)
    return round(total, 2)


def check_jurisdiction(
    fiat: str,
    amount_usd: float,
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    fiat = fiat.upper()
    result = {
        "approved": True,
        "blocked_by": None,
        "warnings": [],
        "checks": {
            "jurisdiction_enabled": None,
            "operating_hours": None,
            "single_amount_limit": None,
            "daily_exposure_limit": None,
            "aml_flag": None,
        },
        "daily_exposure_usd": 0.0,
    }

    rules = JURISDICTION_RULES.get(fiat)
    if not rules:
        result["approved"] = False
        result["blocked_by"] = f"UNKNOWN_JURISDICTION: {fiat}"
        result["checks"]["jurisdiction_enabled"] = False
        return result

    if not rules.get("enabled", False):
        result["approved"] = False
        result["blocked_by"] = f"JURISDICTION_DISABLED: {fiat} ({rules['name']})"
        result["checks"]["jurisdiction_enabled"] = False
        return result
    result["checks"]["jurisdiction_enabled"] = True

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

    limits = rules.get("limits", {})
    max_single_usd = limits.get("max_single_transfer_usd", float("inf"))
    if amount_usd > max_single_usd:
        result["approved"] = False
        result["blocked_by"] = f"EXCEEDS_SINGLE_LIMIT: ${amount_usd:.2f} > ${max_single_usd:.2f} USD"
        result["checks"]["single_amount_limit"] = False
        return result
    result["checks"]["single_amount_limit"] = True

    daily_limit_usd = limits.get("daily_limit_usd", float("inf"))
    current_exposure = get_daily_exposure(fiat, session)
    result["daily_exposure_usd"] = current_exposure

    if current_exposure + amount_usd > daily_limit_usd:
        result["approved"] = False
        remaining = max(0, daily_limit_usd - current_exposure)
        result["blocked_by"] = (
            f"EXCEEDS_DAILY_LIMIT: "
            f"current ${current_exposure:.2f} + ${amount_usd:.2f} > ${daily_limit_usd:.2f} USD "
            f"(remaining: ${remaining:.2f})"
        )
        result["checks"]["daily_exposure_limit"] = False
        return result
    result["checks"]["daily_exposure_limit"] = True

    aml = rules.get("aml", {})
    aml_threshold_usd = aml.get("flag_threshold_usd", float("inf"))
    if amount_usd > aml_threshold_usd:
        result["warnings"].append(
            f"AML_FLAG: Amount ${amount_usd:.2f} exceeds flag threshold ${aml_threshold_usd:.2f} USD"
        )
        result["checks"]["aml_flag"] = "FLAGGED"
    else:
        result["checks"]["aml_flag"] = "CLEAR"

    return result


def get_jurisdiction_summary(fiat: str) -> Dict[str, Any]:
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
        "currently_open": is_operating_hours(fiat),
    }


if __name__ == "__main__":
    import json as _json

    print("LUCIUS FOX - Jurisdiction Check")
    print("=" * 50)
    result = check_jurisdiction("MXN", 500)
    print(_json.dumps(result, indent=2, default=str))
