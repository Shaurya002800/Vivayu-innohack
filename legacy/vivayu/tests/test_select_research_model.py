import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from select_research_model import ELIGIBLE_DAYS, FEATURES, evaluate_candidates, prepare_data  # noqa: E402


class ResearchModelSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv("data/processed/vivayu_readings.csv")

    def test_selection_uses_only_unflagged_days_with_both_classes(self):
        eligible = prepare_data(self.data)

        self.assertEqual(set(eligible["experimental_day"]), set(ELIGIBLE_DAYS))
        self.assertEqual(len(eligible), 122)
        self.assertNotIn("timestamp_ms", FEATURES)

    def test_selection_returns_a_saved_model_contract(self):
        report, bundle = evaluate_candidates(self.data)

        self.assertEqual(report["selection_status"], "research_candidate_only")
        self.assertEqual(len(report["candidate_summary"]), 5)
        self.assertEqual(bundle["features"], FEATURES)
        self.assertIn(report["selected_candidate"], {row["candidate"] for row in report["candidate_summary"]})


if __name__ == "__main__":
    unittest.main()
