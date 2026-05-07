"""Prediction helpers for ZATANNA."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from zatanna.feature_engineer import FeatureEngineer

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "storage" / "models" / "zatanna_v1.pkl"


class ZatannaPredictor:
    def __init__(self, model_path: str = "storage/models/zatanna_v1.pkl"):
        """Load saved model."""
        path = Path(model_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        self.model_path = path
        payload = joblib.load(path)
        self.model = payload["model"]
        self.feature_columns = payload.get("feature_columns", [])
        self.model_name = payload.get("model_name", "unknown")
        self.evaluation = payload.get("evaluation", {})
        self.feature_engineer = FeatureEngineer()

    def predict(self, opportunity: dict) -> dict:
        """
        Returns:
        - probability: 0.0 to 1.0
        - recommendation: 'strong_buy' | 'buy' | 'hold' | 'skip'
        - confidence: 'high' | 'medium' | 'low'
        """
        features = self.feature_engineer.extract_features(opportunity)
        row = {column: features.get(column) for column in self.feature_columns}
        frame = pd.DataFrame([row], columns=self.feature_columns)
        probabilities = self.model.predict_proba(frame)[0]
        classes = list(self.model.classes_)
        true_index = classes.index(True) if True in classes else len(classes) - 1
        probability = float(probabilities[true_index])
        recommendation = self._recommendation(probability)
        confidence = self._confidence(probability)
        return {
            "probability": round(probability, 4),
            "recommendation": recommendation,
            "confidence": confidence,
            "model_name": self.model_name,
        }

    def _recommendation(self, probability: float) -> str:
        if probability >= 0.8:
            return "strong_buy"
        if probability >= 0.6:
            return "buy"
        if probability >= 0.4:
            return "hold"
        return "skip"

    def _confidence(self, probability: float) -> str:
        distance = abs(probability - 0.5)
        if distance >= 0.3:
            return "high"
        if distance >= 0.15:
            return "medium"
        return "low"
