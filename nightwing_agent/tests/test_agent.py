import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import agent
from core.feature_logger import log_features as write_feature_record


def test_run_cycle_logs_features_when_batman_has_pricing_data(monkeypatch, tmp_path: Path):
    features_path = tmp_path / "features.jsonl"

    monkeypatch.setattr(
        agent,
        "fetch_prices",
        lambda mode: {"mode": mode, "prices": {"BTCUSDT": 68000.0, "ETHUSDT": 3200.0}},
    )
    monkeypatch.setattr(agent, "check_jurisdiction", lambda fiat, amount: {"approved": True, "warnings": []})
    monkeypatch.setattr(
        agent,
        "fetch_from_batman",
        lambda fiat: {
            "status": "ok",
            "edge_net": 0.12,
            "viable": True,
            "p2p_premium": 0.001,
            "p2p_buy_price": 17.20,
            "p2p_sell_price": 17.35,
            "total_friction_pct": 0.4,
            "age_seconds": 30.0,
            "spot_price": 17.10,
        },
    )
    monkeypatch.setattr(
        agent, "gordon_check", lambda **kwargs: {"approved": True, "blocked_by": None, "checks": [], "warnings": []}
    )
    monkeypatch.setattr(agent, "log_execution", lambda execution: None)
    monkeypatch.setattr(agent, "record_trade", lambda result: None)
    monkeypatch.setattr(
        agent,
        "log_features",
        lambda metrics, cycle_id, timestamp: write_feature_record(
            metrics,
            cycle_id=cycle_id,
            timestamp=timestamp,
            path=features_path,
        ),
    )

    result = agent.run_cycle("SIMULATED", 7)

    assert result["decision"] == "OPPORTUNITY"
    assert "feature_record" in result

    written = [json.loads(line) for line in features_path.read_text(encoding="utf-8").splitlines()]
    assert written == [
        {
            "cycle": 7,
            "timestamp": result["ts"],
            "spread": 0.15000000000000213,
            "buy_liquidity": 0.0,
            "sell_liquidity": 0.0,
            "depth_imbalance": None,
            "top5_liquidity": 0.0,
            "top10_liquidity": 0.0,
        }
    ]


def test_run_cycle_logs_features_from_batman_depth_summary(monkeypatch, tmp_path: Path):
    features_path = tmp_path / "features.jsonl"

    monkeypatch.setattr(
        agent,
        "fetch_prices",
        lambda mode: {"mode": mode, "prices": {"BTCUSDT": 68000.0, "ETHUSDT": 3200.0}},
    )
    monkeypatch.setattr(agent, "check_jurisdiction", lambda fiat, amount: {"approved": True, "warnings": []})
    monkeypatch.setattr(
        agent,
        "fetch_from_batman",
        lambda fiat: {
            "status": "ok",
            "edge_net": 0.12,
            "viable": True,
            "p2p_premium": 0.001,
            "p2p_buy_price": 17.20,
            "p2p_sell_price": 17.35,
            "total_friction_pct": 0.4,
            "depth_estimate": 2500.0,
            "merchant_count": 10,
            "age_seconds": 30.0,
            "spot_price": 17.10,
        },
    )
    monkeypatch.setattr(
        agent, "gordon_check", lambda **kwargs: {"approved": True, "blocked_by": None, "checks": [], "warnings": []}
    )
    monkeypatch.setattr(agent, "log_execution", lambda execution: None)
    monkeypatch.setattr(agent, "record_trade", lambda result: None)
    monkeypatch.setattr(
        agent,
        "log_features",
        lambda metrics, cycle_id, timestamp: write_feature_record(
            metrics,
            cycle_id=cycle_id,
            timestamp=timestamp,
            path=features_path,
        ),
    )

    result = agent.run_cycle("SIMULATED", 9)

    assert result["decision"] == "OPPORTUNITY"
    assert "feature_record" in result

    written = [json.loads(line) for line in features_path.read_text(encoding="utf-8").splitlines()]
    assert written == [
        {
            "cycle": 9,
            "timestamp": result["ts"],
            "spread": 0.15000000000000213,
            "buy_liquidity": 2500.0,
            "sell_liquidity": 2500.0,
            "depth_imbalance": 0.0,
            "top5_liquidity": 5000.0,
            "top10_liquidity": 5000.0,
        }
    ]


def test_run_cycle_skips_feature_logging_without_batman_depth_inputs(monkeypatch, tmp_path: Path):
    features_path = tmp_path / "features.jsonl"
    log_calls: list[tuple[dict, int, str]] = []

    monkeypatch.setattr(
        agent,
        "fetch_prices",
        lambda mode: {"mode": mode, "prices": {"BTCUSDT": 68000.0, "ETHUSDT": 3200.0}},
    )
    monkeypatch.setattr(agent, "check_jurisdiction", lambda fiat, amount: {"approved": True, "warnings": []})
    monkeypatch.setattr(agent, "fetch_from_batman", lambda fiat: {"status": "error", "error": "missing_batman"})
    monkeypatch.setattr(
        agent, "gordon_check", lambda **kwargs: {"approved": True, "blocked_by": None, "checks": [], "warnings": []}
    )
    monkeypatch.setattr(agent, "log_execution", lambda execution: None)
    monkeypatch.setattr(agent, "record_trade", lambda result: None)

    def capture_log_features(metrics, cycle_id, timestamp):
        log_calls.append((metrics, cycle_id, timestamp))
        return write_feature_record(metrics, cycle_id=cycle_id, timestamp=timestamp, path=features_path)

    monkeypatch.setattr(agent, "log_features", capture_log_features)

    result = agent.run_cycle("SIMULATED", 8)

    assert result["decision"] == "PASS"
    assert "feature_record" not in result
    assert log_calls == []
    assert not features_path.exists()
