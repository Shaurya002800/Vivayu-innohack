import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_windows import build_windows, slope  # noqa: E402


class WindowBuildingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv("data/processed/vivayu_readings.csv")

    def test_slope_is_positive_for_increasing_values(self):
        self.assertAlmostEqual(slope(pd.Series([1, 2, 3, 4, 5])), 1.0)

    def test_nonoverlapping_five_reading_windows_have_expected_counts(self):
        windows, summary = build_windows(self.data, window_size=5)

        self.assertEqual(len(windows), 37)
        self.assertEqual(summary["readings_used_in_windows"], 185)
        self.assertEqual(summary["unused_remainder_readings"], 10)
        self.assertTrue((windows["readings_in_window"] == 5).all())
        self.assertTrue(windows["window_id"].is_unique)
        self.assertFalse(windows.filter(like="_mean").isna().any().any())


if __name__ == "__main__":
    unittest.main()
