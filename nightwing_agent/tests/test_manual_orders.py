"""Tests for nightwing_agent/core/manual_orders.py (audit Section L.3 / Phase 3A)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _redirect_orders_log(tmp_path, monkeypatch):
    """Each test gets a clean log file."""
    import core.manual_orders as mo

    log_path = tmp_path / "manual_orders.jsonl"
    monkeypatch.setattr(mo, "ORDERS_LOG", log_path)
    yield log_path


# ─────────────────────── create_order ───────────────────────


def test_create_order_persists_pending_record(_redirect_orders_log):
    from core.manual_orders import create_order, get_order

    order = create_order(
        fiat="MXN",
        asset="USDT",
        side="BUY",
        expected_price=18.05,
        amount_usd=500.0,
        opp_id="OPP-C-DEADBEEF",
    )
    assert order["status"] == "PENDING"
    assert order["intent_id"].startswith("INTENT-P2P-")
    assert order["fiat"] == "MXN"
    assert order["asset"] == "USDT"
    assert order["amount_usd"] == 500.0
    assert order["opp_id"] == "OPP-C-DEADBEEF"
    assert order["filled_price"] is None

    fetched = get_order(order["intent_id"])
    assert fetched is not None
    assert fetched["status"] == "PENDING"


def test_create_order_validates_inputs(_redirect_orders_log):
    from core.manual_orders import create_order

    with pytest.raises(ValueError):
        create_order(fiat="MXN", asset="USDT", side="HOLD", expected_price=18, amount_usd=100)
    with pytest.raises(ValueError):
        create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=0, amount_usd=100)
    with pytest.raises(ValueError):
        create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=0)


def test_create_order_records_sl_tp_when_provided(_redirect_orders_log):
    from core.manual_orders import create_order

    order = create_order(
        fiat="MXN",
        asset="USDT",
        side="BUY",
        expected_price=18.05,
        amount_usd=500.0,
        stop_loss_price=17.69,
        take_profit_price=18.32,
        max_loss_usd=10.0,
    )
    assert order["stop_loss_price"] == 17.69
    assert order["take_profit_price"] == 18.32
    assert order["max_loss_usd"] == 10.0


# ─────────────────────── list_pending ───────────────────────


def test_list_pending_returns_only_pending(_redirect_orders_log):
    from core.manual_orders import create_order, list_pending, mark_filled

    o1 = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    o2 = create_order(fiat="ARS", asset="USDT", side="BUY", expected_price=900, amount_usd=200)
    mark_filled(o1["intent_id"], filled_price=18.0, filled_amount_usd=100)

    pending = list_pending()
    assert len(pending) == 1
    assert pending[0]["intent_id"] == o2["intent_id"]


def test_list_pending_orders_oldest_first(_redirect_orders_log):
    from core.manual_orders import create_order, list_pending

    o1 = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    o2 = create_order(fiat="ARS", asset="USDT", side="BUY", expected_price=900, amount_usd=200)
    pending = list_pending()
    assert [p["intent_id"] for p in pending] == [o1["intent_id"], o2["intent_id"]]


# ─────────────────────── mark_filled ───────────────────────


def test_mark_filled_transitions_to_filled(_redirect_orders_log):
    from core.manual_orders import create_order, get_order, mark_filled

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18.05, amount_usd=500)
    result = mark_filled(order["intent_id"], filled_price=18.07, filled_amount_usd=500.0, fees_usd=0.50)
    assert result is not None
    assert result["status"] == "FILLED"
    assert result["filled_price"] == 18.07
    assert result["fees_usd"] == 0.50

    current = get_order(order["intent_id"])
    assert current["status"] == "FILLED"


def test_mark_filled_rejects_invalid_inputs(_redirect_orders_log):
    from core.manual_orders import create_order, mark_filled

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    assert mark_filled(order["intent_id"], filled_price=0, filled_amount_usd=100) is None
    assert mark_filled(order["intent_id"], filled_price=18, filled_amount_usd=-1) is None


def test_mark_filled_rejects_unknown_intent(_redirect_orders_log):
    from core.manual_orders import mark_filled

    assert mark_filled("INTENT-P2P-DOESNOTEXIST", filled_price=18, filled_amount_usd=100) is None


def test_mark_filled_blocks_double_fill(_redirect_orders_log):
    """An order in FILLED state should not transition again."""
    from core.manual_orders import create_order, mark_filled

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    mark_filled(order["intent_id"], filled_price=18, filled_amount_usd=100)
    second = mark_filled(order["intent_id"], filled_price=19, filled_amount_usd=100)
    assert second is None


# ─────────────────────── mark_cancelled / mark_expired ───────────────────────


def test_mark_cancelled_transitions(_redirect_orders_log):
    from core.manual_orders import create_order, get_order, mark_cancelled

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    result = mark_cancelled(order["intent_id"], reason="operator changed mind")
    assert result is not None
    assert result["status"] == "CANCELLED"
    assert result["reason"] == "operator changed mind"
    assert get_order(order["intent_id"])["status"] == "CANCELLED"


def test_mark_expired_transitions(_redirect_orders_log):
    from core.manual_orders import create_order, mark_expired

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    result = mark_expired(order["intent_id"])
    assert result["status"] == "EXPIRED"


def test_terminal_states_reject_further_transitions(_redirect_orders_log):
    from core.manual_orders import create_order, mark_cancelled, mark_filled

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    mark_cancelled(order["intent_id"])
    # Try to fill an already-cancelled order — must fail.
    assert mark_filled(order["intent_id"], filled_price=18, filled_amount_usd=100) is None


# ─────────────────────── expire_overdue ───────────────────────


def test_expire_overdue_only_expires_past_deadline(_redirect_orders_log):
    from core.manual_orders import create_order, expire_overdue, list_pending

    create_order(
        fiat="MXN",
        asset="USDT",
        side="BUY",
        expected_price=18,
        amount_usd=100,
        deadline_minutes=15,
    )
    create_order(
        fiat="ARS",
        asset="USDT",
        side="BUY",
        expected_price=900,
        amount_usd=200,
        deadline_minutes=15,
    )

    # Before deadline: nothing expires.
    expired_now = expire_overdue(now=datetime.now(timezone.utc))
    assert expired_now == []
    assert len(list_pending()) == 2

    # After deadline: both expire.
    later = datetime.now(timezone.utc) + timedelta(minutes=20)
    expired = expire_overdue(now=later)
    assert len(expired) == 2
    assert all(o["status"] == "EXPIRED" for o in expired)
    assert list_pending() == []


# ─────────────────────── append-only audit trail ───────────────────────


def test_log_is_append_only_state_reconstructed(_redirect_orders_log):
    """All four state transitions for one order produce four lines in the log,
    not a mutation of one line. Most-recent state wins."""
    from core.manual_orders import create_order, get_order, mark_cancelled

    order = create_order(fiat="MXN", asset="USDT", side="BUY", expected_price=18, amount_usd=100)
    mark_cancelled(order["intent_id"])

    raw = _redirect_orders_log.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) == 2  # one PENDING, one CANCELLED
    final = get_order(order["intent_id"])
    assert final["status"] == "CANCELLED"
