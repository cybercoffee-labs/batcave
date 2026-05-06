"""
Nightwing — Per-Trade Risk Manager (audit Section L.4)

Two related responsibilities, intentionally kept separate from GORDON:

1. POSITION SIZING — given the configured risk-per-trade fraction, the
   entry price and the proposed stop-loss, return how many USD to put
   on the table. This is the fixed-fraction Kelly variant: the trader
   is willing to lose at most X% of capital per trade.

2. STOP-LOSS / TAKE-PROFIT GEOMETRY — given an entry price, side, and
   risk-per-trade %, return the SL and TP prices. P2P uses a tight TP
   (escrow timeout makes long holds unsafe); the SL is the operator's
   real bound on loss.

3. INTRADAY LOSS BUDGET — RiskManager tracks realized P&L within a
   session. validate_trade refuses a new trade if cumulative loss +
   the new trade's max-loss exceeds the daily cap. This is the
   per-trade complement to GORDON's portfolio-level circuit breaker.

GORDON gates ENGAGEMENT (kill switch, circuit breaker, exposure cap).
RISK_MANAGER gates SIZING (how big, how tight). Both must pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger("nightwing.risk_manager")

Side = Literal["BUY", "SELL"]


# Defaults are intentionally conservative. A live operator can override
# them via the RiskManager constructor or per-call overrides.
DEFAULT_DAILY_CAPITAL_USD = 10_000.0
DEFAULT_RISK_PER_TRADE_PCT = 0.01  # 1% of daily capital at risk per trade
DEFAULT_DAILY_LOSS_CAP_PCT = 0.05  # halt new trades after 5% daily drawdown
DEFAULT_STOP_LOSS_PCT = 0.02  # 2% adverse move from entry triggers SL
DEFAULT_TAKE_PROFIT_PCT = 0.015  # 1.5% favourable move triggers TP (P2P-friendly)


@dataclass(frozen=True)
class PositionPlan:
    """Output of plan_position. All numeric fields are USD or absolute prices."""

    side: Side
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    position_size_usd: float
    max_loss_usd: float
    risk_reward_ratio: float


def calculate_stop_loss(
    entry_price: float,
    side: Side,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
) -> float:
    """Return the SL price for a *side*-of-entry order.

    BUY  → SL is below entry by stop_loss_pct.
    SELL → SL is above entry by stop_loss_pct.
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive (got {entry_price})")
    if stop_loss_pct <= 0 or stop_loss_pct >= 1:
        raise ValueError(f"stop_loss_pct must be in (0,1) (got {stop_loss_pct})")
    if side == "BUY":
        return entry_price * (1 - stop_loss_pct)
    if side == "SELL":
        return entry_price * (1 + stop_loss_pct)
    raise ValueError(f"side must be 'BUY' or 'SELL' (got {side!r})")


def calculate_take_profit(
    entry_price: float,
    side: Side,
    take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
) -> float:
    """Mirror of calculate_stop_loss for the favourable side."""
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive (got {entry_price})")
    if take_profit_pct <= 0 or take_profit_pct >= 1:
        raise ValueError(f"take_profit_pct must be in (0,1) (got {take_profit_pct})")
    if side == "BUY":
        return entry_price * (1 + take_profit_pct)
    if side == "SELL":
        return entry_price * (1 - take_profit_pct)
    raise ValueError(f"side must be 'BUY' or 'SELL' (got {side!r})")


def calculate_position_size(
    capital_usd: float,
    entry_price: float,
    stop_loss_price: float,
    risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT,
) -> float:
    """Return the position size in USD using the fixed-fraction model.

        max_loss_usd = capital_usd * risk_per_trade_pct
        loss_per_unit = abs(entry_price - stop_loss_price) / entry_price
        size_usd = max_loss_usd / loss_per_unit

    If the SL is at the entry price (loss_per_unit == 0), returns 0 to
    refuse a sizing decision rather than divide by zero.
    """
    if capital_usd <= 0:
        return 0.0
    if entry_price <= 0:
        return 0.0
    if risk_per_trade_pct <= 0:
        return 0.0
    loss_per_unit = abs(entry_price - stop_loss_price) / entry_price
    if loss_per_unit == 0:
        logger.warning("calculate_position_size: SL at entry, refusing to size")
        return 0.0
    max_loss = capital_usd * risk_per_trade_pct
    return max_loss / loss_per_unit


