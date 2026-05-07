#!/usr/bin/env python3
"""
NIGHTWING P2P Agent

Modes:
    SIMULATED - Fake data, no API calls
    PAPER     - Real prices, simulated trades
    LIVE      - BLOCKED (requires human gate)
"""

import argparse
import json
import logging
import math
import sys
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.market_data import fetch_prices, _get_mode  # noqa: E402
from core.lucius import check_jurisdiction  # noqa: E402
from core.batman_bridge import fetch_from_batman  # noqa: E402
from core.harvey import record_trade, print_summary  # noqa: E402
from core.gordon import run_all_checks as gordon_check  # noqa: E402
from core.notifier import alert_opportunity, alert_blocked, alert_autopause  # noqa: E402
from core.microstructure import compute_depth_metrics  # noqa: E402
from core.feature_logger import log_features  # noqa: E402

CONFIG_FILE = BASE_DIR / "config" / "settings.yaml"
PAIRS_FILE = BASE_DIR / "config" / "pairs.yaml"
LOG_FILE = BASE_DIR / "storage" / "logs" / "agent.log"
EXECUTIONS_FILE = BASE_DIR / "storage" / "logs" / "executions.jsonl"
KILL_SWITCH = BASE_DIR / "storage" / "KILL_SWITCH"

# Auto-pause: stop after this many consecutive blocks
MAX_CONSECUTIVE_BLOCKS = 3

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)
logger = logging.getLogger("nightwing.agent")


