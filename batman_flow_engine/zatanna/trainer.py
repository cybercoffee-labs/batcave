"""Training utilities for ZATANNA."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from zatanna.feature_engineer import FeatureEngineer

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "storage" / "logs" / "opportunities.jsonl"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "storage" / "models" / "zatanna_v1.pkl"


class ZatannaTrainer:
    def __init__(self) -> None:
        self.feature_engineer = FeatureEngineer()
        self.model: Pipeline | None = None
        self.best_model_name: str | None = None
        self.feature_columns = [
            "hour",
            "day_of_week",
            "scanner_type",
            "edge_net",
            "spread",
            "volume",
            "market",
            "exchange",
            "merchant_count",
            "depth_estimate",
        ]
        self._evaluation: dict[str, float] | None = None

    def train(self, data_path: str = "storage/logs/opportunities.jsonl"):
        """Train model on historical data."""
        dataset = self._load_dataset(Path(data_path))
        if dataset.empty:
            raise ValueError("No labeled opportunities found for training.")

        X = dataset[self.feature_columns]
        y = dataset["target"]

        models = {
            "logistic_regression": self._build_pipeline(LogisticRegression(max_iter=1000, random_state=42)),
            "random_forest": self._build_pipeline(RandomForestClassifier(n_estimators=200, random_state=42)),
        }

        if len(dataset) >= 10 and y.nunique() > 1 and y.value_counts().min() >= 2:
            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=0.3,
                random_state=42,
                stratify=y,
            )
        else:
            X_train, X_test, y_train, y_test = X, X, y, y

        best_score = -1.0
        best_metrics: dict[str, float] | None = None
        best_model: Pipeline | None = None
        best_model_name: str | None = None

        for model_name, pipeline in models.items():
            pipeline.fit(X_train, y_train)
            predictions = pipeline.predict(X_test)
            metrics = {
                "accuracy": float(accuracy_score(y_test, predictions)),
                "precision": float(precision_score(y_test, predictions, zero_division=0)),
                "recall": float(recall_score(y_test, predictions, zero_division=0)),
                "f1": float(f1_score(y_test, predictions, zero_division=0)),
            }
            if metrics["f1"] > best_score:
                best_score = metrics["f1"]
                best_metrics = metrics
                best_model = pipeline
                best_model_name = model_name

        if best_model is None or best_metrics is None or best_model_name is None:
            raise ValueError("Model training failed.")

        self.model = best_model
        self.best_model_name = best_model_name
        self._evaluation = best_metrics
        return self

    def evaluate(self) -> dict:
        """Return accuracy, precision, recall, f1."""
        if self._evaluation is None:
            return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
        return {key: round(value, 4) for key, value in self._evaluation.items()}

    def save_model(self, path: str = "storage/models/zatanna_v1.pkl"):
        """Save trained model."""
        if self.model is None:
            raise ValueError("No trained model available. Run train() first.")

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "model_name": self.best_model_name,
            "evaluation": self.evaluate(),
            "feature_columns": self.feature_columns,
        }
        joblib.dump(payload, output_path)
        return str(output_path)

    def _load_dataset(self, path: Path) -> pd.DataFrame:
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        if not path.exists():
            return pd.DataFrame()

        feature_rows: list[dict[str, Any]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                opportunity = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "viable" not in opportunity:
                continue
            features = self.feature_engineer.extract_features(opportunity)
            features["target"] = bool(opportunity.get("viable"))
            feature_rows.append(features)

        return pd.DataFrame(feature_rows)

    def _build_pipeline(self, estimator) -> Pipeline:
        numeric_features = ["hour", "day_of_week", "edge_net", "spread", "volume", "merchant_count", "depth_estimate"]
        categorical_features = ["scanner_type", "market", "exchange"]

        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "num",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
                            ("scaler", StandardScaler()),
                        ]
                    ),
                    numeric_features,
                ),
                (
                    "cat",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    categorical_features,
                ),
            ]
        )

        return Pipeline(steps=[("preprocessor", preprocessor), ("classifier", estimator)])


if __name__ == "__main__":
    trainer = ZatannaTrainer().train()
    output = trainer.save_model()
    print(json.dumps({"model": trainer.best_model_name, "metrics": trainer.evaluate(), "path": output}, indent=2))
