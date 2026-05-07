#!/usr/bin/env python3
"""
Automatic Loop Runner for Batman Flow Engine.

Runs engine.run_engine() every 20 minutes indefinitely with self-healing,
health checks, daily summaries, and graceful shutdown.

Usage:
    python tools/run_loop.py                          # Run continuous loop
    python tools/run_loop.py --test                   # Run single cycle for testing
    python tools/run_loop.py --max-cycles 2           # Stop after 2 cycles
    python tools/run_loop.py --interval-seconds 5     # Override wait for local testing
"""

from __future__ import annotations

import argparse
import io
import logging
import signal
import sys
import time
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.startup_check import run_all_checks  # noqa: E402
from engine import run_engine  # noqa: E402
from tools.make_daily_summary import main as make_daily_summary  # noqa: E402

CYCLE_INTERVAL_MINUTES = 20
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 60
DAILY_SUMMARY_HOUR = 21
STALE_RUN_ALERT_MINUTES = 30
MAX_RETRY_COOLDOWN_SECONDS = 300
LOG_FILE = BASE_DIR / "storage" / "logs" / "loop.log"

shutdown_requested = False


def signal_handler(signum, frame):
    """Handle Ctrl+C and SIGTERM gracefully."""
    del signum, frame
    global shutdown_requested
    shutdown_requested = True


