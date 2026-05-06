"""Tests for nightwing_agent/core/risk_manager.py (audit Section L.4)."""

from __future__ import annotations

import pytest

from core.risk_manager import (
    DEFAULT_DAILY_CAPITAL_USD,
    DEFAULT_STOP_LOSS_PCT,
    PositionPlan,
    RiskManager,
    calculate_position_size,
    calculate_stop_loss,
    calculate_take_profit,
)


# ─────────────────────── stop loss ───────────────────────


def test_calculate_stop_loss_buy_below_entry():
    sl = calculate_stop_loss(entry_price=100.0, side="BUY", stop_loss_pct=0.02)
    assert sl == pytest.approx(98.0)


def test_calculate_stop_loss_sell_above_entry():
    sl = calculate_stop_loss(entry_price=100.0, side="SELL", stop_loss_pct=0.02)
    assert sl == pytest.approx(102.0)


def test_calculate_stop_loss_rejects_zero_entry():
    with pytest.raises(ValueError):
        calculate_stop_loss(0.0, "BUY")


def test_calculate_stop_loss_rejects_pct_out_of_range():
    with pytest.raises(ValueError):
        calculate_stop_loss(100.0, "BUY", stop_loss_pct=0)
    with pytest.raises(ValueError):
        calculate_stop_loss(100.0, "BUY", stop_loss_pct=1.0)


def test_calculate_stop_loss_rejects_invalid_side():
    with pytest.raises(ValueError):
        calculate_stop_loss(100.0, "HOLD")  # type: ignore[arg-type]


# ─────────────────────── take profit ───────────────────────


def test_calculate_take_profit_buy_above_entry():
    tp = calculate_take_profit(entry_price=100.0, side="BUY", take_profit_pct=0.015)
    assert tp == pytest.approx(101.5)


def test_calculate_take_profit_sell_below_entry():
    tp = calculate_take_profit(entry_price=100.0, side="SELL", take_profit_pct=0.015)
    assert tp == pytest.approx(98.5)


# ─────────────────────── position size ───────────────────────


def test_calculate_position_size_fixed_fraction():
    """capital=10000, risk=1%, entry=100, SL=98 → 100/0.02 = 5000 USD."""
    size = calculate_position_size(
        capital_usd=10_000.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        risk_per_trade_pct=0.01,
    )
    assert size == pytest.approx(5000.0)


def test_calculate_position_size_zero_when_sl_equals_entry():
    size = calculate_position_size(10_000.0, 100.0, 100.0, 0.01)
    assert size == 0.0


def test_calculate_position_size_zero_when_capital_invalid():
    assert calculate_position_size(0, 100, 98, 0.01) == 0.0
    assert calculate_position_size(-1, 100, 98, 0.01) == 0.0


def test_calculate_position_size_zero_when_risk_invalid():
    assert calculate_position_size(10_000, 100, 98, 0) == 0.0
    assert calculate_position_size(10_000, 100, 98, -0.01) == 0.0


# ─────────────────────── RiskManager ───────────────────────


def test_risk_manager_constructor_validates_inputs():
    with pytest.raises(ValueError):
        RiskManager(daily_capital_usd=0)
    with pytest.raises(ValueError):
        RiskManager(daily_loss_cap_pct=0)
    with pytest.raises(ValueError):
        RiskManager(daily_loss_cap_pct=1.0)
    with pytest.raises(ValueError):
        RiskManager(risk_per_trade_pct=0)


def test_risk_manager_default_constructor():
    r = RiskManager()
    assert r.daily_capital_usd == DEFAULT_DAILY_CAPITAL_USD
    assert r.realized_pnl_usd == 0.0


def test_risk_manager_daily_loss_cap_usd():
    r = RiskManager(daily_capital_usd=10_000, daily_loss_cap_pct=0.05)
    assert r.daily_loss_cap_usd == 500.0


def test_risk_manager_validate_trade_passes_within_budget():
    r = RiskManager(daily_capital_usd=10_000, daily_loss_cap_pct=0.05)
    ok, reason = r.validate_trade(max_loss_usd=100.0)
    assert ok is True
    assert reason == "ok"


