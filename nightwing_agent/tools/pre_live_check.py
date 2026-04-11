#!/usr/bin/env python3
"""
PRE-LIVE CHECKLIST — Run before starting a LIVE/PAPER trading session.

Verifies all systems are ready:
  1. Batman running and producing fresh data
  2. Nightwing modules importable
  3. GORDON checks passing
  4. LUCIUS compliance ok
  5. Kill switch off
  6. Ledger writable
  7. Config valid

Run: python tools/pre_live_check.py
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def check(name: str, passed: bool, detail: str = "") -> bool:
    icon = "✅" if passed else "❌"
    msg = f"  {icon} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return passed


def run_checklist() -> bool:
    print("\n🦇 NIGHTWING PRE-LIVE CHECKLIST")
    print("=" * 50)

    all_pass = True

    # 1. Batman alive
    try:
        from core.batman_bridge import is_batman_alive, fetch_from_batman

        alive = is_batman_alive()
        all_pass &= check(
            "Batman alive", alive, "latest.json < 20 min" if alive else "Batman NOT running or data stale"
        )

        if alive:
            data = fetch_from_batman("MXN")
            fresh = data.get("status") == "ok"
            age = data.get("age_seconds", 9999)
            all_pass &= check(
                "Batman bridge MXN",
                fresh,
                f"age={age:.0f}s edge={data.get('edge_net', 'N/A')}%" if fresh else f"status={data.get('status')}",
            )
    except Exception as e:
        all_pass &= check("Batman bridge", False, str(e))

    # 2. Core modules importable
    modules = [
        ("core.lucius", "LUCIUS"),
        ("core.gordon", "GORDON"),
        ("core.harvey", "HARVEY"),
        ("core.market_data", "Market Data"),
        ("core.notifier", "Notifier"),
    ]
    for mod, name in modules:
        try:
            __import__(mod)
            all_pass &= check(f"{name} module", True)
        except Exception as e:
            all_pass &= check(f"{name} module", False, str(e))

    # 3. LUCIUS compliance
    try:
        from core.lucius import check_jurisdiction

        result = check_jurisdiction("MXN", 500)
        approved = result.get("approved", False)
        all_pass &= check(
            "LUCIUS MXN $500", approved, result.get("blocked_by", "approved") if not approved else "approved"
        )
    except Exception as e:
        all_pass &= check("LUCIUS check", False, str(e))

    # 4. GORDON security
    try:
        from core.gordon import run_all_checks

        result = run_all_checks(edge_net=0.5, amount_usd=500)
        approved = result.get("approved", False)
        blocked = result.get("blocked_by")
        all_pass &= check("GORDON security", approved, str(blocked) if not approved else "all 4 checks pass")
    except Exception as e:
        all_pass &= check("GORDON check", False, str(e))

    # 5. Kill switch
    ks = BASE_DIR / "storage" / "KILL_SWITCH"
    ks_off = not ks.exists()
    all_pass &= check("Kill switch OFF", ks_off, "ACTIVE — remove storage/KILL_SWITCH" if not ks_off else "not active")

    # 6. Ledger writable
    ledger = BASE_DIR / "storage" / "ledger" / "trades.jsonl"
    ledger_dir = ledger.parent
    try:
        ledger_dir.mkdir(parents=True, exist_ok=True)
        test_file = ledger_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        all_pass &= check("Ledger writable", True, str(ledger))
    except Exception as e:
        all_pass &= check("Ledger writable", False, str(e))

    # 7. Config valid
    try:
        import yaml

        config = yaml.safe_load((BASE_DIR / "config" / "settings.yaml").read_text())
        mode = config.get("mode", "UNKNOWN")
        interval = config.get("cycle", {}).get("interval_seconds", "?")
        all_pass &= check("Config valid", True, f"mode={mode} interval={interval}s")
    except Exception as e:
        all_pass &= check("Config valid", False, str(e))

    # 8. Executions file clean (check daily exposure)
    try:
        from core.lucius import get_daily_exposure

        exposure = get_daily_exposure("MXN")
        all_pass &= check("Daily exposure", True, f"${exposure:.2f} USD today")
    except Exception as e:
        all_pass &= check("Daily exposure", False, str(e))

    # 9. Tests passing (quick check)
    print("\n  ℹ️  Run 'python -m pytest tests/ -q' separately to verify 126 tests")

    # Summary
    print("\n" + "=" * 50)
    if all_pass:
        print("  🟢 ALL CHECKS PASSED — Ready to trade")
    else:
        print("  🔴 SOME CHECKS FAILED — Fix before trading")

    return all_pass


if __name__ == "__main__":
    passed = run_checklist()
    sys.exit(0 if passed else 1)