def load_config() -> Dict[str, Any]:
    try:
        if CONFIG_FILE.exists():
            return yaml.safe_load(CONFIG_FILE.read_text()) or {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return {}


def load_pairs() -> Dict[str, Any]:
    try:
        if PAIRS_FILE.exists():
            return yaml.safe_load(PAIRS_FILE.read_text()) or {}
    except Exception as e:
        logger.error(f"Failed to load pairs: {e}")
    return {}


def check_kill_switch() -> bool:
    if KILL_SWITCH.exists():
        logger.warning("KILL SWITCH ACTIVE")
        return True
    return False


def log_execution(execution: Dict[str, Any]) -> None:
    try:
        EXECUTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(EXECUTIONS_FILE, "a") as f:
            f.write(json.dumps(execution) + "\n")
    except Exception as e:
        logger.error(f"Failed to log execution: {e}")


def get_default_fiat() -> str:
    pairs_config = load_pairs()
    default_pair = pairs_config.get("default_pair", "USDT/MXN")
    return default_pair.split("/")[-1] if "/" in default_pair else "MXN"


def _build_feature_depth_payload(batman: Dict[str, Any]) -> Dict[str, Any] | None:
    if batman.get("status") == "ok":
        source = batman
    elif batman.get("status") == "stale":
        source = batman.get("data", {})
    else:
        return None

    buy_offers = source.get("buy_offers")
    if not isinstance(buy_offers, list):
        buy_offers = []

    sell_offers = source.get("sell_offers")
    if not isinstance(sell_offers, list):
        sell_offers = []

    if not buy_offers and not sell_offers:
        buy_offers, sell_offers = _build_summary_offers(source)

    best_buy = source.get("best_buy", source.get("p2p_buy_price"))
    best_sell = source.get("best_sell", source.get("p2p_sell_price"))

    if not buy_offers and not sell_offers and best_buy is None and best_sell is None:
        return None

    return {
        "buy_offers": buy_offers,
        "sell_offers": sell_offers,
        "best_buy": best_buy,
        "best_sell": best_sell,
    }


def _build_summary_offers(source: Dict[str, Any]) -> tuple[list[Dict[str, float]], list[Dict[str, float]]]:
    depth_estimate = source.get("depth_estimate")
    if not isinstance(depth_estimate, (int, float)) or depth_estimate <= 0:
        return [], []

    merchant_count = source.get("merchant_count")
    if isinstance(merchant_count, int) and merchant_count > 0:
        offers_per_side = max(1, math.ceil(merchant_count / 2))
    else:
        offers_per_side = 1

    offer_size = float(depth_estimate) / offers_per_side
    offers = [{"max_single_trans_amount_value": offer_size} for _ in range(offers_per_side)]
    return list(offers), list(offers)


def _log_cycle_features(batman: Dict[str, Any], cycle_id: int, timestamp: str) -> Dict[str, Any] | None:
    depth_payload = _build_feature_depth_payload(batman)
    if depth_payload is None:
        return None

    metrics = compute_depth_metrics(depth_payload)
    return log_features(metrics, cycle_id=cycle_id, timestamp=timestamp)


def run_cycle(
    mode: str, cycle_num: int, market_mode: str | None = None, last_opp_id: str | None = None
) -> Dict[str, Any]:
    cycle_start = datetime.now(timezone.utc)
    logger.info(f"{'='*60}")
    logger.info(f"CYCLE {cycle_num} - Mode: {mode}")
    if market_mode is None:
        market_mode = mode

    result = {
        "cycle": cycle_num,
        "ts": cycle_start.isoformat(),
        "mode": mode,
        "status": "pending",
    }

    if check_kill_switch():
        result["status"] = "killed"
        return result

    print(f"\n[Cycle {cycle_num}] Fetching market prices...")
    try:
        prices = fetch_prices(market_mode)
        result["prices"] = prices
        btc = prices["prices"].get("BTCUSDT", 0)
        eth = prices["prices"].get("ETHUSDT", 0)
        print(f"   BTC: ${btc:,.2f}")
        print(f"   ETH: ${eth:,.2f}")
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        result["status"] = "error"
        result["error"] = str(e)
        return result

    fiat = get_default_fiat()
    evaluated_amount_usd = 500.0
    executed_amount_usd = 0.0
    result["fiat"] = fiat
    result["amount_usd"] = evaluated_amount_usd
    result["evaluated_amount_usd"] = evaluated_amount_usd
    result["executed_amount_usd"] = executed_amount_usd

    # LUCIUS compliance check (BEFORE risk gate)
    print(f"\n[Cycle {cycle_num}] Checking compliance (LUCIUS)...")
    lucius = check_jurisdiction(fiat, evaluated_amount_usd)
    result["lucius"] = lucius

    if not lucius.get("approved", False):
        print(f"   LUCIUS BLOCKED: {lucius.get('blocked_by')}")
        result["status"] = "blocked"
        result["blocked_by"] = lucius.get("blocked_by")
        result["decision"] = "BLOCKED_COMPLIANCE"
        result["duration_ms"] = int((datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000)
        log_execution(result)
        return result

    for warning in lucius.get("warnings", []):
        print(f"   LUCIUS WARNING: {warning}")

    print(f"   LUCIUS APPROVED: {fiat} ${evaluated_amount_usd:.2f} USD")

    print(f"\n[Cycle {cycle_num}] Evaluating opportunity...")

    # BATMAN BRIDGE — primary data source
    print(f"\n[Cycle {cycle_num}] Fetching P2P data from Batman...")
    batman = fetch_from_batman(fiat)
    result["batman"] = batman

    if batman.get("status") == "ok":
        edge_net = batman.get("edge_net", 0)
        viable = batman.get("viable", False)
        premium = batman.get("p2p_premium", 0)
        depth_estimate = batman.get("depth_estimate")
        depth_text = f"{depth_estimate:,.0f}" if isinstance(depth_estimate, (int, float)) else "n/a"
        age_seconds = batman.get("age_seconds")
        age_text = f"{age_seconds:.0f}s" if isinstance(age_seconds, (int, float)) else "n/a"
        print(
            f"   🦇 USDT/{fiat} premium={premium*100:+.3f}% edge_net={edge_net:+.3f}% viable={'✅' if viable else '❌'}"
        )
        print(
            f"   spot={batman.get('spot_price')} buy={batman.get('p2p_buy_price')} sell={batman.get('p2p_sell_price')}"
        )
        print(f"   friction={batman.get('total_friction_pct')}% depth=${depth_text} age={age_text}")

        # DEDUP: Skip if same opportunity as last cycle
        current_opp_id = batman.get("opp_id")
        if current_opp_id and current_opp_id == last_opp_id:
            print(f"   ⏭️  SKIP — same opportunity as last cycle ({current_opp_id[:15]})")
            result["status"] = "skipped"
            result["decision"] = "SKIP_DUPLICATE"
            result["edge_net"] = edge_net
            result["opp_id"] = current_opp_id
            result["duration_ms"] = int((datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000)
            print(f"\n[Cycle {cycle_num}] Skipped in {result['duration_ms']}ms")
            return result

    elif batman.get("status") == "stale":
        print(f"   ⚠️  Batman data STALE ({batman.get('age_seconds', 0):.0f}s old) — using anyway with caution")
        stale_data = batman.get("data", {})
        edge_net = stale_data.get("edge_net", 0)
        viable = False
    else:
        print(f"   ❌ Batman bridge failed: {batman.get('error')}")
        edge_net = 0
        viable = False

    # GORDON security check (AFTER data, BEFORE decision)
    print(f"\n[Cycle {cycle_num}] Security check (GORDON)...")
    gordon = gordon_check(
        edge_net=edge_net,
        amount_usd=evaluated_amount_usd,
        batman_data=batman if batman.get("status") == "ok" else None,
    )
    result["gordon"] = gordon

    if not gordon.get("approved", False):
        blocked = gordon.get("blocked_by", ["unknown"])
        print(f"   🛡️  GORDON BLOCKED: {blocked}")
        alert_blocked(str(blocked))
        result["status"] = "blocked"
        result["blocked_by"] = f"gordon: {blocked}"
        result["decision"] = "BLOCKED_SECURITY"
        result["duration_ms"] = int((datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000)
        log_execution(result)
        record_trade(result)
        return result

    for warning in gordon.get("warnings", []):
        print(f"   🛡️  GORDON WARNING: {warning}")

    print("   🛡️  GORDON APPROVED")

    try:
        feature_record = _log_cycle_features(batman, cycle_num, result["ts"])
        if feature_record is not None:
            result["feature_record"] = feature_record
    except Exception as e:
        logger.error(f"Feature logging failed: {e}")

    result["edge_net"] = edge_net

    if not viable:
        print(f"   PASS - viable=False edge_net={edge_net:+.3f}%")
        result["decision"] = "PASS"
    else:
        print(f"   OPPORTUNITY - viable=True edge_net={edge_net:+.3f}%")
        result["decision"] = "OPPORTUNITY"

        # ALERT — notify Erick
        alert_opportunity(
            edge_net=edge_net,
            fiat=fiat,
            spot=batman.get("spot_price", 0),
            buy=batman.get("p2p_buy_price", 0),
            depth=batman.get("depth_estimate", 0) or 0,
            opp_id=batman.get("opp_id", ""),
        )

        if mode == "LIVE":
            result["action"] = "BLOCKED"
        elif mode == "PAPER":
            print("   SIMULATING trade (PAPER mode)")
            result["action"] = "SIMULATED_TRADE"
            result["executed_amount_usd"] = evaluated_amount_usd
        elif mode == "MANUAL_P2P":
            # Audit Section L.3 — Phase 3A
            # Generate a PENDING manual order with sizing + SL/TP from
            # RiskManager. Operator completes the trade on Binance P2P,
            # then runs `manual_orders_cli.py fill <intent_id> ...` to
            # close it. HARVEY records the trade only on FILLED.
            try:
                from core.manual_orders import create_order
                from core.risk_manager import RiskManager

                # Side is BUY for Nightwing's P2P USDT-vs-fiat path
                # (we always buy USDT cheap from a merchant when there's
                # premium edge to capture).
                _side = "BUY"
                _entry = float(batman.get("p2p_buy_price") or 0)
                _risk_mgr = RiskManager(
                    daily_capital_usd=10_000.0,
                    risk_per_trade_pct=0.01,
                )
                _plan = _risk_mgr.plan_position(entry_price=_entry, side=_side)
                # Validate against the daily loss budget.
                _ok, _why = _risk_mgr.validate_trade(_plan.max_loss_usd)
                if not _ok:
                    print(f"   🛑 Manual order BLOCKED by RiskManager: {_why}")
                    result["action"] = "BLOCKED_RISK_BUDGET"
                else:
                    _order = create_order(
                        fiat=fiat,
                        asset="USDT",
                        side=_side,
                        expected_price=_entry,
                        amount_usd=min(_plan.position_size_usd, evaluated_amount_usd),
                        stop_loss_price=_plan.stop_loss_price,
                        take_profit_price=_plan.take_profit_price,
                        max_loss_usd=_plan.max_loss_usd,
                        opp_id=batman.get("opp_id"),
                    )
                    print(
                        f"   📝 MANUAL P2P order created: {_order['intent_id']} " f"(deadline={_order['deadline_ts']})"
                    )
                    result["action"] = "MANUAL_P2P_PENDING"
                    result["manual_order"] = {
                        "intent_id": _order["intent_id"],
                        "expected_price": _order["expected_price"],
                        "amount_usd": _order["amount_usd"],
                        "stop_loss_price": _order["stop_loss_price"],
                        "take_profit_price": _order["take_profit_price"],
                        "deadline_ts": _order["deadline_ts"],
                    }
            except Exception as _exc:
                logger.error(f"Manual P2P order creation failed: {_exc}", exc_info=True)
                result["action"] = "ERROR_MANUAL_P2P"
                result["error"] = str(_exc)
        else:
            result["action"] = "LOGGED"

    result["status"] = "complete"
    result["duration_ms"] = int((datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000)
    log_execution(result)
    record_trade(result)
    print(f"\n[Cycle {cycle_num}] Complete in {result['duration_ms']}ms")
    return result


def main():
    parser = argparse.ArgumentParser(description="NIGHTWING P2P Agent")
    parser.add_argument(
        "--mode",
        choices=["simulated", "paper", "manual_p2p", "live"],
        help="simulated=fake prices; paper=real prices, simulated execution; "
        "manual_p2p=real prices, operator completes trade on Binance P2P "
        "(audit Section L.3 Phase 3A); live=BLOCKED until Phase 3B.",
    )
    parser.add_argument("--cycles", type=int, default=0)
    parser.add_argument("--live", action="store_true", help="Use live market ingestion for price fetching")
    args = parser.parse_args()

    mode = args.mode.upper() if args.mode else _get_mode()
    # MANUAL_P2P uses real market data (like PAPER) — flip to LIVE pricing
    # ingestion, since the operator needs accurate quotes to confirm the
    # trade on Binance P2P.
    market_mode = "LIVE" if (args.live or mode == "MANUAL_P2P") else mode

    if mode == "LIVE" and not args.live:
        print("ERROR: LIVE mode is BLOCKED.")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    NIGHTWING P2P AGENT                       ║
║  Mode: {mode:<10}  Cycles: {args.cycles if args.cycles else 'Continuous':<10}              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    config = load_config()
    interval = config.get("cycle", {}).get("interval_seconds", 300)
    cycle_num = 0
    max_cycles = args.cycles if args.cycles > 0 else float("inf")
    consecutive_blocks = 0
    last_opp_id = None

    try:
        while cycle_num < max_cycles:
            cycle_num += 1
            result = run_cycle(mode, cycle_num, market_mode=market_mode, last_opp_id=last_opp_id)

            if result.get("status") == "killed":
                break

            # Update last_opp_id from batman data
            batman_data = result.get("batman", {})
            current_opp_id = batman_data.get("opp_id")
            if current_opp_id and result.get("decision") not in ("SKIP_DUPLICATE",):
                last_opp_id = current_opp_id

            # Auto-pause: track consecutive blocks
            if result.get("status") == "blocked":
                consecutive_blocks += 1
                if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                    blocked_by = result.get("blocked_by", "unknown")
                    print(f"\n⏸️  AUTO-PAUSE: {consecutive_blocks} consecutive blocks ({blocked_by})")
                    print("   Agent will stop to avoid wasting cycles.")
                    alert_autopause(str(blocked_by))
                    logger.warning(f"Auto-pause triggered: {consecutive_blocks} consecutive blocks — {blocked_by}")
                    break
            elif result.get("status") != "skipped":
                consecutive_blocks = 0

            if cycle_num < max_cycles:
                print(f"\nNext cycle in {interval}s...")
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nAgent stopped by user.")

    print(f"\nCompleted {cycle_num} cycle(s).")
    print_summary()


if __name__ == "__main__":
    main()
