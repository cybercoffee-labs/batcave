#!/usr/bin/env python3
"""
Nightwing — Manual P2P Orders CLI

Operator-facing companion to ``core/manual_orders.py``. Lists pending
orders the agent has proposed, lets the operator mark them filled or
cancelled. Auto-expires orders past their deadline.

Usage:
    python tools/manual_orders_cli.py list
    python tools/manual_orders_cli.py expire-overdue
    python tools/manual_orders_cli.py fill <intent_id> <filled_price> <filled_amount_usd> [--fees=<usd>]
    python tools/manual_orders_cli.py cancel <intent_id> [--reason=<text>]

Examples:
    python tools/manual_orders_cli.py list
    python tools/manual_orders_cli.py fill INTENT-P2P-ABCDEF012345 18.07 500.00 --fees=0.50
    python tools/manual_orders_cli.py cancel INTENT-P2P-ABCDEF012345 --reason="merchant offline"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make the agent's package importable regardless of cwd.
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.manual_orders import (  # noqa: E402
    expire_overdue,
    get_order,
    list_pending,
    mark_cancelled,
    mark_filled,
)

logger = logging.getLogger("nightwing.manual_orders.cli")


def cmd_list(_args: argparse.Namespace) -> int:
    pending = list_pending()
    if not pending:
        print("No pending manual orders.")
        return 0
    print(f"{len(pending)} pending order(s):\n")
    for o in pending:
        print(
            f"  {o['intent_id']}  {o['side']:4s} {o['fiat']}/{o['asset']}  "
            f"price={o['expected_price']:>10.4f}  amt=${o['amount_usd']:>9.2f}  "
            f"deadline={o['deadline_ts']}  opp={o.get('opp_id') or '—'}"
        )
    return 0


def cmd_fill(args: argparse.Namespace) -> int:
    result = mark_filled(
        intent_id=args.intent_id,
        filled_price=args.filled_price,
        filled_amount_usd=args.filled_amount_usd,
        fees_usd=args.fees,
    )
    if result is None:
        print(f"ERROR: could not mark {args.intent_id} as filled. Check status with 'list'.")
        return 1
    print(f"OK: {args.intent_id} marked FILLED at price={args.filled_price} amount=${args.filled_amount_usd}")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    result = mark_cancelled(args.intent_id, reason=args.reason)
    if result is None:
        print(f"ERROR: could not cancel {args.intent_id}. Check status with 'list'.")
        return 1
    print(f"OK: {args.intent_id} CANCELLED ({args.reason})")
    return 0


def cmd_expire(_args: argparse.Namespace) -> int:
    expired = expire_overdue()
    if not expired:
        print("No overdue orders to expire.")
        return 0
    print(f"Expired {len(expired)} order(s):")
    for o in expired:
        print(f"  {o['intent_id']}  {o['fiat']}/{o['asset']}  reason={o.get('reason')}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Detail view for a single order (any status)."""
    order = get_order(args.intent_id)
    if order is None:
        print(f"Order {args.intent_id} not found.")
        return 1
    print(f"intent_id     : {order['intent_id']}")
    print(f"status        : {order['status']}")
    print(f"fiat/asset    : {order['fiat']}/{order['asset']}")
    print(f"side          : {order['side']}")
    print(f"expected_price: {order['expected_price']}")
    print(f"amount_usd    : {order['amount_usd']}")
    print(f"deadline_ts   : {order['deadline_ts']}")
    print(f"stop_loss     : {order.get('stop_loss_price')}")
    print(f"take_profit   : {order.get('take_profit_price')}")
    print(f"max_loss_usd  : {order.get('max_loss_usd')}")
    print(f"opp_id        : {order.get('opp_id')}")
    print(f"filled_price  : {order.get('filled_price')}")
    print(f"filled_amount : {order.get('filled_amount_usd')}")
    print(f"filled_ts     : {order.get('filled_ts')}")
    print(f"fees_usd      : {order.get('fees_usd')}")
    print(f"reason        : {order.get('reason')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual P2P orders for Nightwing operator.")
    subs = parser.add_subparsers(dest="command", required=True)

    sub_list = subs.add_parser("list", help="List pending orders")
    sub_list.set_defaults(func=cmd_list)

    sub_show = subs.add_parser("show", help="Show details for a specific order")
    sub_show.add_argument("intent_id")
    sub_show.set_defaults(func=cmd_show)

    sub_fill = subs.add_parser("fill", help="Mark an order as filled")
    sub_fill.add_argument("intent_id")
    sub_fill.add_argument("filled_price", type=float)
    sub_fill.add_argument("filled_amount_usd", type=float)
    sub_fill.add_argument("--fees", type=float, default=0.0, help="Fees paid in USD")
    sub_fill.set_defaults(func=cmd_fill)

    sub_cancel = subs.add_parser("cancel", help="Cancel a pending order")
    sub_cancel.add_argument("intent_id")
    sub_cancel.add_argument("--reason", default="operator_cancel")
    sub_cancel.set_defaults(func=cmd_cancel)

    sub_expire = subs.add_parser("expire-overdue", help="Auto-expire orders past their deadline")
    sub_expire.set_defaults(func=cmd_expire)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