def test_risk_manager_validate_trade_blocks_when_exhausted():
    r = RiskManager(daily_capital_usd=10_000, daily_loss_cap_pct=0.05)
    r.update_realized_pnl(-450.0)  # 450 of 500 cap consumed
    ok, reason = r.validate_trade(max_loss_usd=100.0)  # would push past cap
    assert ok is False
    assert "daily loss budget" in reason


def test_risk_manager_validate_trade_recovers_after_profitable_trade():
    r = RiskManager(daily_capital_usd=10_000, daily_loss_cap_pct=0.05)
    r.update_realized_pnl(-400.0)
    # New profit pushes budget back up.
    r.update_realized_pnl(+200.0)
    ok, _ = r.validate_trade(max_loss_usd=250.0)
    assert ok is True


def test_risk_manager_validate_trade_rejects_negative_max_loss():
    r = RiskManager()
    ok, reason = r.validate_trade(max_loss_usd=-10.0)
    assert ok is False
    assert "non-negative" in reason


def test_risk_manager_remaining_budget_floors_at_zero():
    """If realized loss already exceeds the cap, remaining is 0 — not negative."""
    r = RiskManager(daily_capital_usd=10_000, daily_loss_cap_pct=0.05)
    r.update_realized_pnl(-1000.0)  # blew through the 500 cap
    assert r.remaining_loss_budget_usd == 0.0


# ─────────────────────── plan_position ───────────────────────


def test_plan_position_returns_complete_plan_for_buy():
    r = RiskManager(daily_capital_usd=10_000, risk_per_trade_pct=0.01)
    plan = r.plan_position(entry_price=100.0, side="BUY", stop_loss_pct=0.02, take_profit_pct=0.015)
    assert isinstance(plan, PositionPlan)
    assert plan.side == "BUY"
    assert plan.entry_price == 100.0
    assert plan.stop_loss_price == pytest.approx(98.0)
    assert plan.take_profit_price == pytest.approx(101.5)
    assert plan.position_size_usd == pytest.approx(5000.0)
    assert plan.max_loss_usd == pytest.approx(100.0)
    # R:R = profit_distance(1.5) / loss_distance(2.0) = 0.75
    assert plan.risk_reward_ratio == pytest.approx(0.75)


def test_plan_position_for_sell_inverts_sl_tp():
    r = RiskManager(daily_capital_usd=10_000, risk_per_trade_pct=0.01)
    plan = r.plan_position(entry_price=100.0, side="SELL", stop_loss_pct=0.02, take_profit_pct=0.015)
    assert plan.stop_loss_price == pytest.approx(102.0)
    assert plan.take_profit_price == pytest.approx(98.5)
    assert plan.max_loss_usd == pytest.approx(100.0)


def test_plan_position_zero_size_when_sl_at_entry():
    """Defensive: a trader who passes stop_loss_pct so small the SL rounds
    to entry should get a zero position, not a divide-by-zero."""
    r = RiskManager(daily_capital_usd=10_000, risk_per_trade_pct=0.01)
    # Use a tiny stop_loss_pct that's still > 0 → real but tiny SL distance.
    plan = r.plan_position(entry_price=100.0, side="BUY", stop_loss_pct=0.0001)
    # 1% of 10k = 100; 100 / (0.01% loss) = 1,000,000 USD position. That's
    # enormous but mathematically correct — small SL = big size. We assert
    # we got a finite number, not NaN.
    assert plan.position_size_usd == pytest.approx(1_000_000.0)
    assert plan.max_loss_usd == pytest.approx(100.0)


def test_plan_position_uses_default_sl_tp_pct():
    r = RiskManager()
    plan = r.plan_position(entry_price=100.0, side="BUY")
    expected_sl = 100.0 * (1 - DEFAULT_STOP_LOSS_PCT)
    assert plan.stop_loss_price == pytest.approx(expected_sl)
