"""
BATMAN BRIDGE — Reads latest verified data from Batman Flow Engine.

Source: batman_flow_engine/storage/logs/opportunities.jsonl
Rule: Bridge is PRIMARY source. market_data.py is FALLBACK only.

Configuration:
- Set BATMAN_BASE_PATH in .env to override default location
- Default: auto-detects relative to nightwing_agent location
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("nightwing.batman_bridge")

# === CONFIGURABLE PATH ===
# Priority: 1) ENV var, 2) Relative to this file, 3) Fallback to home
BATMAN_BASE = Path(os.getenv("BATMAN_BASE_PATH", str(Path(__file__).resolve().parents[2] / "batman_flow_engine")))

BATMAN_OPPS = BATMAN_BASE / "storage" / "logs" / "opportunities.jsonl"
BATMAN_LATEST = BATMAN_BASE / "storage" / "latest.json"
MAX_STALENESS_SECONDS = 1200  # 20 minutes


def verify_bridge() -> bool:
    """
    Verifica que el puente Batman está conectado y funcionando.
    Returns:
        True if both files exist and are accessible
    """
    opps_exists = BATMAN_OPPS.exists()
    latest_exists = BATMAN_LATEST.exists()

    if not opps_exists:
        logger.warning("⚠️  Batman bridge DESCONECTADO: opportunities.jsonl no existe")
        logger.warning(f"    Esperado en: {BATMAN_OPPS}")
        logger.warning(f"    BATMAN_BASE_PATH actual: {BATMAN_BASE}")
        return False

    if not latest_exists:
        logger.warning(f"⚠️  Batman latest.json no encontrado: {BATMAN_LATEST}")
        # No es crítico, puede funcionar solo con opportunities
