import json
import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from assess_model_readiness import assess_readiness  # noqa: E402


class ModelReadinessTests(unittest.TestCase):
    def test_current_dataset_is_marked_research_only(self):
        readings = pd.read_csv("data/processed/vivayu_readings.csv")
        windows = pd.read_csv("data/processed/vivayu_windows_5.csv")
        summary = json.loads(Path("reports/random_forest_summary.json").read_text())

        readiness = assess_readiness(readings, windows, summary)

        self.assertEqual(readiness["status"], "research_only_not_deployable")
        self.assertEqual(readiness["window_level_data"]["windows"], 37)
        self.assertEqual(readiness["window_level_data"]["window_features"], 33)
        self.assertEqual(readiness["window_level_data"]["training_windows_days_1_2"], 13)


if __name__ == "__main__":
    unittest.main()