def configure_logger() -> logging.Logger:
    """Create the loop logger backed by storage/logs/loop.log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("batcave.run_loop")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("[%(asctime)s UTC] %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    has_loop_file_handler = any(
        isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == str(LOG_FILE)
        for handler in root_logger.handlers
    )
    if not has_loop_file_handler:
        root_logger.addHandler(file_handler)

    return logger


class BatcaveLoop:
    def __init__(
        self,
        interval_seconds: int | None = None,
        max_cycles: int | None = None,
        skip_startup_check: bool = False,
    ):
        self.cycle_count = 0
        self.error_count = 0
        self.start_time = datetime.now(UTC)
        self.last_success: datetime | None = None
        self.last_summary_date = None
        self.interval_seconds = interval_seconds or (CYCLE_INTERVAL_MINUTES * 60)
        self.max_cycles = max_cycles
        self.skip_startup_check = skip_startup_check
        self.logger = configure_logger()

    def _run_startup_checks(self) -> bool:
        """Run startup health checks (audit Section C #8). Return False on any failure."""
        if self.skip_startup_check:
            self._log("⚠️  Startup checks SKIPPED (--skip-startup-check)")
            return True
        self._log("")
        self._log("🔍 Running startup health checks...")
        ok = run_all_checks()
        if not ok:
            self._log("🛑 Startup checks FAILED — refusing to start engine loop.")
        return ok

    def run_forever(self):
        """Main loop with self-healing."""
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self._log("🦇 BATCAVE ENGINE LOOP STARTED")
        self._log(
            f"   Cycle interval: {self.interval_seconds // 60 if self.interval_seconds >= 60 else self.interval_seconds} {'min' if self.interval_seconds >= 60 else 'sec'}"
        )
        self._log(f"   Log file: {LOG_FILE}")
        self._log("   Press Ctrl+C to stop\n")

        if not self._run_startup_checks():
            return

        while not shutdown_requested:
            if self.max_cycles is not None and self.cycle_count >= self.max_cycles:
                self._log(f"Reached max cycles limit ({self.max_cycles}). Stopping.")
                break

            try:
                self._run_cycle()
            except KeyboardInterrupt:
                self._graceful_shutdown()
                break
            except Exception as exc:
                if shutdown_requested:
                    self._graceful_shutdown()
                    break
                should_wait_full_cycle = self._handle_error(exc)
                if shutdown_requested:
                    break
                if should_wait_full_cycle:
                    self._wait_next_cycle()
                continue

            if shutdown_requested:
                break

            self._maybe_run_daily_summary()
            self._wait_next_cycle()

        if shutdown_requested:
            self._graceful_shutdown()

    def _run_cycle(self):
        """Run one engine cycle."""
        self.cycle_count += 1
        now = datetime.now(UTC)
        self._log("")
        self._log("=" * 60)
        self._log(f"🦇 CYCLE #{self.cycle_count} — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self._log("=" * 60)

        result = run_engine()
        if isinstance(result, dict) and result.get("status") == "already_running":
            raise RuntimeError("engine lock already present")

        self.last_success = datetime.now(UTC)
        self.error_count = 0
        self._log(f"✓ Cycle #{self.cycle_count} completed successfully")

    def _handle_error(self, error):
        """Handle engine crash with retry logic."""
        self.error_count += 1
        self._log(f"⚠️  Engine error (attempt {self.error_count}/{MAX_RETRIES}): {type(error).__name__}: {error}")

        if self.error_count >= MAX_RETRIES:
            self._log(
                f"🛑 Max retries reached. Waiting {MAX_RETRY_COOLDOWN_SECONDS // 60} minutes before next cycle window..."
            )
            self._sleep_with_interrupt(MAX_RETRY_COOLDOWN_SECONDS)
            self.error_count = 0
            return True

        self._log(f"🔄 Retrying in {RETRY_WAIT_SECONDS} seconds...")
        self._sleep_with_interrupt(RETRY_WAIT_SECONDS)
        return False

    def _wait_next_cycle(self):
        """Wait until next cycle with countdown and health checks."""
        next_run = datetime.now(UTC) + timedelta(seconds=self.interval_seconds)
        self._log("")
        self._log(f"⏰ Next cycle: {next_run.strftime('%H:%M:%S UTC')}")
        self._log(f"   Cycles run: {self.cycle_count}")
        self._log(f"   Errors in current streak: {self.error_count}")
        if self.last_success:
            uptime = datetime.now(UTC) - self.start_time
            self._log(f"   Uptime: {str(uptime).split('.')[0]}")

        waited = 0
        while waited < self.interval_seconds and not shutdown_requested:
            self._check_engine_health()
            self._maybe_run_daily_summary()
            time.sleep(1)
            waited += 1

    def _check_engine_health(self):
        """Alert if the engine has not completed successfully in 30 minutes."""
        reference = self.last_success or self.start_time
        age = datetime.now(UTC) - reference
        if age >= timedelta(minutes=STALE_RUN_ALERT_MINUTES):
            self._log(
                f"🚨 HEALTH ALERT: engine has not completed a successful run in "
                f"{int(age.total_seconds() // 60)} minutes"
            )

    def _maybe_run_daily_summary(self):
        """Run the daily summary once per UTC day at or after 21:00."""
        now = datetime.now(UTC)
        if now.hour < DAILY_SUMMARY_HOUR:
            return
        if self.last_summary_date == now.date():
            return

        self._log("")
        self._log("📊 Running daily summary...")
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                make_daily_summary()
        except Exception as exc:
            self._log(f"⚠️  Daily summary failed: {type(exc).__name__}: {exc}")
            return

        summary_text = buffer.getvalue().strip()
        if summary_text:
            for line in summary_text.splitlines():
                self._log(f"   {line}")
        self.last_summary_date = now.date()

    def _sleep_with_interrupt(self, seconds: int):
        """Sleep in small increments so Ctrl+C can stop the loop quickly."""
        elapsed = 0
        while elapsed < seconds and not shutdown_requested:
            time.sleep(1)
            elapsed += 1

    def _graceful_shutdown(self):
        """Clean shutdown on Ctrl+C."""
        uptime = datetime.now(UTC) - self.start_time
        self._log("")
        self._log("")
        self._log("🦇 BATCAVE SHUTTING DOWN")
        self._log(f"   Total cycles: {self.cycle_count}")
        self._log(f"   Uptime: {str(uptime).split('.')[0]}")
        self._log("   Goodbye.\n")

    def _log(self, message: str):
        self.logger.info(message)


def run_single_cycle(skip_startup_check: bool = False):
    """Run a single cycle and exit."""
    loop = BatcaveLoop(max_cycles=1, skip_startup_check=skip_startup_check)
    if not loop._run_startup_checks():
        return 1
    try:
        loop._run_cycle()
        loop._maybe_run_daily_summary()
        loop._graceful_shutdown()
        return 0
    except Exception as exc:
        loop._handle_error(exc)
        loop._graceful_shutdown()
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Run Batman Flow Engine in a self-healing loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/run_loop.py
  python tools/run_loop.py --test
  python tools/run_loop.py --max-cycles 2 --interval-seconds 5
        """,
    )
    parser.add_argument("--test", action="store_true", help="Run a single cycle for testing")
    parser.add_argument("--max-cycles", type=int, help="Stop after N successful/attempted cycles")
    parser.add_argument("--interval-seconds", type=int, help="Override cycle interval for local testing")
    parser.add_argument(
        "--skip-startup-check",
        action="store_true",
        help="Skip startup health checks (PG/schema/ALFRED). Use only for offline tests.",
    )
    args = parser.parse_args()

    if args.test:
        raise SystemExit(run_single_cycle(skip_startup_check=args.skip_startup_check))

    loop = BatcaveLoop(
        interval_seconds=args.interval_seconds,
        max_cycles=args.max_cycles,
        skip_startup_check=args.skip_startup_check,
    )
    loop.run_forever()


if __name__ == "__main__":
    main()
