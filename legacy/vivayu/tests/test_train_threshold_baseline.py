import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from train_threshold_baseline import find_best_threshold, predict_with_threshold, train_and_evaluate  # noqa: E402


class ThresholdBaselineTests(unittest.TestCase):
    def test_finds_lower_is_diseased_rule(self):
        feature_values = np.array([10.0, 11.0, 1.0, 2.0])
        labels = np.array([0, 0, 1, 1])

        result = find_best_threshold(feature_values, labels)

        self.assertEqual(result["direction"], "lower_is_diseased")
        predictions = predict_with_threshold(feature_values, result["threshold"], result["direction"])
        self.assertTrue(np.array_equal(predictions, labels))

    def test_uses_day_three_as_an_unseen_holdout(self):
        data = pd.read_csv("data/processed/vivayu_readings.csv")

        result = train_and_evaluate(data)

        self.assertEqual(result["training_days"], [1, 2])
        self.assertEqual(result["test_day"], 3)
        self.assertEqual(result["training_rows"], 68)
        self.assertEqual(result["test_rows"], 54)


if __name__ == "__main__":
    unittest.main()
