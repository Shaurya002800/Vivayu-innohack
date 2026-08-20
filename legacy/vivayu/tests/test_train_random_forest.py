import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from train_random_forest import FEATURES, prepare_split, train_and_evaluate  # noqa: E402


class RandomForestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv("data/processed/vivayu_readings.csv")

    def test_split_is_time_ordered_and_features_avoid_leakage(self):
        training, testing = prepare_split(self.data)

        self.assertEqual(set(training["experimental_day"]), {1, 2})
        self.assertEqual(set(testing["experimental_day"]), {3})
        self.assertNotIn("timestamp_ms", FEATURES)
        self.assertNotIn("experimental_day", FEATURES)
        self.assertNotIn("infected", FEATURES)

    def test_model_returns_valid_holdout_metrics(self):
        result, bundle, prediction_audit = train_and_evaluate(self.data)

        self.assertEqual(result["training_rows"], 68)
        self.assertEqual(result["test_rows"], 54)
        self.assertEqual(bundle["features"], FEATURES)
        self.assertEqual(len(prediction_audit), 54)
        self.assertEqual(
            sum(result["test_prediction_counts"].values()), result["test_rows"]
        )
        self.assertEqual(result["test_metrics"]["confusion_matrix"]["true_negative"], 0)
        self.assertGreaterEqual(result["test_metrics"]["balanced_accuracy"], 0.0)
        self.assertLessEqual(result["test_metrics"]["balanced_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
