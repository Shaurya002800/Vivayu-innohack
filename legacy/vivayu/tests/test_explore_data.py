import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from explore_data import build_summary, count_by_day_and_condition  # noqa: E402


class ExploreDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv("data/processed/vivayu_readings.csv")

    def test_day_condition_counts_include_missing_controlled_day_five(self):
        counts = count_by_day_and_condition(self.data)
        by_key = {(item["experimental_day"], item["condition"]): item["rows"] for item in counts}

        self.assertEqual(by_key[(5, "controlled")], 0)
        self.assertEqual(by_key[(5, "diseased")], 38)

    def test_summary_has_expected_cleaning_boundary(self):
        summary = build_summary(self.data)

        self.assertEqual(summary["accepted_rows"], 241)
        self.assertEqual(summary["unflagged_rows"], 195)
        self.assertEqual(summary["quality_flags"]["any_flagged_rows"], 46)


if __name__ == "__main__":
    unittest.main()
