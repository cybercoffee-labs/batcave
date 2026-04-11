#!/usr/bin/env python3
"""
test_breaker.py — Batman Flow Engine / DQ Breaker Test
=======================================================
Objetivo: Inyectar suficientes tickers inválidos en config.yaml para que
  overall_ratio caiga bajo 0.60 y el breaker se active (DATA_DEGRADED).

USO:
  python test_breaker.py --inject    # backup + inyecta fakes + corre engine + valida
  python test_breaker.py --revert    # restaura config.yaml desde backup
  python test_breaker.py --validate  # solo valida latest.json (sin correr engine)
  python test_breaker.py --status    # muestra estado actual de DQ sin modificar nada
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import datetime

# ─────────────────────────────────────────────
# CONFIG — ajusta si tu estructura difiere
# ─────────────────────────────────────────────
CONFIG_YAML = pathlib.Path("config.yaml")
CONFIG_BACKUP = pathlib.Path("config.yaml.bak_breaker_test")
LATEST_JSON = pathlib.Path("storage/latest.json")
ENGINE_LOCK = pathlib.Path("storage/engine.lock")
PYTHON_BIN = "./.venv/bin/python"
ENGINE_SCRIPT = "engine.py"

# Cuántos fakes inyectar. Con 21 equities, necesitas >= 9 fakes para ratio < 0.60
# (20 equities reales - 8 más fake = 12 ok / 21 = 0.571 < 0.60)
# Usamos 9 para tener margen.
N_FAKES_TO_INJECT = 9
FAKE_PREFIX = "ZZFAKE"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────


def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "✓", "WARN": "⚠", "ERROR": "✗", "HEAD": "►"}.get(level, "·")
    print(f"[{ts}] {prefix}  {msg}")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_config():
    return CONFIG_YAML.read_text(encoding="utf-8")


def write_config(text):
    CONFIG_YAML.write_text(text, encoding="utf-8")


def backup_config():
    if CONFIG_BACKUP.exists():
        log(f"Backup previo encontrado: {CONFIG_BACKUP} — lo sobreescribimos", "WARN")
    shutil.copy2(CONFIG_YAML, CONFIG_BACKUP)
    log(f"Backup creado: {CONFIG_BACKUP}")


def revert_config():
    if not CONFIG_BACKUP.exists():
        log(f"No existe backup en {CONFIG_BACKUP} — nada que revertir", "ERROR")
        sys.exit(1)
    shutil.copy2(CONFIG_BACKUP, CONFIG_YAML)
    log(f"config.yaml restaurado desde {CONFIG_BACKUP}")
    CONFIG_BACKUP.unlink()
    log("Backup eliminado")


def clean_lock():
    """Mata procesos engine.py y limpia lockfile stale."""
    subprocess.run(["pkill", "-f", ENGINE_SCRIPT], capture_output=True)
    if ENGINE_LOCK.exists():
        ENGINE_LOCK.unlink()
        log(f"Lockfile eliminado: {ENGINE_LOCK}")


def inject_fakes(n=N_FAKES_TO_INJECT):
    """
    Reemplaza los primeros N tickers REALES en el bloque equities: con ZZFAKE_XX.
    Opera SOLO dentro del bloque equities: hasta la siguiente sección de primer nivel.
    No usa regex global — parsea línea por línea para máxima seguridad.
    """
    text = read_config()
    lines = text.splitlines()

    in_equities = False
    replaced = 0
    new_lines = []
    injected_names = []

    for line in lines:
        # Detectar inicio del bloque equities:
        if re.match(r"^\s+equities\s*:", line):
            in_equities = True
            new_lines.append(line)
            continue

        # Detectar fin del bloque equities (otra key de primer nivel)
        if in_equities and re.match(r"^\s+crypto\s*:", line):
            in_equities = False

        # Dentro de equities, sustituir los primeros N items que sean tickers reales
        if in_equities and replaced < n:
            # Línea tipo: "  - SPY" o "  - AAPL" (con o sin guion)
            m = re.match(r"^(\s*-\s*)([A-Z][A-Z0-9._/-]{0,19})(\s*)$", line)
            if m:
                prefix_ws, ticker, trailing = m.groups()
                # No reemplazar si ya es fake o el ticker de prueba existente
                if not ticker.startswith(FAKE_PREFIX) and not ticker.endswith("_FAKE_TEST"):
                    fake_name = f"{FAKE_PREFIX}{replaced+1:02d}"
                    injected_names.append((ticker, fake_name))
                    new_lines.append(f"{prefix_ws}{fake_name}{trailing}")
                    replaced += 1
                    continue

        new_lines.append(line)

    if replaced < n:
        log(f"Solo se pudieron inyectar {replaced}/{n} fakes. Revisa formato de config.yaml", "WARN")
    else:
        log(f"Inyectados {replaced} tickers fake en bloque equities:")
        for orig, fake in injected_names:
            log(f"  {orig:12s} → {fake}")

    write_config("\n".join(new_lines))
    return replaced, injected_names


def run_engine():
    log("Corriendo engine.py...", "HEAD")
    clean_lock()
    result = subprocess.run([PYTHON_BIN, ENGINE_SCRIPT], capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Engine terminó con código {result.returncode}", "WARN")
        if result.stderr:
            print("--- STDERR ---")
            print(result.stderr[-2000:])  # últimas 2000 chars
    else:
        log("Engine completado OK")
    return result.returncode


# ─────────────────────────────────────────────
# VALIDACIONES
# ─────────────────────────────────────────────


def validate_breaker_active():
    """Afirma que el breaker se activó correctamente."""
    if not LATEST_JSON.exists():
        log(f"No existe {LATEST_JSON}", "ERROR")
        return False

    data = load_json(LATEST_JSON)
    dq = data.get("dq", {})
    stress = data.get("stress", {})
    meta = data.get("meta", {})

    ok = True
    failures = []

    # 1) overall_ratio debe ser < 0.60
    eq_ratio = dq.get("equities_ok_ratio", 1.0)
    cr_ratio = dq.get("crypto_ok_ratio", 1.0)
    overall = min(eq_ratio, cr_ratio)
    if overall >= 0.60:
        failures.append(f"overall_ratio = {overall:.3f} — esperado < 0.60 para activar breaker")
        ok = False

    # 2) overall_status debe ser "degraded"
    status = dq.get("overall_status", "")
    if status != "degraded":
        failures.append(f"overall_status = '{status}' — esperado 'degraded'")
        ok = False

    # 3) breaker_triggered debe ser True
    breaker = dq.get("breaker_triggered", False)
    if not breaker:
        failures.append("breaker_triggered = False — esperado True")
        ok = False

    # 4) regime.label debe ser DATA_DEGRADED
    regime_label = stress.get("regime", {}).get("label", "")
    if regime_label != "DATA_DEGRADED":
        failures.append(f"stress.regime.label = '{regime_label}' — esperado 'DATA_DEGRADED'")
        ok = False

    # 5) dq_breaker debe estar en triggers
    triggers = stress.get("regime", {}).get("triggers", [])
    if "dq_breaker" not in triggers:
        failures.append(f"'dq_breaker' no está en stress.regime.triggers: {triggers}")
        ok = False

    # ── Reporte ──
    log("", "HEAD")
    log("RESULTADO VALIDACIÓN BREAKER", "HEAD")
    log(f"  equities_ok_ratio : {eq_ratio:.3f}")
    log(f"  crypto_ok_ratio   : {cr_ratio:.3f}")
    log(f"  overall_ratio     : {overall:.3f}")
    log(f"  overall_status    : {status}")
    log(f"  breaker_triggered : {breaker}")
    log(f"  regime.label      : {regime_label}")
    log(f"  triggers          : {triggers}")
    log(f"  equities_total    : {meta.get('equities_total')}, equities_ok: {meta.get('equities_ok')}")
    log("")

    if ok:
        log("✅  BREAKER TEST PASSED — sistema se comporta correctamente ante degradación", "HEAD")
    else:
        log("❌  BREAKER TEST FAILED — fallos:", "ERROR")
        for f in failures:
            log(f"    • {f}", "ERROR")

    return ok


def validate_normal_state():
    """Valida estado saludable (post-revert, con SPY_FAKE_TEST incluido)."""
    if not LATEST_JSON.exists():
        log(f"No existe {LATEST_JSON}", "ERROR")
        return False

    data = load_json(LATEST_JSON)
    dq = data.get("dq", {})

    eq_ratio = dq.get("equities_ok_ratio", 0.0)
    status = dq.get("overall_status", "")
    breaker = dq.get("breaker_triggered", True)

    ok = status == "ok" and not breaker and eq_ratio >= 0.85

    log("ESTADO DQ ACTUAL", "HEAD")
    log(f"  equities_ok_ratio : {eq_ratio:.3f}")
    log(f"  overall_status    : {status}")
    log(f"  breaker_triggered : {breaker}")

    if ok:
        log("✅  Estado OK — DQ saludable, breaker inactivo")
    else:
        log("⚠   Estado no-nominal — revisa si hay fakes activos en config.yaml", "WARN")

    return ok


def show_status():
    """Muestra estado actual sin modificar nada."""
    if not LATEST_JSON.exists():
        log(f"{LATEST_JSON} no existe — corre el engine primero", "WARN")
        return

    data = load_json(LATEST_JSON)
    dq = data.get("dq", {})
    meta = data.get("meta", {})
    stress = data.get("stress", {})

    log("══════════════════════════════════", "HEAD")
    log("  ESTADO ACTUAL — batman_flow_engine", "HEAD")
    log("══════════════════════════════════", "HEAD")
    log(f"  equities_total    : {meta.get('equities_total')}")
    log(f"  equities_ok       : {meta.get('equities_ok')}")
    log(f"  crypto_total      : {meta.get('crypto_total')}")
    log(f"  crypto_ok         : {meta.get('crypto_ok')}")
    log(f"  errors            : {meta.get('errors')}")
    log(f"  duration_sec      : {meta.get('duration_sec', '?')}")
    log("  ─────────────────────────────")
    log(f"  equities_ok_ratio : {dq.get('equities_ok_ratio')}")
    log(f"  crypto_ok_ratio   : {dq.get('crypto_ok_ratio')}")
    log(f"  overall_status    : {dq.get('overall_status')}")
    log(f"  breaker_triggered : {dq.get('breaker_triggered')}")
    log(f"  regime.label      : {stress.get('regime', {}).get('label')}")
    log(f"  triggers          : {stress.get('regime', {}).get('triggers')}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Batman Flow Engine — DQ Breaker Test")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inject", action="store_true", help="Backup + inyecta fakes + corre engine + valida breaker")
    group.add_argument("--revert", action="store_true", help="Restaura config.yaml desde backup")
    group.add_argument("--validate", action="store_true", help="Solo valida latest.json (sin correr engine)")
    group.add_argument("--status", action="store_true", help="Muestra estado DQ actual sin modificar nada")
    args = parser.parse_args()

    # Verificar que estamos en el directorio correcto
    if not CONFIG_YAML.exists():
        log(f"No se encuentra {CONFIG_YAML} — ¿estás en el directorio del proyecto?", "ERROR")
        log(f"Directorio actual: {pathlib.Path.cwd()}")
        sys.exit(1)

    if args.status:
        show_status()

    elif args.validate:
        if not validate_breaker_active():
            sys.exit(1)

    elif args.inject:
        log("═══ INICIO TEST BREAKER ═══", "HEAD")

        # 1) Backup
        backup_config()

        # 2) Inyectar fakes
        replaced, names = inject_fakes(N_FAKES_TO_INJECT)
        if replaced == 0:
            log("No se inyectó ningún fake — abortando y revirtiendo", "ERROR")
            revert_config()
            sys.exit(1)

        # 3) Correr engine
        rc = run_engine()
        if rc != 0:
            log(f"Engine terminó con error (rc={rc}) — el JSON puede estar incompleto", "WARN")

        # 4) Validar
        passed = validate_breaker_active()

        # 5) Resultado final
        log("")
        if passed:
            log("🎯  Test completo. El breaker funciona correctamente.", "HEAD")
            log("   config.yaml TODAVÍA tiene los fakes inyectados.")
            log("   Para revertir: python test_breaker.py --revert")
        else:
            log("💥  Alguna aserción falló. Revisa el output arriba.", "ERROR")
            log("   Para revertir: python test_breaker.py --revert")
        sys.exit(0 if passed else 1)

    elif args.revert:
        log("═══ REVERT CONFIG ═══", "HEAD")
        revert_config()
        log("")
        log("config.yaml restaurado. Corre el engine para actualizar latest.json:")
        log("  pkill -f engine.py 2>/dev/null; rm -f storage/engine.lock")
        log("  ./.venv/bin/python engine.py")
        log("")
        log("Luego verifica estado con:")
        log("  python test_breaker.py --status")


if __name__ == "__main__":
    main()
