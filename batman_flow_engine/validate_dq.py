#!/usr/bin/env python3
"""
validate_dq.py — Batman Flow Engine / Validación continua de DQ
================================================================
Valida que latest.json cumpla el contrato de Data Quality.
Úsalo después de cada ejecución del engine para detección temprana de problemas.

USO:
  python validate_dq.py                  # valida estado nominal (ok, sin breaker)
  python validate_dq.py --expect degraded # valida que el breaker esté activo
  python validate_dq.py --report          # reporte completo sin assertions (siempre sale 0)

INTEGRACIÓN (crontab / post-run):
  ./.venv/bin/python engine.py && python validate_dq.py
"""

import argparse
import json
import pathlib
import sys
import datetime

LATEST_JSON = pathlib.Path("storage/latest.json")

STATUS_CONTRACT = {
    "equities": {"ok", "ok_daily"},
    "crypto": {"ok"},
}

KNOWN_NON_OK_STATUSES = {"no_daily", "no_intraday", "error", "timeout", "empty"}


def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "  ", "OK": "✅", "WARN": "⚠️ ", "ERROR": "❌", "HEAD": "►"}
    print(f"[{ts}] {icons.get(level, '  ')} {msg}")


def load_latest():
    if not LATEST_JSON.exists():
        log(f"No existe {LATEST_JSON} — corre el engine primero", "ERROR")
        sys.exit(1)
    with open(LATEST_JSON, encoding="utf-8") as f:
        return json.load(f)


def run_validation(data, expect_degraded=False):
    """
    Ejecuta todas las validaciones de DQ.
    Retorna (passed: bool, failures: list[str], warnings: list[str])
    """
    failures = []
    warnings = []

    dq = data.get("dq", {})
    meta = data.get("meta", {})
    stress = data.get("stress", {})
    equities = data.get("equities", {})
    crypto = data.get("crypto", {})

    # ──────────────────────────────────────────
    # A) Consistencia meta vs conteo manual
    # ──────────────────────────────────────────
    manual_eq_ok = sum(1 for v in equities.values() if v.get("status") in STATUS_CONTRACT["equities"])
    manual_cr_ok = sum(1 for v in crypto.values() if v.get("status") in STATUS_CONTRACT["crypto"])
    meta_eq_ok = meta.get("equities_ok", -1)
    meta_cr_ok = meta.get("crypto_ok", -1)

    if manual_eq_ok != meta_eq_ok:
        failures.append(
            f"[CONSISTENCY] meta.equities_ok={meta_eq_ok} pero conteo real={manual_eq_ok} " f"— bug en criterio de ok"
        )

    if manual_cr_ok != meta_cr_ok:
        failures.append(f"[CONSISTENCY] meta.crypto_ok={meta_cr_ok} pero conteo real={manual_cr_ok}")

    # ──────────────────────────────────────────
    # B) Ratios coherentes con meta
    # ──────────────────────────────────────────
    eq_total = meta.get("equities_total", 0)
    cr_total = meta.get("crypto_total", 0)

    if eq_total > 0:
        expected_eq_ratio = round(meta_eq_ok / eq_total, 3)
        actual_eq_ratio = round(dq.get("equities_ok_ratio", -1), 3)
        if abs(expected_eq_ratio - actual_eq_ratio) > 0.005:
            failures.append(
                f"[RATIO] equities_ok_ratio={actual_eq_ratio} pero "
                f"debería ser {expected_eq_ratio} ({meta_eq_ok}/{eq_total})"
            )

    if cr_total > 0:
        expected_cr_ratio = round(meta_cr_ok / cr_total, 3)
        actual_cr_ratio = round(dq.get("crypto_ok_ratio", -1), 3)
        if abs(expected_cr_ratio - actual_cr_ratio) > 0.005:
            failures.append(
                f"[RATIO] crypto_ok_ratio={actual_cr_ratio} pero "
                f"debería ser {expected_cr_ratio} ({meta_cr_ok}/{cr_total})"
            )

    # ──────────────────────────────────────────
    # C) Estado DQ vs thresholds
    # ──────────────────────────────────────────
    overall = min(dq.get("equities_ok_ratio", 0), dq.get("crypto_ok_ratio", 0))
    status = dq.get("overall_status", "")
    breaker = dq.get("breaker_triggered", None)

    expected_status = "ok" if overall >= 0.85 else "partial" if overall >= 0.60 else "degraded"
    expected_breaker = overall < 0.60

    if status != expected_status:
        failures.append(
            f"[STATUS] overall_status='{status}' pero overall_ratio={overall:.3f} " f"implica '{expected_status}'"
        )

    if breaker != expected_breaker:
        failures.append(
            f"[BREAKER] breaker_triggered={breaker} pero overall_ratio={overall:.3f} "
            f"implica breaker={expected_breaker}"
        )

    # ──────────────────────────────────────────
    # D) Breaker → régimen DATA_DEGRADED
    # ──────────────────────────────────────────
    regime_label = stress.get("regime", {}).get("label", "")
    triggers = stress.get("regime", {}).get("triggers", [])

    if breaker:
        if regime_label != "DATA_DEGRADED":
            failures.append(
                f"[BREAKER_REGIME] breaker=True pero regime.label='{regime_label}' " f"(esperado 'DATA_DEGRADED')"
            )
        if "dq_breaker" not in triggers:
            failures.append(f"[BREAKER_TRIGGER] 'dq_breaker' no está en triggers: {triggers}")
    else:
        if regime_label == "DATA_DEGRADED":
            warnings.append(f"[REGIME] breaker=False pero regime.label='{regime_label}' " f"— ¿se resetó el engine?")

    # ──────────────────────────────────────────
    # E) Assets no-ok conocidos (auditoría)
    # ──────────────────────────────────────────
    eq_nok = [
        (sym, v.get("status")) for sym, v in equities.items() if v.get("status") not in STATUS_CONTRACT["equities"]
    ]
    cr_nok = [(sym, v.get("status")) for sym, v in crypto.items() if v.get("status") not in STATUS_CONTRACT["crypto"]]

    if eq_nok:
        warnings.append(
            f"[NON_OK_EQUITIES] {len(eq_nok)} equities no-ok: " + ", ".join(f"{s}={st}" for s, st in eq_nok[:5])
        )
    if cr_nok:
        warnings.append(
            f"[NON_OK_CRYPTO] {len(cr_nok)} crypto no-ok: " + ", ".join(f"{s}={st}" for s, st in cr_nok[:3])
        )

    # ──────────────────────────────────────────
    # F) Expectativa de test
    # ──────────────────────────────────────────
    if expect_degraded:
        if not breaker:
            failures.append("[EXPECT] Se esperaba estado degraded/breaker=True pero el estado es nominal")
    else:
        if breaker:
            failures.append(
                "[EXPECT] Se esperaba estado nominal pero el breaker está activo — "
                "¿hay fakes inyectados en config.yaml?"
            )

    return len(failures) == 0, failures, warnings


