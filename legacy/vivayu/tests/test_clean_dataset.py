import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from clean_dataset import clean_workbook, extract_payload  # noqa: E402


class ExtractPayloadTests(unittest.TestCase):
    def test_plain_six_value_payload(self):
        values, error = extract_payload("6472,31.68,51.16,97481.00,6180.00,25315")

        self.assertIsNone(error)
        self.assertEqual(values, [6472.0, 31.68, 51.16, 97481.0, 6180.0, 25315.0])

    def test_serial_monitor_prefix_is_removed(self):
        values, error = extract_payload(
            "8:28:22.812 -> 1181072,29.87,56.13,97481.00,62070.00,29005"
        )

        self.assertIsNone(error)
        self.assertEqual(values[0], 1181072.0)
        self.assertEqual(values[-1], 29005.0)

    def test_dash_is_rejected_as_missing_payload(self):
        values, error = extract_payload(":25.224 -> -")

        self.assertIsNone(values)
        self.assertEqual(error, "missing_sensor_payload")

    def test_wrong_number_of_values_is_rejected(self):
        values, error = extract_payload("1,2,3")

        self.assertIsNone(values)
        self.assertEqual(error, "expected_six_comma_separated_numbers")


class CleanWorkbookTests(unittest.TestCase):
    def test_whitespace_only_cells_are_not_rejected(self):
        workbook = Path("data/raw/Vivayu dataset tomato.xlsx")
        clean, rejects = clean_workbook(workbook)

        self.assertEqual(len(clean), 241)
        self.assertEqual(len(rejects), 117)
        self.assertEqual(set(rejects["rejection_reason"]), {"missing_sensor_payload"})


if __name__ == "__main__":
    unittest.main()
