"""
NIGHTWING ALERT NOTIFIER — Sounds + desktop notification when opportunity detected.

Used by agent.py to alert Erick when a real trade opportunity appears.
On macOS: uses osascript for notification + afplay for sound.
"""

import subprocess
import logging
import platform

logger = logging.getLogger("nightwing.notifier")


def notify(title: str, message: str, sound: bool = True) -> None:
    """Send desktop notification with optional sound."""
    system = platform.system()

    if system == "Darwin":  # macOS
        try:
            # Desktop notification
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)

            # Extra alert sound for attention
            if sound:
                subprocess.run(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    capture_output=True,
                    timeout=5,
                )
        except Exception as e:
            logger.error(f"Notification failed: {e}")
    else:
        # Fallback: terminal bell
        print("\a")
        logger.info(f"ALERT: {title} — {message}")


def alert_opportunity(edge_net: float, fiat: str, spot: float, buy: float, depth: float, opp_id: str) -> None:
    """Alert for a trade opportunity — the main alert Erick needs."""
    title = f"🦇 OPPORTUNITY USDT/{fiat}"
    message = f"Edge: +{edge_net:.3f}% | Buy: {buy} | Spot: {spot} | Depth: ${depth:,.0f}"
    notify(title, message, sound=True)


def alert_blocked(reason: str) -> None:
    """Alert when something blocks trading — less urgent."""
    notify("🛡️ NIGHTWING BLOCKED", reason, sound=False)


def alert_autopause(reason: str) -> None:
    """Alert when agent auto-pauses — needs attention."""
    notify("⏸️ NIGHTWING PAUSED", reason, sound=True)
