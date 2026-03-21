"""
Command-line system health report for Batcave governance and analytics.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.gordon import get_system_health
from core.harvey import get_scanner_performance


def _print_section(title: str) -> None:
    print(title)
    print("-" * len(title))


def main() -> None:
    """Print a human-readable Batcave health report."""
    health = get_system_health()

    _print_section("BATMAN SYSTEM HEALTH")
    print(f"Timestamp: {health['timestamp']}")
    print(f"Audit log: {health['audit_log_path']}")
    print()

    _print_section("GORDON STATUS")
    print(f"Kill switch active: {health['kill_switch_active']}")
    runtime_guard = health["runtime_guard"]
    print(f"Runtime guard active: {runtime_guard.get('active')}")
    print(f"Runtime guard path: {runtime_guard.get('path')}")
    print(f"Runtime guard pid: {runtime_guard.get('pid')}")
    print(f"Runtime guard status: {runtime_guard.get('status')}")
    print()

    _print_section("HARVEY SUMMARY")
    scanner_stats = get_scanner_performance()
    if not scanner_stats:
        print("No scanner statistics available.")
        return

    for row in scanner_stats:
        print(
            f"{row['scanner_id']}: signals={row['signals']} "
            f"avg_edge={row['avg_edge']} max_edge={row['max_edge']} "
            f"last_seen={row['last_seen']}"
        )


if __name__ == "__main__":
    main()
