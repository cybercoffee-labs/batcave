#!/usr/bin/env python3
"""
Batman Lab — Post-Trade Analysis (audit Section L.6)

Decompose closed-trade P&L into the three components a real trader cares
about:

    expected_edge_pct    = scanner's predicted edge at decision time
    realized_slippage_pct = (filled_price − expected_price) / expected_price * 100
                            (signed: positive = price moved favourably)
    friction_pct         = fees / amount_usd * 100
    net_pnl_pct          = expected_edge_pct − friction_pct − abs(realized_slippage_pct)

This is the single most important diagnostic for "is the system actually
making money?" without a live exchange feed: the JSONL ledger has all
three components per trade, so we can attribute losses to the right
cause (bad edge call vs fees vs execution slippage).

Source ledgers:
  - HARVEY:        nightwing_agent/storage/ledger/trades.jsonl
  - Manual orders: nightwing_agent/storage/manual_orders.jsonl  (FILLED rows)

A trade is considered "closed" if it has both expected_price and
filled_price + filled_amount_usd. SIMULATED rows (no real fill) are
filtered out.

Public API:
    analyze_trade(trade) -> dict
    run_daily_analysis(date_iso=None) -> dict
    main() -> int
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # batcave/
HARVEY_LEDGER = BASE_DIR / "nightwing_agent" / "storage" / "ledger" / "trades.jsonl"
MANUAL_ORDERS = BASE_DIR / "nightwing_agent" / "storage" / "manual_orders.jsonl"

# Per-trade analysis output ledger. Two destinations because reconciliation
# matters here too — the JSONL is the durable append-only audit trail; the
# SQLite table is for fast queries from the Streamlit dashboard.
ANALYSIS_JSONL = BASE_DIR / "batman_flow_engine" / "storage" / "logs" / "post_trade_analysis.jsonl"
ANALYSIS_SQLITE = BASE_DIR / "batman_flow_engine" / "storage" / "batman.db"

# Classification thresholds in PERCENT (so 0.5 = 0.5%, NOT 50%).
PROFIT_THRESHOLD_PCT = 0.5
LOSS_THRESHOLD_PCT = -0.5

logger = logging.getLogger("batman.post_trade_analysis")


# ─────────────────────── per-trade analysis ───────────────────────


def _coalesce_float(*values: Any) -> float | None:
    """Return the first non-None float-able value, else None."""
    for v in values:
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def analyze_trade(trade: dict[str, Any]) -> dict[str, Any]:
    """Decompose a single closed trade into edge / slippage / friction / net.

    Returns a dict with the components above plus a "classification"
    field (PROFITABLE | BREAKEVEN | LOSS) and an "error" field on
    insufficient data.
    """
    if not isinstance(trade, dict):
        return {"error": "non-dict input", "classification": "ERROR"}

    expected_price = _coalesce_float(
        trade.get("expected_price"),
        trade.get("p2p_buy_price"),
        trade.get("entry_price"),
    )
    actual_price = _coalesce_float(
        trade.get("filled_price"),
        trade.get("actual_price"),
        trade.get("executed_price"),
    )
    amount_usd = (
        _coalesce_float(
            trade.get("filled_amount_usd"),
            trade.get("executed_amount_usd"),
            trade.get("amount_usd"),
        )
        or 0.0
    )
    fees_usd = _coalesce_float(trade.get("fees_usd"), trade.get("fee")) or 0.0
    expected_edge_pct = _coalesce_float(
        trade.get("expected_edge_pct"),
        trade.get("edge_net"),
    )

    if expected_price is None or actual_price is None or expected_edge_pct is None:
        return {
            "trade_id": trade.get("intent_id") or trade.get("opp_id") or "unknown",
            "error": "insufficient data — missing expected_price, filled_price, or edge",
            "classification": "ERROR",
        }

    # All percentages are in absolute % (not basis points, not fractions).
    if expected_price > 0:
        slippage_pct = (actual_price - expected_price) / expected_price * 100
    else:
        slippage_pct = 0.0
    friction_pct = (fees_usd / amount_usd * 100) if amount_usd > 0 else 0.0
    # We treat slippage's MAGNITUDE as a cost: even favourable slippage on
    # the entry doesn't materialise as profit until the trade is closed,
    # and the operator wants to budget for the worst case.
    net_pnl_pct = expected_edge_pct - friction_pct - abs(slippage_pct)

    if net_pnl_pct >= PROFIT_THRESHOLD_PCT:
        classification = "PROFITABLE"
    elif net_pnl_pct <= LOSS_THRESHOLD_PCT:
        classification = "LOSS"
    else:
        classification = "BREAKEVEN"

    return {
        "trade_id": trade.get("intent_id") or trade.get("opp_id") or "unknown",
        "expected_edge_pct": round(expected_edge_pct, 4),
        "realized_slippage_pct": round(slippage_pct, 4),
        "friction_pct": round(friction_pct, 4),
        "net_pnl_pct": round(net_pnl_pct, 4),
        "amount_usd": round(amount_usd, 2),
        "fees_usd": round(fees_usd, 4),
        "expected_price": expected_price,
        "actual_price": actual_price,
        "classification": classification,
        "pnl_attribution": {
            "edge_contribution": round(expected_edge_pct, 4),
            "slippage_loss": round(-abs(slippage_pct), 4),
            "friction_loss": round(-friction_pct, 4),
            "net": round(net_pnl_pct, 4),
        },
    }


# ─────────────────────── primitive helpers (public API) ───────────────────────


def measure_slippage(
    expected_price: float,
    realized_price: float,
    fees: float = 0.0,
    amount_usd: float = 0.0,
) -> dict[str, float]:
    """Quantify slippage between an expected and realized fill price.

    Returns a dict so callers can read both the price-only slippage and the
    fee-adjusted "effective" version (operator usually cares about both):

        {
            "slippage_pct": price-only slippage as % of expected,
            "slippage_signed_pct": same but signed (positive = adverse for BUY),
            "friction_pct": fees as % of amount_usd (or 0 if amount_usd<=0),
            "effective_slippage_pct": |slippage_pct| + friction_pct,
        }

    Sign convention: positive ``slippage_signed_pct`` means the realized
    price moved AGAINST the trader for a BUY (paid more than expected). For
    a SELL the operator can flip the sign at the call site. We don't take a
    side argument here because the consumers we have all use BUY-side P2P.

    Edge cases:
      - expected_price <= 0 → slippage = 0 (we cannot divide).
      - amount_usd     <= 0 → friction_pct = 0 (no denominator).
    """
    zero_result = {
        "slippage_pct": 0.0,
        "slippage_signed_pct": 0.0,
        "friction_pct": 0.0,
        "effective_slippage_pct": 0.0,
    }
    if expected_price is None:
        return zero_result
    try:
        ep = float(expected_price)
        rp = float(realized_price) if realized_price is not None else ep
        fee = float(fees or 0.0)
        amt = float(amount_usd or 0.0)
    except (TypeError, ValueError):
        return zero_result
    if ep <= 0:
        return zero_result
    signed = (rp - ep) / ep * 100.0
    friction = (fee / amt * 100.0) if amt > 0 else 0.0
    return {
        "slippage_pct": round(abs(signed), 6),
        "slippage_signed_pct": round(signed, 6),
        "friction_pct": round(friction, 6),
        "effective_slippage_pct": round(abs(signed) + friction, 6),
    }


def attribution(
    edge_net: float,
    fees: float,
    slippage: float,
    amount_usd: float = 0.0,
) -> dict[str, Any]:
    """Decompose realized P&L into expected-edge / friction / slippage.

    Inputs are all PERCENTAGES (so 0.5 = 0.5%, not 50%) except *amount_usd*
    which is the trade notional in USD (used to compute USD attribution).

    *fees* may be passed either as a percentage (e.g. 0.1 for 0.1%) or as
    USD; we treat it as a percentage and the caller is expected to convert
    USD to % before calling. ``measure_slippage`` does that conversion.

    Returns:
        {
            "edge_pct": float,         # echoed expected edge
            "friction_pct": float,     # echoed
            "slippage_pct": float,     # echoed (absolute magnitude treated as cost)
            "net_pnl_pct": float,      # edge - friction - |slippage|
            "classification": "PROFITABLE" | "BREAKEVEN" | "LOSS",
            "breakdown": {
                "edge_contribution":  edge_pct,
                "friction_loss":      -friction_pct,
                "slippage_loss":      -|slippage_pct|,
                "net":                net_pnl_pct,
            },
            "net_pnl_usd": float,  # only when amount_usd > 0
        }
    """
    try:
        edge = float(edge_net)
        fric = float(fees)
        slip = abs(float(slippage))
    except (TypeError, ValueError):
        return {
            "edge_pct": 0.0,
            "friction_pct": 0.0,
            "slippage_pct": 0.0,
            "net_pnl_pct": 0.0,
            "classification": "ERROR",
            "breakdown": {"edge_contribution": 0.0, "friction_loss": 0.0, "slippage_loss": 0.0, "net": 0.0},
            "error": "non-numeric input",
        }

    net = edge - fric - slip
    if net >= PROFIT_THRESHOLD_PCT:
        cls = "PROFITABLE"
    elif net <= LOSS_THRESHOLD_PCT:
        cls = "LOSS"
    else:
        cls = "BREAKEVEN"

    out: dict[str, Any] = {
        "edge_pct": round(edge, 6),
        "friction_pct": round(fric, 6),
        "slippage_pct": round(slip, 6),
        "net_pnl_pct": round(net, 6),
        "classification": cls,
        "breakdown": {
            "edge_contribution": round(edge, 6),
            "friction_loss": round(-fric, 6),
            "slippage_loss": round(-slip, 6),
            "net": round(net, 6),
        },
    }
    try:
        amt = float(amount_usd or 0.0)
        if amt > 0:
            out["net_pnl_usd"] = round(amt * net / 100.0, 4)
            out["amount_usd"] = round(amt, 2)
    except (TypeError, ValueError):
        pass
    return out


# ─────────────────────── persistence (public API) ───────────────────────

_ANALYSIS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS post_trade_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_id TEXT,
    opp_id TEXT,
    cycle_id TEXT,
    fiat TEXT,
    asset TEXT,
    side TEXT,
    expected_price REAL,
    actual_price REAL,
    amount_usd REAL,
    fees_usd REAL,
    edge_pct REAL,
    slippage_pct REAL,
    friction_pct REAL,
    net_pnl_pct REAL,
    net_pnl_usd REAL,
    classification TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_pta_ts ON post_trade_analysis(ts DESC);
CREATE INDEX IF NOT EXISTS idx_pta_trade_id ON post_trade_analysis(trade_id);
CREATE INDEX IF NOT EXISTS idx_pta_classification ON post_trade_analysis(classification);
"""


