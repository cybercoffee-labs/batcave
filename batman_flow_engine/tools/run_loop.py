#!/usr/bin/env python3
"""
Automatic Loop Runner for Batman Flow Engine

Runs engine.run_engine() every 20 minutes indefinitely with error handling and logging.

Usage:
    python tools/run_loop.py           # Run continuous loop
    python tools/run_loop.py --test    # Run single cycle for testing
"""

import sys
import time
import signal
import argparse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine import run_engine

# ── Configuration ────────────────────────────────────────────────────────────
INTERVAL_SECONDS = 20 * 60  # 20 minutes
LOG_FILE = BASE_DIR / "storage" / "logs" / "loop.log"

# Ensure log directory exists
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Global State ─────────────────────────────────────────────────────────────
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_requested
    print("\n⚠️  Shutdown signal received. Finishing current cycle...")
    shutdown_requested = True


def log_message(message: str, to_file: bool = True):
    """
    Print and optionally log a message with timestamp.

    Args:
        message: Message to log
        to_file: Whether to append to log file
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    formatted = f"[{timestamp}] {message}"

    print(formatted)

    if to_file:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception as e:
            print(f"  ⚠️  Failed to write to log file: {e}")


def run_cycle(cycle_number: int) -> bool:
    """
    Execute a single engine cycle.

    Args:
        cycle_number: Current cycle number

    Returns:
        True if successful, False if error occurred
    """
    log_message(f"─── CYCLE #{cycle_number} START ───")

    try:
        result = run_engine()
        if result.get("status") == "already_running":
            log_message(f"⚠ CYCLE #{cycle_number} SKIPPED (engine lock already present)")
            return False

        log_message(f"✓ CYCLE #{cycle_number} COMPLETED SUCCESSFULLY")
        return True

    except Exception as e:
        log_message(f"✗ CYCLE #{cycle_number} ERROR: {type(e).__name__}: {e}")
        return False


def run_single_cycle():
    """Run a single test cycle and exit."""
    log_message("═══ TEST MODE: Single Cycle ═══")
    success = run_cycle(1)

    if success:
        log_message("═══ TEST COMPLETED SUCCESSFULLY ═══")
        sys.exit(0)
    else:
        log_message("═══ TEST FAILED ═══")
        sys.exit(1)


def run_continuous_loop():
    """Run continuous loop every 20 minutes."""
    global shutdown_requested

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log_message("═══ BATMAN FLOW ENGINE LOOP STARTED ═══")
    log_message(f"Interval: {INTERVAL_SECONDS // 60} minutes")
    log_message(f"Log file: {LOG_FILE}")
    log_message("Press Ctrl+C to stop gracefully")

    cycle_number = 0

    while not shutdown_requested:
        cycle_number += 1

        # Run cycle
        success = run_cycle(cycle_number)

        # Check if shutdown was requested during cycle
        if shutdown_requested:
            break

        # Wait for next cycle
        if not shutdown_requested:
            next_run = datetime.now(timezone.utc).timestamp() + INTERVAL_SECONDS
            next_run_time = datetime.fromtimestamp(next_run, tz=timezone.utc).strftime("%H:%M:%S UTC")

            log_message(f"⏳ Waiting {INTERVAL_SECONDS // 60} minutes until next cycle...")
            log_message(f"   Next run at: {next_run_time}")

            # Sleep in 1-second intervals to check for shutdown signal
            elapsed = 0
            while elapsed < INTERVAL_SECONDS and not shutdown_requested:
                time.sleep(1)
                elapsed += 1

    log_message("═══ LOOP STOPPED GRACEFULLY ═══")
    log_message(f"Total cycles completed: {cycle_number}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Batman Flow Engine in a loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/run_loop.py           # Run continuous loop
  python tools/run_loop.py --test    # Run single test cycle
        """,
    )

    parser.add_argument("--test", action="store_true", help="Run single cycle for testing (no loop)")

    args = parser.parse_args()

    # Run in test or continuous mode
    if args.test:
        run_single_cycle()
    else:
        run_continuous_loop()


if __name__ == "__main__":
    main()
