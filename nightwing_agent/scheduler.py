#!/usr/bin/env python3
"""
Minimal local scheduler for Nightwing laboratory monitoring.

Role:
- Runs the existing Nightwing agent, scanners, and alerts in a repeatable
  local sequence.
- Does not modify trading logic or Batman behavior. It only orchestrates
  existing CLIs and reports their outcomes.

Run:
    python scheduler.py --interval 300 --rows 100 --edge-threshold 0.10 --age-threshold 300
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent


def build_cycle_commands(
    rows: int,
    edge_threshold: float,
    age_threshold: float,
) -> list[tuple[str, list[str]]]:
    """Build the scheduler's fixed command sequence for one monitoring cycle."""
    python = sys.executable
    return [
        ("agent cycle", [python, "agent.py", "--cycles", "1"]),
        (
            "opportunity scanner",
            [python, "scanners/opportunity_scanner.py", "--rows", str(rows), "--edge-threshold", str(edge_threshold)],
        ),
        (
            "system scanner",
            [python, "scanners/system_scanner.py", "--rows", str(rows), "--age-threshold", str(age_threshold)],
        ),
        ("alerts check", [python, "alerts.py", "--rows", str(rows), "--edge-threshold", str(edge_threshold)]),
    ]


def run_command(name: str, command: list[str]) -> dict[str, Any]:
    """Run one CLI command and capture a compact execution result."""
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = time.time() - started
    return {
        "name": name,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_seconds": duration_seconds,
    }


def run_cycle(
    cycle_number: int,
    rows: int,
    edge_threshold: float,
    age_threshold: float,
    runner: Callable[[str, list[str]], dict[str, Any]] = run_command,
) -> list[dict[str, Any]]:
    """Run one full scheduler cycle in the required fixed order."""
    del cycle_number
    results = []
    for name, command in build_cycle_commands(rows, edge_threshold, age_threshold):
        results.append(runner(name, command))
    return results


def render_cycle_summary(cycle_number: int, results: list[dict[str, Any]]) -> str:
    """Render a clear terminal summary for one completed scheduler cycle."""
    lines = [f"Scheduler cycle {cycle_number}"]
    for result in results:
        status = "ok" if result.get("returncode") == 0 else f"failed ({result.get('returncode')})"
        duration_seconds = result.get("duration_seconds", 0.0)
        lines.append(f"- {result.get('name')}: {status} in {duration_seconds:.2f}s")

        stdout = (result.get("stdout") or "").strip().splitlines()
        if stdout:
            lines.append(f"  stdout: {stdout[0]}")

        stderr = (result.get("stderr") or "").strip().splitlines()
        if stderr:
            lines.append(f"  stderr: {stderr[0]}")
    return "\n".join(lines)


def run_scheduler(
    interval: float,
    rows: int,
    edge_threshold: float,
    age_threshold: float,
    runner: Callable[[str, list[str]], dict[str, Any]] = run_command,
    sleeper: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
) -> int:
    """Run scheduler cycles until interrupted or until `max_cycles` is reached."""
    cycle_number = 0
    try:
        while max_cycles is None or cycle_number < max_cycles:
            cycle_number += 1
            results = run_cycle(
                cycle_number,
                rows=rows,
                edge_threshold=edge_threshold,
                age_threshold=age_threshold,
                runner=runner,
            )
            print(render_cycle_summary(cycle_number, results))
            if max_cycles is not None and cycle_number >= max_cycles:
                break
            print(f"\nWaiting {interval:.0f}s before next cycle...\n")
            sleeper(interval)
    except KeyboardInterrupt:
        print("\nScheduler interrupted by user.")
    return cycle_number


def main() -> None:
    """Run the local Nightwing scheduler CLI."""
    parser = argparse.ArgumentParser(description="Minimal local scheduler for Nightwing laboratory")
    parser.add_argument("--interval", type=float, default=300.0, help="Seconds between scheduler cycles")
    parser.add_argument("--rows", type=int, default=100, help="Latest N execution rows for scanners and alerts")
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=0.0,
        help="Threshold used by the opportunity scanner and alerts",
    )
    parser.add_argument(
        "--age-threshold",
        type=float,
        default=300.0,
        help="Threshold used by the system scanner for Batman age",
    )
    args = parser.parse_args()

    completed_cycles = run_scheduler(
        interval=max(0.0, args.interval),
        rows=max(1, args.rows),
        edge_threshold=args.edge_threshold,
        age_threshold=args.age_threshold,
    )
    print(f"\nCompleted {completed_cycles} scheduler cycle(s).")


if __name__ == "__main__":
    main()
