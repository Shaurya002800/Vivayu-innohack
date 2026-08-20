"""Reusable model components that must remain importable after joblib loading."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score


class GasThresholdClassifier:
    """Transparent one-feature classifier using gas resistance."""

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "GasThresholdClassifier":
        values = x["gas_resistance_ohm"].to_numpy(dtype=float)
        labels = np.asarray(y, dtype=int)
        unique_values = np.unique(values)
        if len(unique_values) < 2:
            raise ValueError("Gas threshold needs at least two distinct values.")

        self.threshold_ = float(unique_values[0])
        self.direction_ = "lower_is_diseased"
        best_score = -1.0
        for threshold in (unique_values[:-1] + unique_values[1:]) / 2:
            for direction in ("lower_is_diseased", "higher_is_diseased"):
                predictions = self._predict_values(values, float(threshold), direction)
                score = balanced_accuracy_score(labels, predictions)
                if score > best_score:
                    self.threshold_ = float(threshold)
                    self.direction_ = direction
                    best_score = float(score)
        return self

    @staticmethod
    def _predict_values(values: np.ndarray, threshold: float, direction: str) -> np.ndarray:
        if direction == "lower_is_diseased":
            return (values < threshold).astype(int)
        return (values > threshold).astype(int)

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return self._predict_values(
            x["gas_resistance_ohm"].to_numpy(dtype=float), self.threshold_, self.direction_
        )

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        """Return a soft score based on distance from the learned threshold."""
        values = x["gas_resistance_ohm"].to_numpy(dtype=float)
        scale = max(abs(self.threshold_) * 0.10, 1.0)
        signed_distance = (self.threshold_ - values) / scale
        if self.direction_ == "higher_is_diseased":
            signed_distance = -signed_distance
        disease_probability = 1 / (1 + np.exp(-signed_distance))
        return np.column_stack((1 - disease_probability, disease_probability))