def _resolved_jsonl_path() -> Path:
    """Resolve module-level ANALYSIS_JSONL at call time so tests can monkeypatch."""
    import tools.post_trade_analysis as _self  # noqa: PLC0415

    return _self.ANALYSIS_JSONL


def _resolved_sqlite_path() -> Path:
    import tools.post_trade_analysis as _self  # noqa: PLC0415

    return _self.ANALYSIS_SQLITE


def _coerce_ts(value: Any) -> str:
    """Convert a timestamp-like value to ISO-8601 string. Falls back to now()."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.replace(tzinfo=UTC).isoformat()
    if isinstance(value, str) and value:
        return value
    return datetime.now(UTC).isoformat()


def log_trade_analysis(
    trade_data: dict[str, Any],
    analysis_result: dict[str, Any],
    *,
    jsonl_path: Path | None = None,
    sqlite_path: Path | None = None,
) -> dict[str, bool]:
    """Persist an analysis result to BOTH JSONL and SQLite.

    *trade_data* is the original closed trade (carries ids and metadata).
    *analysis_result* is the dict returned by ``analyze_trade`` or
    ``attribution``.

    Returns ``{"jsonl_ok": bool, "sqlite_ok": bool}``. Each side is
    attempted independently so a missing SQLite file doesn't lose the
    durable JSONL record.
    """
    jsonl = jsonl_path if jsonl_path is not None else _resolved_jsonl_path()
    sqlite_p = sqlite_path if sqlite_path is not None else _resolved_sqlite_path()

    record: dict[str, Any] = {
        "ts": _coerce_ts(trade_data.get("filled_ts") or trade_data.get("ts") or trade_data.get("timestamp")),
        "trade_id": (
            trade_data.get("intent_id")
            or trade_data.get("trade_id")
            or analysis_result.get("trade_id")
            or trade_data.get("opp_id")
            or "unknown"
        ),
        "opp_id": trade_data.get("opp_id"),
        "cycle_id": trade_data.get("cycle_id"),
        "fiat": trade_data.get("fiat") or trade_data.get("market"),
        "asset": trade_data.get("asset"),
        "side": trade_data.get("side"),
        "expected_price": _coalesce_float(
            trade_data.get("expected_price"),
            analysis_result.get("expected_price"),
        ),
        "actual_price": _coalesce_float(
            trade_data.get("filled_price"),
            analysis_result.get("actual_price"),
        ),
        "amount_usd": _coalesce_float(
            trade_data.get("filled_amount_usd"),
            trade_data.get("amount_usd"),
            analysis_result.get("amount_usd"),
        ),
        "fees_usd": _coalesce_float(trade_data.get("fees_usd"), analysis_result.get("fees_usd")),
        "edge_pct": _coalesce_float(
            analysis_result.get("edge_pct"),
            analysis_result.get("expected_edge_pct"),
        ),
        "slippage_pct": _coalesce_float(
            analysis_result.get("slippage_pct"),
            analysis_result.get("realized_slippage_pct"),
        ),
        "friction_pct": _coalesce_float(analysis_result.get("friction_pct")),
        "net_pnl_pct": _coalesce_float(analysis_result.get("net_pnl_pct")),
        "net_pnl_usd": _coalesce_float(analysis_result.get("net_pnl_usd")),
        "classification": analysis_result.get("classification"),
        "raw_json": json.dumps({"trade": trade_data, "analysis": analysis_result}, default=str),
    }

    jsonl_ok = False
    try:
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        jsonl_ok = True
    except Exception as exc:
        logger.error("Post-trade analysis JSONL write failed: %s", exc, exc_info=True)

    sqlite_ok = False
    try:
        sqlite_p.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(sqlite_p) as conn:
            conn.executescript(_ANALYSIS_SCHEMA_SQL)
            conn.execute(
                """
                INSERT INTO post_trade_analysis (
                    ts, trade_id, opp_id, cycle_id, fiat, asset, side,
                    expected_price, actual_price, amount_usd, fees_usd,
                    edge_pct, slippage_pct, friction_pct, net_pnl_pct,
                    net_pnl_usd, classification, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["ts"],
                    record["trade_id"],
                    record["opp_id"],
                    record["cycle_id"],
                    record["fiat"],
                    record["asset"],
                    record["side"],
                    record["expected_price"],
                    record["actual_price"],
                    record["amount_usd"],
                    record["fees_usd"],
                    record["edge_pct"],
                    record["slippage_pct"],
                    record["friction_pct"],
                    record["net_pnl_pct"],
                    record["net_pnl_usd"],
                    record["classification"],
                    record["raw_json"],
                ),
            )
            conn.commit()
        sqlite_ok = True
    except Exception as exc:
        logger.error("Post-trade analysis SQLite write failed: %s", exc, exc_info=True)

    if jsonl_ok and sqlite_ok:
        logger.info(
            "Post-trade analysis logged: trade=%s class=%s net=%.4f%%",
            record["trade_id"],
            record["classification"],
            record["net_pnl_pct"] or 0.0,
        )
    return {"jsonl_ok": jsonl_ok, "sqlite_ok": sqlite_ok}


