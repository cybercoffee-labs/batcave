"""
Research analysis utilities for stored microstructure features.

This module reads the append-only feature dataset produced by
`core.feature_logger` and computes lightweight aggregate metrics for terminal
inspection. It is intended for quick research passes over recent cycles rather
than full offline analytics pipelines.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from statistics import mean, pstdev
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.feature_logger import FEATURES_FILE


def load_features(path: Path = FEATURES_FILE, rows: int | None = None) -> list[dict[str, Any]]:
    """Load feature records from JSONL, optionally limited to the latest rows."""
    if not path.exists():
        return []

    if rows is not None and rows <= 0:
        return []

    if rows is None:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    recent_records: deque[dict[str, Any]] = deque(maxlen=rows)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                recent_records.append(json.loads(line))
    return list(recent_records)


def compute_statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate research statistics from feature records."""
    spreads = [float(value) for value in _field_values(records, "spread")]
    imbalances = [float(value) for value in _field_values(records, "depth_imbalance")]
    buy_liquidity = [float(value) for value in _field_values(records, "buy_liquidity")]
    sell_liquidity = [float(value) for value in _field_values(records, "sell_liquidity")]
    top_ratios = [
        float(top5) / float(top10)
        for record in records
        if (top5 := record.get("top5_liquidity")) is not None
        and (top10 := record.get("top10_liquidity")) not in (None, 0)
    ]

    return {
        "record_count": len(records),
        "average_spread": _average(spreads),
        "spread_volatility": _volatility(spreads),
        "average_depth_imbalance": _average(imbalances),
        "liquidity_distribution": {
            "buy_average": _average(buy_liquidity),
            "buy_min": min(buy_liquidity) if buy_liquidity else None,
            "buy_max": max(buy_liquidity) if buy_liquidity else None,
            "sell_average": _average(sell_liquidity),
            "sell_min": min(sell_liquidity) if sell_liquidity else None,
            "sell_max": max(sell_liquidity) if sell_liquidity else None,
        },
        "top5_vs_top10_ratio": _average(top_ratios),
    }


def _field_values(records: list[dict[str, Any]], field: str) -> list[Any]:
    """Collect non-null values for one field from feature records."""
    return [record[field] for record in records if record.get(field) is not None]


def _average(values: list[float]) -> float | None:
    """Return the arithmetic mean or None when no values exist."""
    return mean(values) if values else None


def _volatility(values: list[float]) -> float | None:
    """Return population standard deviation or None when no values exist."""
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return pstdev(values)


def _format_number(value: float | None) -> str:
    """Render numeric summary values for a compact terminal table."""
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _render_summary_table(statistics: dict[str, Any]) -> str:
    """Build a plain-text summary table for terminal output."""
    liquidity = statistics["liquidity_distribution"]
    rows = [
        ("records", str(statistics["record_count"])),
        ("average spread", _format_number(statistics["average_spread"])),
        ("spread volatility", _format_number(statistics["spread_volatility"])),
        ("average depth imbalance", _format_number(statistics["average_depth_imbalance"])),
        (
            "buy liquidity avg/min/max",
            f"{_format_number(liquidity['buy_average'])} / "
            f"{_format_number(liquidity['buy_min'])} / "
            f"{_format_number(liquidity['buy_max'])}",
        ),
        (
            "sell liquidity avg/min/max",
            f"{_format_number(liquidity['sell_average'])} / "
            f"{_format_number(liquidity['sell_min'])} / "
            f"{_format_number(liquidity['sell_max'])}",
        ),
        ("top5 vs top10 ratio", _format_number(statistics["top5_vs_top10_ratio"])),
    ]

    metric_width = max(len("metric"), *(len(metric) for metric, _ in rows))
    value_width = max(len("value"), *(len(value) for _, value in rows))
    border = f"+-{'-' * metric_width}-+-{'-' * value_width}-+"
    lines = [
        border,
        f"| {'metric'.ljust(metric_width)} | {'value'.ljust(value_width)} |",
        border,
    ]
    for metric, value in rows:
        lines.append(f"| {metric.ljust(metric_width)} | {value.ljust(value_width)} |")
    lines.append(border)
    return "\n".join(lines)


def main() -> int:
    """Run the feature analysis CLI."""
    parser = argparse.ArgumentParser(description="Analyze stored microstructure feature logs.")
    parser.add_argument("--rows", type=int, default=500, help="Number of most recent rows to analyze.")
    parser.add_argument("--path", type=Path, default=FEATURES_FILE, help="Path to the feature JSONL log.")
    args = parser.parse_args()

    records = load_features(path=args.path, rows=args.rows)
    statistics = compute_statistics(records)
    print(_render_summary_table(statistics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
