from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from research.feature_analysis import compute_statistics, load_features


def test_load_features_returns_latest_rows(tmp_path: Path):
    path = tmp_path / "features.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"cycle": 1, "timestamp": "2026-03-10T10:00:00+00:00", "spread": 0.10}',
                '{"cycle": 2, "timestamp": "2026-03-10T10:05:00+00:00", "spread": 0.15}',
                '{"cycle": 3, "timestamp": "2026-03-10T10:10:00+00:00", "spread": 0.20}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = load_features(path=path, rows=2)

    assert [record["cycle"] for record in records] == [2, 3]


def test_compute_statistics_summarizes_feature_records():
    records = [
        {
            "cycle": 1,
            "timestamp": "2026-03-10T10:00:00+00:00",
            "spread": 0.10,
            "buy_liquidity": 1000.0,
            "sell_liquidity": 800.0,
            "depth_imbalance": 0.1111,
            "top5_liquidity": 900.0,
            "top10_liquidity": 1800.0,
        },
        {
            "cycle": 2,
            "timestamp": "2026-03-10T10:05:00+00:00",
            "spread": 0.20,
            "buy_liquidity": 1200.0,
            "sell_liquidity": 700.0,
            "depth_imbalance": 0.2632,
            "top5_liquidity": 1000.0,
            "top10_liquidity": 2000.0,
        },
        {
            "cycle": 3,
            "timestamp": "2026-03-10T10:10:00+00:00",
            "spread": None,
            "buy_liquidity": 800.0,
            "sell_liquidity": 900.0,
            "depth_imbalance": None,
            "top5_liquidity": 0.0,
            "top10_liquidity": 0.0,
        },
    ]

    statistics = compute_statistics(records)

    assert statistics["record_count"] == 3
    assert round(statistics["average_spread"], 4) == 0.1500
    assert round(statistics["spread_volatility"], 4) == 0.0500
    assert statistics["average_depth_imbalance"] == 0.18714999999999998
    assert statistics["liquidity_distribution"] == {
        "buy_average": 1000.0,
        "buy_min": 800.0,
        "buy_max": 1200.0,
        "sell_average": 800.0,
        "sell_min": 700.0,
        "sell_max": 900.0,
    }
    assert round(statistics["top5_vs_top10_ratio"], 4) == 0.5000