# ─────────────────────── ledger loading ───────────────────────


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed row at line %d in %s", line_no, path)
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc, exc_info=True)
        return []
    return rows


def _ts_matches_date(ts_value: Any, date_iso: str) -> bool:
    if ts_value is None:
        return False
    try:
        dt = datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).date().isoformat() == date_iso


def _is_closed_trade(row: dict[str, Any]) -> bool:
    """A row is 'closed' enough to analyse if it has filled price+amount.

    HARVEY rows from PAPER mode have action=SIMULATED_TRADE — those have
    expected_price but no filled_price; we exclude them so the
    classification reflects real fills only.
    """
    if row.get("filled_price") is None:
        return False
    if row.get("filled_amount_usd") is None and row.get("executed_amount_usd") is None:
        return False
    return True


def _load_closed_trades(date_iso: str, sources: list[Path]) -> list[dict[str, Any]]:
    """Walk the configured ledgers, return rows that match *date_iso* and
    have enough data to be analysed."""
    closed: list[dict[str, Any]] = []
    for path in sources:
        for row in _load_jsonl(path):
            if not _is_closed_trade(row):
                continue
            ts = row.get("filled_ts") or row.get("ts")
            if not _ts_matches_date(ts, date_iso):
                continue
            closed.append(row)
    return closed