class RiskManager:
    """Per-session loss-budget tracker.

    Construct once per agent session. ``update_realized_pnl`` is called
    after each closed trade. ``validate_trade`` is called before each new
    trade to confirm the cumulative loss + the new trade's max loss
    stays within the daily cap.
    """

    def __init__(
        self,
        daily_capital_usd: float = DEFAULT_DAILY_CAPITAL_USD,
        daily_loss_cap_pct: float = DEFAULT_DAILY_LOSS_CAP_PCT,
        risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT,
    ):
        if daily_capital_usd <= 0:
            raise ValueError("daily_capital_usd must be positive")
        if not (0 < daily_loss_cap_pct < 1):
            raise ValueError("daily_loss_cap_pct must be in (0, 1)")
        if not (0 < risk_per_trade_pct < 1):
            raise ValueError("risk_per_trade_pct must be in (0, 1)")
        self.daily_capital_usd = float(daily_capital_usd)
        self.daily_loss_cap_pct = float(daily_loss_cap_pct)
        self.risk_per_trade_pct = float(risk_per_trade_pct)
        self.realized_pnl_usd = 0.0  # cumulative for the session

    @property
    def daily_loss_cap_usd(self) -> float:
        """Absolute USD value of the daily loss cap."""
        return self.daily_capital_usd * self.daily_loss_cap_pct

    @property
    def remaining_loss_budget_usd(self) -> float:
        """How many USD of additional loss the session can still absorb.

        Realized P&L is signed: profits push the budget UP (more headroom).
        """
        return max(self.daily_loss_cap_usd + self.realized_pnl_usd, 0.0)

    def validate_trade(self, max_loss_usd: float) -> tuple[bool, str]:
        """Check whether a new trade with the given max-loss fits the budget.

        Returns (ok, reason). reason is a short message for logging.
        """
        if max_loss_usd < 0:
            return False, f"max_loss_usd must be non-negative (got {max_loss_usd})"
        if max_loss_usd > self.remaining_loss_budget_usd:
            return (
                False,
                f"daily loss budget exhausted: "
                f"max_loss={max_loss_usd:.2f} remaining={self.remaining_loss_budget_usd:.2f}",
            )
        return True, "ok"

    def update_realized_pnl(self, pnl_usd: float) -> None:
        """Record the closed-trade P&L. Profits and losses both update."""
        self.realized_pnl_usd += float(pnl_usd)
        logger.info(
            "RiskManager: realized P&L now %.2f USD (cap=%.2f)",
            self.realized_pnl_usd,
            self.daily_loss_cap_usd,
        )

    def plan_position(
        self,
        entry_price: float,
        side: Side,
        stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
        take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
    ) -> PositionPlan:
        """Build a complete sizing + SL + TP plan for one trade.

        The returned plan is advisory: validate_trade must still confirm
        it fits the daily budget before execution.
        """
        sl_price = calculate_stop_loss(entry_price, side, stop_loss_pct)
        tp_price = calculate_take_profit(entry_price, side, take_profit_pct)
        size_usd = calculate_position_size(
            capital_usd=self.daily_capital_usd,
            entry_price=entry_price,
            stop_loss_price=sl_price,
            risk_per_trade_pct=self.risk_per_trade_pct,
        )
        max_loss_usd = self.daily_capital_usd * self.risk_per_trade_pct
        # R:R = potential profit / potential loss in absolute price terms.
        loss_distance = abs(entry_price - sl_price)
        profit_distance = abs(tp_price - entry_price)
        rr = profit_distance / loss_distance if loss_distance > 0 else 0.0
        return PositionPlan(
            side=side,
            entry_price=entry_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            position_size_usd=round(size_usd, 2),
            max_loss_usd=round(max_loss_usd, 2),
            risk_reward_ratio=round(rr, 4),
        )
