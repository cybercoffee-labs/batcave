"""
Feature logging for Nightwing microstructure research.

This module persists the compact market microstructure features computed by
Nightwing into an append-only JSONL dataset. The logger sits after feature
extraction in the research pipeline: upstream code captures a depth snapshot,
`core.microstructure.compute_depth_metrics()` derives normalized metrics from
that snapshot, and `log_features()` writes the resulting values as one record
per cycle for later offline analysis.

Feature records are stored separately from execution logs on purpose. Execution
logs explain what the runtime did, how components interacted, and whether a
cycle succeeded or failed. Feature logs instead preserve the numeric inputs
used for research, model tuning, and retrospective audits. Keeping the two log
streams separate makes the feature dataset easier to query, reduces noise in
audit trails, and avoids coupling research data retention to operational
logging concerns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURES_FILE = BASE_DIR / "storage" / "logs" / "features.jsonl"


def log_features(
    metrics: dict[str, Any],
    cycle_id: int,
    timestamp: str,
    path: Path = FEATURES_FILE,
) -> dict[str, Any]:
    """Append one feature record to the local JSONL research log.

    Parameters:
        metrics: Mapping of computed feature names to scalar values. The logger
            reads the following keys when present: `spread`, `buy_liquidity`,
            `sell_liquidity`, `depth_imbalance`, `top5_liquidity`, and
            `top10_liquidity`. Missing keys are serialized as JSON `null`.
        cycle_id: Integer identifier for the research/execution cycle that
            produced the metrics.
        timestamp: Cycle timestamp as a string, typically an ISO 8601 value.
        path: Destination JSONL file. Parent directories are created on demand.

    Metrics structure:
        `metrics` is expected to be the output of
        `core.microstructure.compute_depth_metrics()`: a flat dictionary whose
        values are numeric scalars or `None`. Additional keys are ignored.

    JSONL output:
        Each call appends exactly one JSON object followed by a newline. The
        persisted record contains these fields only: `cycle`, `timestamp`,
        `spread`, `buy_liquidity`, `sell_liquidity`, `depth_imbalance`,
        `top5_liquidity`, and `top10_liquidity`. Keys are serialized in sorted
        order to keep diffs and audit inspection deterministic.

    Example record:
        {"buy_liquidity": 1700.0, "cycle": 7, "depth_imbalance": 0.1724, "sell_liquidity": 1200.0, "spread": 0.15, "timestamp": "2026-03-10T10:30:00+00:00", "top10_liquidity": 2900.0, "top5_liquidity": 2900.0}
    """
    # Persist a narrow, cycle-scoped feature record for downstream analysis.
    record = {
        "cycle": cycle_id,
        "timestamp": timestamp,
        "spread": metrics.get("spread"),
        "buy_liquidity": metrics.get("buy_liquidity"),
        "sell_liquidity": metrics.get("sell_liquidity"),
        "depth_imbalance": metrics.get("depth_imbalance"),
        "top5_liquidity": metrics.get("top5_liquidity"),
        "top10_liquidity": metrics.get("top10_liquidity"),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")

    return record
