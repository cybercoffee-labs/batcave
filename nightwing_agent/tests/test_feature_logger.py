import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.feature_logger import log_features


def test_log_features_writes_expected_fields(tmp_path: Path):
    path = tmp_path / "features.jsonl"
    metrics = {
        "spread": 0.15,
        "buy_liquidity": 1700.0,
        "sell_liquidity": 1200.0,
        "depth_imbalance": 0.1724,
        "top5_liquidity": 2900.0,
        "top10_liquidity": 2900.0,
    }

    record = log_features(metrics, cycle_id=7, timestamp="2026-03-10T10:30:00+00:00", path=path)

    assert record == {
        "cycle": 7,
        "timestamp": "2026-03-10T10:30:00+00:00",
        "spread": 0.15,
        "buy_liquidity": 1700.0,
        "sell_liquidity": 1200.0,
        "depth_imbalance": 0.1724,
        "top5_liquidity": 2900.0,
        "top10_liquidity": 2900.0,
    }
    written = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(written) == 1
    assert json.loads(written[0]) == record


def test_log_features_appends_and_defaults_missing_metrics_to_none(tmp_path: Path):
    path = tmp_path / "features.jsonl"

    log_features({"spread": 0.10}, cycle_id=1, timestamp="2026-03-10T10:00:00+00:00", path=path)
    log_features({}, cycle_id=2, timestamp="2026-03-10T10:05:00+00:00", path=path)

    written = [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]

    assert [record["cycle"] for record in written] == [1, 2]
    assert written[1] == {
        "cycle": 2,
        "timestamp": "2026-03-10T10:05:00+00:00",
        "spread": None,
        "buy_liquidity": None,
        "sell_liquidity": None,
        "depth_imbalance": None,
        "top5_liquidity": None,
        "top10_liquidity": None,
    }
