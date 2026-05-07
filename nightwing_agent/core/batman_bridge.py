"""
BATMAN BRIDGE — Reads latest verified data from Batman Flow Engine.

Source: batman_flow_engine/storage/logs/opportunities.jsonl
Rule: Bridge is PRIMARY source. market_data.py is FALLBACK only.

Configuration:
- Set BATMAN_BASE_PATH in .env to override default location
- Default: auto-detects relative to nightwing_agent location
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("nightwing.batman_bridge")

# === CONFIGURABLE PATH ===
# Priority: 1) ENV var, 2) Relative to this file, 3) Fallback to home
BATMAN_BASE = Path(os.getenv("BATMAN_BASE_PATH", str(Path(__file__).resolve().parents[2] / "batman_flow_engine")))

BATMAN_OPPS = BATMAN_BASE / "storage" / "logs" / "opportunities.jsonl"
BATMAN_LATEST = BATMAN_BASE / "storage" / "latest.json"
MAX_STALENESS_SECONDS = 1200  # 20 minutes

# Last-N-lines window for the legacy fetch_from_batman scan. Big enough to
# catch the latest record per pair across one full Batman cycle (every 20
# min, 11 scanners ≈ 30-50 records max), small enough to keep the agent
# fast even if the JSONL is huge.
TAIL_LINES = 50


# ─────────────────────── helpers ───────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _read_records(path: Path, last_n: int | None = None) -> list[dict[str, Any]]:
    """Read JSONL records, skipping malformed lines. Optionally tails the
    last *last_n* lines."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if last_n is not None:
        lines = lines[-last_n:]
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def verify_bridge() -> bool:
    """Verify the bridge files exist and are accessible."""
    opps_exists = BATMAN_OPPS.exists()
    latest_exists = BATMAN_LATEST.exists()

    if not opps_exists:
        logger.warning("⚠️  Batman bridge DESCONECTADO: opportunities.jsonl no existe")
        logger.warning(f"    Esperado en: {BATMAN_OPPS}")
        logger.warning(f"    BATMAN_BASE_PATH actual: {BATMAN_BASE}")
        return False

    if not latest_exists:
        logger.warning(f"⚠️  Batman latest.json no encontrado: {BATMAN_LATEST}")

    return opps_exists


# ─────────────────────── primary API: fetch_from_batman ───────────────────────


def fetch_from_batman(fiat: str) -> dict[str, Any]:
    """Return the most recent type-C opportunity for *fiat*.

    Returns one of:
      - {"status": "ok", ...full opportunity fields..., "age_seconds": float}
      - {"status": "stale", "age_seconds": >1200, "data": {...}}
      - {"status": "error", "error": "<reason>"}
    """
    if not BATMAN_OPPS.exists():
        return {"status": "error", "error": f"opportunities_jsonl_not_found: {BATMAN_OPPS}"}

    records = _read_records(BATMAN_OPPS, last_n=TAIL_LINES)
    if not records:
        return {"status": "error", "error": "opportunities_jsonl_empty"}

    # Latest type-C record matching the fiat. Iterate in reverse so the
    # most recent matching record wins.
    candidate: dict[str, Any] | None = None
    for record in reversed(records):
        if record.get("type") != "C":
            continue
        if record.get("market") != fiat:
            continue
        candidate = record
        break

    if candidate is None:
        return {"status": "error", "error": f"no_record_for_{fiat}"}

    ts = _parse_ts(candidate.get("ts"))
    if ts is None:
        return {"status": "error", "error": "bad_timestamp"}
    age = (_now() - ts).total_seconds()

    base = {
        "fiat": fiat,
        "market": f"{candidate.get('asset', 'USDT')}/{fiat}",
        "p2p_premium": candidate.get("p2p_premium"),
        "edge_net": candidate.get("edge_net"),
        "viable": candidate.get("viable", False),
        "total_friction_pct": candidate.get("total_friction_pct"),
        "spot_price": candidate.get("spot_price"),
        "p2p_buy_price": candidate.get("p2p_buy_price"),
        "p2p_sell_price": candidate.get("p2p_sell_price"),
        "depth_estimate": candidate.get("depth_estimate"),
        "merchant_count": candidate.get("merchant_count"),
        "premium_quality": candidate.get("premium_quality"),
        "rate_source": candidate.get("rate_source"),
        "spread_flag": candidate.get("spread_flag"),
        "age_seconds": age,
        "batman_ts": candidate.get("ts"),
        "opp_id": candidate.get("opp_id"),
    }

    if age > MAX_STALENESS_SECONDS:
        return {"status": "stale", "age_seconds": age, "data": base}

    return {"status": "ok", **base}


# ─────────────────────── liveness check ───────────────────────


def is_batman_alive(max_age_seconds: int = MAX_STALENESS_SECONDS) -> bool:
    """True iff Batman's latest.json is younger than max_age_seconds."""
    if not BATMAN_LATEST.exists():
        return False
    try:
        data = json.loads(BATMAN_LATEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    ts = _parse_ts(data.get("timestamp"))
    if ts is None:
        return False
    age = (_now() - ts).total_seconds()
    return age <= max_age_seconds


# ─────────────────────── multi-strategy: fetch_best_opportunity ───────────────────────


def fetch_best_opportunity(
    fiats: list[str] | None = None,
    types: list[str] | None = None,
    max_staleness_seconds: int = MAX_STALENESS_SECONDS,
) -> dict[str, Any]:
    """Return the highest-edge non-stale opportunity matching *fiats* / *types*.

    Args:
        fiats: list of accepted fiat markets (default ["MXN"]).
        types: list of accepted scanner types (default: any). E.g. ["C","D"].
        max_staleness_seconds: records older than this are excluded.

    Returns one of:
        - {"status": "ok", ...flat fields..., "raw_record": {...}}
        - {"status": "no_match"}
        - {"status": "error", "error": "..."}
    """
    if fiats is None:
        fiats = ["MXN"]
    fiats_set = set(fiats)
    types_set = set(types) if types is not None else None

    if not BATMAN_OPPS.exists():
        return {"status": "error", "error": f"opportunities_jsonl_not_found: {BATMAN_OPPS}"}

    try:
        text = BATMAN_OPPS.read_text(encoding="utf-8")
    except Exception as exc:
        return {"status": "error", "error": f"read_failed: {exc}"}

    now = _now()
    best: dict[str, Any] | None = None
    best_edge: float = float("-inf")

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        if record.get("market") not in fiats_set:
            continue
        if types_set is not None and record.get("type") not in types_set:
            continue

        ts = _parse_ts(record.get("ts"))
        if ts is None:
            continue
        age = (now - ts).total_seconds()
        if age > max_staleness_seconds:
            continue

        edge = record.get("edge_net")
        try:
            edge_f = float(edge)
        except (TypeError, ValueError):
            continue

        if edge_f > best_edge:
            best_edge = edge_f
            best = record

    if best is None:
        return {"status": "no_match"}

    return {
        "status": "ok",
        "opp_id": best.get("opp_id"),
        "type": best.get("type"),
        "fiat": best.get("market"),
        "market": best.get("market"),
        "edge_net": best.get("edge_net"),
        "viable": best.get("viable"),
        "scanner_id": best.get("scanner_id"),
        "ts": best.get("ts"),
        "raw_record": best,
    }