def print_report(data, failures, warnings):
    dq = data.get("dq", {})
    meta = data.get("meta", {})
    stress = data.get("stress", {})

    log("══════════════════════════════════════════", "HEAD")
    log("  DQ VALIDATION REPORT — batman_flow_engine", "HEAD")
    log("══════════════════════════════════════════", "HEAD")
    log(f"  equities : {meta.get('equities_ok')}/{meta.get('equities_total')} ok   ratio={dq.get('equities_ok_ratio')}")
    log(f"  crypto   : {meta.get('crypto_ok')}/{meta.get('crypto_total')} ok   ratio={dq.get('crypto_ok_ratio')}")
    log(f"  status   : {dq.get('overall_status')}  |  breaker={dq.get('breaker_triggered')}")
    log(f"  regime   : {stress.get('regime', {}).get('label')}  triggers={stress.get('regime', {}).get('triggers')}")
    log(f"  errors   : {meta.get('errors')}")
    log(f"  duration : {meta.get('duration_sec', '?')}s")
    log("")

    if warnings:
        for w in warnings:
            log(w, "WARN")
        log("")

    if failures:
        log(f"FAILED — {len(failures)} assertion(s):", "ERROR")
        for f in failures:
            log(f"  • {f}", "ERROR")
    else:
        log("ALL ASSERTIONS PASSED", "OK")


def main():
    parser = argparse.ArgumentParser(description="Batman Flow Engine — DQ Validator")
    parser.add_argument("--expect", choices=["ok", "degraded"], default="ok", help="Estado DQ esperado (default: ok)")
    parser.add_argument("--report", action="store_true", help="Solo muestra reporte, no falla aunque haya errores")
    args = parser.parse_args()

    data = load_latest()
    expect_degraded = args.expect == "degraded"
    passed, failures, warnings = run_validation(data, expect_degraded=expect_degraded)
    print_report(data, failures, warnings)

    if args.report:
        sys.exit(0)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