# ─────────────────────── daily analysis ───────────────────────


def run_daily_analysis(
    date_iso: str | None = None,
    sources: list[Path] | None = None,
) -> dict[str, Any]:
    """Analyse all closed trades for *date_iso* (default: today UTC).

    Returns a summary dict containing per-trade analyses + aggregate
    metrics (avg slippage, avg friction, avg net P&L, classification
    counts).
    """
    target_date = date_iso or datetime.now(UTC).date().isoformat()
    sources = sources if sources is not None else [HARVEY_LEDGER, MANUAL_ORDERS]

    report: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "date": target_date,
        "total_trades": 0,
        "profitable": 0,
        "breakeven": 0,
        "loss": 0,
        "errored": 0,
        "avg_expected_edge_pct": 0.0,
        "avg_slippage_pct": 0.0,
        "avg_friction_pct": 0.0,
        "avg_net_pnl_pct": 0.0,
        "trades": [],
    }

    rows = _load_closed_trades(target_date, sources)
    report["total_trades"] = len(rows)

    if not rows:
        return report

    edges: list[float] = []
    slippages: list[float] = []
    frictions: list[float] = []
    nets: list[float] = []

    for row in rows:
        analysis = analyze_trade(row)
        report["trades"].append(analysis)
        cls = analysis.get("classification")
        if cls == "PROFITABLE":
            report["profitable"] += 1
        elif cls == "BREAKEVEN":
            report["breakeven"] += 1
        elif cls == "LOSS":
            report["loss"] += 1
        else:
            report["errored"] += 1
            continue
        edges.append(float(analysis["expected_edge_pct"]))
        slippages.append(float(analysis["realized_slippage_pct"]))
        frictions.append(float(analysis["friction_pct"]))
        nets.append(float(analysis["net_pnl_pct"]))

    if edges:
        report["avg_expected_edge_pct"] = round(sum(edges) / len(edges), 4)
        report["avg_slippage_pct"] = round(sum(slippages) / len(slippages), 4)
        report["avg_friction_pct"] = round(sum(frictions) / len(frictions), 4)
        report["avg_net_pnl_pct"] = round(sum(nets) / len(nets), 4)

    logger.info(
        "Post-trade analysis %s: total=%d profit=%d breakeven=%d loss=%d "
        "avg_net=%.3f%% avg_edge=%.3f%% avg_slip=%.3f%% avg_fric=%.3f%%",
        target_date,
        report["total_trades"],
        report["profitable"],
        report["breakeven"],
        report["loss"],
        report["avg_net_pnl_pct"],
        report["avg_expected_edge_pct"],
        report["avg_slippage_pct"],
        report["avg_friction_pct"],
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI: prints the daily report as JSON. Always exits 0 (informational)."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Daily post-trade P&L attribution.")
    parser.add_argument("--date", default=None, help="UTC date YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args(argv)

    report = run_daily_analysis(date_iso=args.date)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
