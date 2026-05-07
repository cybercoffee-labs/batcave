"""
Nightwing — Manual P2P Order Tracking (audit Section L.3 — Phase 3A)

Bridge between SIMULATED/PAPER and full LIVE automation. The agent
produces an order PROPOSAL with full sizing + SL/TP from RiskManager;
the OPERATOR completes the trade manually on the Binance P2P app
(because P2P involves human counterparty + escrow); the operator
later marks the order FILLED, EXPIRED, or CANCELLED via the CLI tool.

Why a separate file from HARVEY:
- HARVEY records EXECUTED trades (forward-only ledger).
- manual_orders tracks PENDING state with mutability (status transitions
  PENDING → FILLED / EXPIRED / CANCELLED). When marked filled, the order
  is also recorded in HARVEY for unified P&L attribution.

Storage: storage/manual_orders.jsonl — append-only event log. Each row is
either a creation or a status update. The current state of each order
is rebuilt from the latest row keyed by intent_id.

Public API:
    create_order(...) -> dict
    list_pending() -> list[dict]
    mark_filled(intent_id, filled_price, filled_amount_usd, fees_usd=0.0) -> dict | None
    mark_expired(intent_id, reason="deadline_passed") -> dict | None
    mark_cancelled(intent_id, reason="operator_cancel") -> dict | None
    get_order(intent_id) -> dict | None

Order shape (one record per state transition):
    {
        "intent_id": "INTENT-P2P-<uuid12>",
        "ts": ISO-8601,
        "status": "PENDING" | "FILLED" | "EXPIRED" | "CANCELLED",
        "fiat": "MXN", "asset": "USDT",
        "side": "BUY" | "SELL",
        "expected_price": float,
        "amount_usd": float,
        "stop_loss_price": float | None,
        "take_profit_price": float | None,
        "max_loss_usd": float | None,
        "deadline_ts": ISO-8601,             # when the operator must act by
        "opp_id": str | None,                # Batman opp_id that triggered this
        "filled_price": float | None,        # only on FILLED
        "filled_amount_usd": float | None,
        "filled_ts": ISO-8601 | None,
        "fees_usd": float,
        "reason": str | None,                # only on EXPIRED / CANCELLED
        "operator_notes": str | None,
    }
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("nightwing.manual_orders")

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
ORDERS_LOG = STORAGE_DIR / "manual_orders.jsonl"

# Default lifecycle: P2P trades typically need to be confirmed within
# 15 minutes of merchant acceptance on Binance. We give the operator
# 15 minutes to act before expiring the order.
DEFAULT_DEADLINE_MINUTES = 15

VALID_STATUS = ("PENDING", "FILLED", "EXPIRED", "CANCELLED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _resolved_log_path() -> Path:
    """Resolve the active orders log path at call time so tests can monkeypatch
    the module-level ORDERS_LOG transparently. Returns the live module
    attribute, not whatever value was bound when this file was imported."""
    import core.manual_orders as _self  # noqa: PLC0415

    return _self.ORDERS_LOG


def _append(record: dict[str, Any], path: Path | None = None) -> bool:
    target = path if path is not None else _resolved_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return True
    except Exception as exc:
        logger.error("Failed to append manual order record: %s", exc, exc_info=True)
        return False


def _read_all(path: Path | None = None) -> list[dict[str, Any]]:
    target = path if path is not None else _resolved_log_path()
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed order row at line %d: %s", line_no, line[:100])
    except Exception as exc:
        logger.error("Failed to read manual orders: %s", exc, exc_info=True)
        return []
    return rows


def _latest_state(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build {intent_id: latest_row} from the append-only log."""
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        iid = row.get("intent_id")
        if not iid:
            continue
        latest[iid] = row  # later rows overwrite earlier ones
    return latest


