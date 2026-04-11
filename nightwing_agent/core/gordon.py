"""
GORDON (SHIELD) — Security & Protection Module for Nightwing

4 core protections before LIVE trading:
1. Circuit breaker — daily loss limit
2. Batman heartbeat — data freshness check
3. Spread anomaly detector — reject suspicious edges
4. Max daily exposure — cap total daily risk

GORDON runs AFTER LUCIUS (compliance) and BEFORE execution decisions.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("nightwing.gordon")

BASE_DIR = Path(__file__).resolve().parent.parent
LEDGER_FILE = BASE_DIR / "storage" / "ledger" / "trades.jsonl"
KILL_SWITCH_FILE = BASE_DIR / "storage" / "KILL_SWITCH"
GORDON_AUDIT_FILE = BASE_DIR / "storage" / "logs" / "gordon_audit.jsonl"
BATMAN_LATEST = Path.home() / "Projects" / "batcave" / "batman_flow_engine" / "storage" / "latest.json"

DEFAULT_LIMITS = {
    "max_daily_loss_pct": -2.0,
    "max_consecutive_passes": 10,
    "max_edge_anomaly_pct": 3.0,
    "min_edge_sanity_pct": -5.0,
    "batman_max_silence_seconds": 2400,
    "max_daily_exposure_usd": 10000.0,
    "max_single_trade_usd": 2500.0,
}


def _utc_now():
    return datetime.now(timezone.utc)


def _read_ledger():
    if not LEDGER_FILE.exists():
        return []
    today = _utc_now().strftime("%Y-%m-%d")
    records = []
    for line in LEDGER_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if (r.get("timestamp") or "")[:10] == today:
                records.append(r)
        except json.JSONDecodeError:
            continue
    return records


def _log_event(event_type, details):
    try:
        GORDON_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": _utc_now().isoformat(), "event_type": event_type, "details": details}
        with open(GORDON_AUDIT_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"Gordon audit write failed: {e}")


def check_circuit_breaker(limits=None):
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    records = _read_ledger()
    if not records:
        return {"approved": True, "check": "circuit_breaker", "daily_trades": 0}

    total_pnl = 0.0
    total_traded = 0.0
    for r in records:
        if r.get("decision") == "OPPORTUNITY" and r.get("action") in ("SIMULATED_TRADE", "LOGGED", "EXECUTED"):
            edge = r.get("edge_net", 0) or 0
            amount = r.get("amount_usd", 0) or 0
            total_pnl += amount * (edge / 100)
            total_traded += amount

    if total_traded == 0:
        return {"approved": True, "check": "circuit_breaker", "daily_pnl_usd": 0, "daily_trades": len(records)}

    daily_pnl_pct = (total_pnl / total_traded) * 100
    if daily_pnl_pct < lim["max_daily_loss_pct"]:
        _log_event(
            "circuit_breaker_triggered",
            {"daily_pnl_pct": round(daily_pnl_pct, 4), "threshold": lim["max_daily_loss_pct"]},
        )
        return {
            "approved": False,
            "check": "circuit_breaker",
            "blocked_by": f"daily_loss_{daily_pnl_pct:.2f}%",
            "daily_pnl_pct": round(daily_pnl_pct, 4),
        }

    return {
        "approved": True,
        "check": "circuit_breaker",
        "daily_pnl_pct": round(daily_pnl_pct, 4),
        "daily_trades": len(records),
    }


def check_batman_heartbeat(limits=None):
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    max_silence = lim["batman_max_silence_seconds"]

    if not BATMAN_LATEST.exists():
        _log_event("batman_heartbeat_failed", {"reason": "latest.json_not_found"})
        return {"approved": False, "check": "batman_heartbeat", "blocked_by": "batman_latest_not_found"}

    try:
        data = json.loads(BATMAN_LATEST.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
        age = (_utc_now() - ts).total_seconds()
        if age > max_silence:
            _log_event("batman_heartbeat_failed", {"age_seconds": round(age), "threshold": max_silence})
            return {
                "approved": False,
                "check": "batman_heartbeat",
                "blocked_by": f"batman_silent_{age:.0f}s",
                "age_seconds": round(age),
            }
        return {"approved": True, "check": "batman_heartbeat", "age_seconds": round(age)}
    except Exception as e:
        return {"approved": False, "check": "batman_heartbeat", "blocked_by": f"read_error: {e}"}


def check_spread_anomaly(edge_net, batman_data=None, limits=None):
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    warnings = []

    if edge_net > lim["max_edge_anomaly_pct"]:
        _log_event("spread_anomaly", {"edge_net": edge_net, "type": "too_high"})
        return {
            "approved": False,
            "check": "spread_anomaly",
            "blocked_by": f"edge_{edge_net:.3f}%_too_high",
            "edge_net": edge_net,
        }

    if edge_net < lim["min_edge_sanity_pct"]:
        _log_event("spread_anomaly", {"edge_net": edge_net, "type": "too_low"})
        return {
            "approved": False,
            "check": "spread_anomaly",
            "blocked_by": f"edge_{edge_net:.3f}%_too_low",
            "edge_net": edge_net,
        }

    if batman_data and batman_data.get("spread_flag") == "ANOMALOUS":
        warnings.append("batman_spread_ANOMALOUS")
    if (
        batman_data
        and isinstance(batman_data.get("merchant_count"), (int, float))
        and batman_data["merchant_count"] < 3
    ):
        warnings.append(f"low_merchants_{batman_data['merchant_count']}")

    return {"approved": True, "check": "spread_anomaly", "edge_net": edge_net, "warnings": warnings}


def check_daily_exposure(amount_usd, limits=None):
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    records = _read_ledger()

    today_exposure = sum(
        r.get("amount_usd", 0) or 0
        for r in records
        if r.get("decision") == "OPPORTUNITY" and r.get("action") in ("SIMULATED_TRADE", "LOGGED", "EXECUTED")
    )
    new_total = today_exposure + amount_usd

    if amount_usd > lim["max_single_trade_usd"]:
        return {
            "approved": False,
            "check": "daily_exposure",
            "blocked_by": f"single_trade_{amount_usd}_exceeds_{lim['max_single_trade_usd']}",
        }

    if new_total > lim["max_daily_exposure_usd"]:
        _log_event(
            "daily_exposure_exceeded",
            {"today": today_exposure, "requested": amount_usd, "limit": lim["max_daily_exposure_usd"]},
        )
        return {
            "approved": False,
            "check": "daily_exposure",
            "blocked_by": f"daily_exposure_{new_total:.0f}_exceeds_{lim['max_daily_exposure_usd']:.0f}",
        }

    return {
        "approved": True,
        "check": "daily_exposure",
        "today_exposure": today_exposure,
        "remaining": lim["max_daily_exposure_usd"] - new_total,
    }


def is_kill_switch_active():
    return KILL_SWITCH_FILE.exists()


def activate_kill_switch(reason="manual"):
    KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    KILL_SWITCH_FILE.write_text(f"{_utc_now().isoformat()} | {reason}\n")
    _log_event("kill_switch_activated", {"reason": reason})
    logger.warning(f"KILL SWITCH ACTIVATED: {reason}")


def deactivate_kill_switch():
    if KILL_SWITCH_FILE.exists():
        KILL_SWITCH_FILE.unlink()
        _log_event("kill_switch_deactivated", {})


def run_all_checks(edge_net=0, amount_usd=500, batman_data=None, limits=None):
    if is_kill_switch_active():
        _log_event("blocked_by_kill_switch", {})
        return {"approved": False, "blocked_by": "kill_switch_active", "checks": [], "warnings": []}

    checks = []
    warnings = []
    blocked_by = []

    c1 = check_circuit_breaker(limits)
    checks.append(c1)
    if not c1["approved"]:
        blocked_by.append(c1.get("blocked_by"))

    c2 = check_batman_heartbeat(limits)
    checks.append(c2)
    if not c2["approved"]:
        blocked_by.append(c2.get("blocked_by"))

    c3 = check_spread_anomaly(edge_net, batman_data, limits)
    checks.append(c3)
    if not c3["approved"]:
        blocked_by.append(c3.get("blocked_by"))
    warnings.extend(c3.get("warnings", []))

    c4 = check_daily_exposure(amount_usd, limits)
    checks.append(c4)
    if not c4["approved"]:
        blocked_by.append(c4.get("blocked_by"))

    approved = len(blocked_by) == 0
    if not approved:
        _log_event("gordon_blocked", {"blocked_by": blocked_by})

    return {
        "approved": approved,
        "blocked_by": blocked_by if blocked_by else None,
        "checks": checks,
        "warnings": warnings,
    }
