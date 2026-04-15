"""Tests for ZATANNA."""

from __future__ import annotations

import json


def test_feature_engineer_extracts_expected_fields():
    from zatanna.feature_engineer import FeatureEngineer

    fe = FeatureEngineer()
    features = fe.extract_features(
        {
            "ts": "2026-04-15T16:09:55",
            "type": "C",
            "edge_net": 6.42,
            "spread": 0.5,
            "market": "ARS",
            "merchant_count": 5,
            "depth_estimate": 1000,
            "venue": "binance_p2p",
        }
    )

    assert len(features) == 10
    assert features["hour"] == 16
    assert features["market"] == "ARS"
    assert features["exchange"] == "binance_p2p"


def test_trainer_train_save_and_predict(tmp_path):
    from zatanna.predictor import ZatannaPredictor
    from zatanna.trainer import ZatannaTrainer

    data_path = tmp_path / "opportunities.jsonl"
    model_path = tmp_path / "zatanna.pkl"

    rows = [
        {"ts": "2026-04-14T10:00:00+00:00", "type": "C", "edge_net": 5.0, "spread_pct": 0.8, "market": "ARS", "venue": "binance", "merchant_count": 8, "depth_estimate": 5000, "viable": True},
        {"ts": "2026-04-14T11:00:00+00:00", "type": "D", "edge_net": 0.2, "spread_pct": 0.1, "market": "DOT", "buy_exchange": "okx", "merchant_count": 0, "depth_estimate": 0, "viable": False},
        {"ts": "2026-04-14T12:00:00+00:00", "type": "C", "edge_net": 4.0, "spread_pct": 0.5, "market": "MXN", "venue": "binance", "merchant_count": 10, "depth_estimate": 4000, "viable": True},
        {"ts": "2026-04-14T13:00:00+00:00", "type": "F", "edge_net": 1.5, "cross_premium_spread": 1.0, "market": "USDT", "exchange": "route", "merchant_count": 1, "depth_estimate": 1200, "viable": True},
        {"ts": "2026-04-14T14:00:00+00:00", "type": "E", "edge_net": -0.2, "market": "SOL", "exchange": "binance", "merchant_count": 0, "depth_estimate": 0, "viable": False},
        {"ts": "2026-04-15T10:00:00+00:00", "type": "C", "edge_net": 6.0, "spread_pct": 0.9, "market": "ARS", "venue": "binance", "merchant_count": 9, "depth_estimate": 7000, "viable": True},
        {"ts": "2026-04-15T11:00:00+00:00", "type": "D", "edge_net": 0.1, "spread_pct": 0.05, "market": "LINK", "sell_exchange": "mexc", "merchant_count": 0, "depth_estimate": 0, "viable": False},
        {"ts": "2026-04-15T12:00:00+00:00", "type": "F", "edge_net": 2.0, "cross_premium_spread": 1.2, "market": "USDT", "exchange": "route", "merchant_count": 2, "depth_estimate": 2000, "viable": True},
        {"ts": "2026-04-15T13:00:00+00:00", "type": "E", "edge_net": 0.0, "market": "BTC", "exchange": "okx", "merchant_count": 0, "depth_estimate": 0, "viable": False},
        {"ts": "2026-04-15T14:00:00+00:00", "type": "C", "edge_net": 3.2, "merchant_spread": 0.3, "market": "COP", "venue": "binance", "merchant_count": 6, "depth_estimate": 2500, "viable": True},
    ]
    data_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    trainer = ZatannaTrainer().train(data_path=str(data_path))
    metrics = trainer.evaluate()
    saved = trainer.save_model(str(model_path))

    assert trainer.model is not None
    assert trainer.best_model_name in {"logistic_regression", "random_forest"}
    assert set(metrics) == {"accuracy", "precision", "recall", "f1"}
    assert saved == str(model_path)

    predictor = ZatannaPredictor(model_path=str(model_path))
    prediction = predictor.predict(
        {
            "ts": "2026-04-15T16:09:55",
            "type": "C",
            "edge_net": 6.42,
            "spread": 0.5,
            "market": "ARS",
            "merchant_count": 5,
            "depth_estimate": 1000,
            "venue": "binance",
        }
    )

    assert 0.0 <= prediction["probability"] <= 1.0
    assert prediction["recommendation"] in {"strong_buy", "buy", "hold", "skip"}
    assert prediction["confidence"] in {"high", "medium", "low"}