def create_order(
    *,
    fiat: str,
    asset: str,
    side: str,
    expected_price: float,
    amount_usd: float,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    max_loss_usd: float | None = None,
    deadline_minutes: int = DEFAULT_DEADLINE_MINUTES,
    opp_id: str | None = None,
    operator_notes: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Create a PENDING manual order. Returns the persisted record.

    The intent_id is generated here (12-hex-char uuid) and is the stable
    handle the operator uses to mark the order filled/expired/cancelled.
    """
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL (got {side!r})")
    if expected_price <= 0:
        raise ValueError(f"expected_price must be positive (got {expected_price})")
    if amount_usd <= 0:
        raise ValueError(f"amount_usd must be positive (got {amount_usd})")

    intent_id = f"INTENT-P2P-{uuid.uuid4().hex[:12].upper()}"
    now = _now()
    record = {
        "intent_id": intent_id,
        "ts": _iso(now),
        "status": "PENDING",
        "fiat": fiat.upper(),
        "asset": asset.upper(),
        "side": side,
        "expected_price": float(expected_price),
        "amount_usd": float(amount_usd),
        "stop_loss_price": float(stop_loss_price) if stop_loss_price is not None else None,
        "take_profit_price": float(take_profit_price) if take_profit_price is not None else None,
        "max_loss_usd": float(max_loss_usd) if max_loss_usd is not None else None,
        "deadline_ts": _iso(now + timedelta(minutes=deadline_minutes)),
        "opp_id": opp_id,
        "filled_price": None,
        "filled_amount_usd": None,
        "filled_ts": None,
        "fees_usd": 0.0,
        "reason": None,
        "operator_notes": operator_notes,
    }
    _append(record, path)
    logger.info(
        "Manual order PENDING: intent=%s side=%s %s/%s amount=%.2f USD price=%s deadline=%s opp=%s",
        intent_id,
        side,
        fiat,
        asset,
        amount_usd,
        expected_price,
        record["deadline_ts"],
        opp_id or "—",
    )
    return record


def get_order(intent_id: str, path: Path | None = None) -> dict[str, Any] | None:
    """Return the current state of an order, or None if unknown."""
    rows = _read_all(path)
    return _latest_state(rows).get(intent_id)


def list_pending(path: Path | None = None) -> list[dict[str, Any]]:
    """Return all orders currently in PENDING state, oldest first."""
    rows = _read_all(path)
    state = _latest_state(rows)
    pending = [r for r in state.values() if r.get("status") == "PENDING"]
    pending.sort(key=lambda r: r.get("ts", ""))
    return pending


def _transition(
    intent_id: str,
    new_status: str,
    *,
    extra: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Append a new row representing a status transition.

    Returns the new row, or None if the intent_id is unknown or the
    order is already in a terminal state.
    """
    if new_status not in VALID_STATUS:
        raise ValueError(f"invalid status {new_status!r}")
    current = get_order(intent_id, path)
    if current is None:
        logger.error("Cannot transition unknown order intent_id=%s", intent_id)
        return None
    if current.get("status") in ("FILLED", "EXPIRED", "CANCELLED"):
        logger.error(
            "Refusing transition: order %s already in terminal state %s",
            intent_id,
            current.get("status"),
        )
        return None
    new_row = dict(current)
    new_row.update(
        {
            "status": new_status,
            "ts": _iso(_now()),
        }
    )
    if extra:
        new_row.update(extra)
    _append(new_row, path)
    logger.info("Manual order %s → %s", intent_id, new_status)
    return new_row


def mark_filled(
    intent_id: str,
    filled_price: float,
    filled_amount_usd: float,
    fees_usd: float = 0.0,
    path: Path | None = None,
    skip_post_trade_analysis: bool = False,
) -> dict[str, Any] | None:
    """Operator confirmation: trade was completed on Binance P2P.

    *filled_price* and *filled_amount_usd* may differ from the
    expected_price (price drift, partial fill). Both are recorded so
    post-trade analysis can compute slippage and friction.

    Side effect (audit Section L.6): on a successful FILLED transition,
    invokes ``tools.post_trade_analysis.log_trade_analysis`` to record
    edge / friction / slippage / net P&L for the trade. Set
    *skip_post_trade_analysis* to True for tests that don't want the
    side write into the batman_flow_engine SQLite.
    """
    if filled_price <= 0 or filled_amount_usd <= 0:
        logger.error("mark_filled rejected: non-positive price or amount")
        return None
    row = _transition(
        intent_id,
        "FILLED",
        extra={
            "filled_price": float(filled_price),
            "filled_amount_usd": float(filled_amount_usd),
            "filled_ts": _iso(_now()),
            "fees_usd": float(fees_usd),
        },
        path=path,
    )
    if row is not None and not skip_post_trade_analysis:
        _record_post_trade_analysis(row)
    return row


def _record_post_trade_analysis(filled_row: dict[str, Any]) -> None:
    """Run measure_slippage + attribution + log_trade_analysis for a fill.

    Failures here MUST NOT propagate — the order is already FILLED. The
    most we'll do is log an error.
    """
    try:
        # Locate batman_flow_engine on sys.path so we can import its tools.
        import sys as _sys

        batcave_root = Path(__file__).resolve().parent.parent.parent
        batman_path = batcave_root / "batman_flow_engine"
        if str(batman_path) not in _sys.path:
            _sys.path.insert(0, str(batman_path))
        from tools.post_trade_analysis import (  # noqa: PLC0415
            attribution,
            log_trade_analysis,
            measure_slippage,
        )
    except Exception as exc:
        logger.warning("Post-trade analysis import failed (skipping): %s", exc)
        return

    try:
        expected_price = float(filled_row.get("expected_price") or 0.0)
        filled_price = float(filled_row.get("filled_price") or 0.0)
        amount = float(filled_row.get("filled_amount_usd") or 0.0)
        fees = float(filled_row.get("fees_usd") or 0.0)
        # Edge isn't on the manual order itself; the agent stores opp_id
        # which we could chase, but for now we accept a 0 edge if absent
        # and let the operator sees friction/slippage even when edge is
        # unknown.
        edge_pct = float(filled_row.get("edge_net") or filled_row.get("expected_edge_pct") or 0.0)

        slip = measure_slippage(
            expected_price=expected_price,
            realized_price=filled_price,
            fees=fees,
            amount_usd=amount,
        )
        analysis = attribution(
            edge_net=edge_pct,
            fees=slip["friction_pct"],
            slippage=slip["slippage_pct"],
            amount_usd=amount,
        )
        result = log_trade_analysis(filled_row, analysis)
        logger.info(
            "Post-trade analysis logged for %s: classification=%s net=%.4f%% jsonl_ok=%s sqlite_ok=%s",
            filled_row.get("intent_id"),
            analysis.get("classification"),
            analysis.get("net_pnl_pct", 0.0),
            result.get("jsonl_ok"),
            result.get("sqlite_ok"),
        )
    except Exception as exc:
        logger.error("Post-trade analysis failed for %s: %s", filled_row.get("intent_id"), exc, exc_info=True)


def mark_expired(
    intent_id: str,
    reason: str = "deadline_passed",
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Auto-close after deadline_ts elapses without operator action."""
    return _transition(intent_id, "EXPIRED", extra={"reason": reason}, path=path)


def mark_cancelled(
    intent_id: str,
    reason: str = "operator_cancel",
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Operator-initiated abort before fill."""
    return _transition(intent_id, "CANCELLED", extra={"reason": reason}, path=path)


def expire_overdue(now: datetime | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    """Auto-expire any PENDING order whose deadline_ts has passed.

    Intended to be called by the agent at the start of each cycle so
    stale orders don't block the operator's view.
    """
    when = now or _now()
    expired: list[dict[str, Any]] = []
    for order in list_pending(path):
        try:
            deadline = datetime.fromisoformat(order["deadline_ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if when >= deadline:
            row = mark_expired(order["intent_id"], reason="auto_deadline_passed", path=path)
            if row:
                expired.append(row)
    return expired
