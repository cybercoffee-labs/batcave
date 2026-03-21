from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.microstructure import compute_depth_metrics


def test_compute_depth_metrics_returns_expected_values():
    depth_payload = {
        "best_buy": 17.20,
        "best_sell": 17.35,
        "buy_offers": [
            {"max_single_trans_amount_value": 1000.0},
            {"max_single_trans_amount_value": 500.0},
            {"max_single_trans_amount_value": 200.0},
        ],
        "sell_offers": [
            {"max_single_trans_amount_value": 800.0},
            {"max_single_trans_amount_value": 300.0},
            {"max_single_trans_amount_value": 100.0},
        ],
    }

    metrics = compute_depth_metrics(depth_payload)

    assert round(metrics["spread"], 4) == 0.15
    assert metrics["buy_liquidity"] == 1700.0
    assert metrics["sell_liquidity"] == 1200.0
    assert round(metrics["depth_imbalance"], 4) == 0.1724
    assert metrics["top5_liquidity"] == 2900.0
    assert metrics["top10_liquidity"] == 2900.0


def test_compute_depth_metrics_handles_missing_or_zero_liquidity():
    depth_payload = {
        "best_buy": None,
        "best_sell": 17.35,
        "buy_offers": [{"max_single_trans_amount_value": None}],
        "sell_offers": [],
    }

    metrics = compute_depth_metrics(depth_payload)

    assert metrics["spread"] is None
    assert metrics["buy_liquidity"] == 0.0
    assert metrics["sell_liquidity"] == 0.0
    assert metrics["depth_imbalance"] is None
    assert metrics["top5_liquidity"] == 0.0
    assert metrics["top10_liquidity"] == 0.0


def test_compute_depth_metrics_limits_top5_and_top10_independently():
    buy_offers = [{"max_single_trans_amount_value": 100.0} for _ in range(7)]
    sell_offers = [{"max_single_trans_amount_value": 50.0} for _ in range(12)]

    metrics = compute_depth_metrics(
        {
            "best_buy": 17.10,
            "best_sell": 17.20,
            "buy_offers": buy_offers,
            "sell_offers": sell_offers,
        }
    )

    assert metrics["top5_liquidity"] == 750.0
    assert metrics["top10_liquidity"] == 1200.0
