import sys
import tempfile
import unittest
from pathlib import Path

import joblib
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from select_research_model import evaluate_candidates  # noqa: E402
from vivayu_runtime import ReadingValidationError, RollingPredictor, parse_sensor_reading  # noqa: E402


class VivayuRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = pd.read_csv("data/processed/vivayu_readings.csv")
        _, bundle = evaluate_candidates(data)
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.model_path = Path(cls.temp_dir.name) / "candidate.joblib"
        joblib.dump(bundle, cls.model_path)
        cls.readings = data[data["quality_flag"].fillna("") == ""].head(5)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_parses_serial_payload(self):
        reading = parse_sensor_reading("8:28:22.812 -> 1181072,29.87,56.13,97481.00,62070.00,29005")

        self.assertEqual(reading["timestamp_ms"], 1181072)
        self.assertEqual(reading["sraw"], 29005)

    def test_rejects_incomplete_payload(self):
        with self.assertRaises(ReadingValidationError):
            parse_sensor_reading("1,2,3")

    def test_returns_research_result_after_five_readings(self):
        predictor = RollingPredictor(self.model_path)
        for _, row in self.readings.iterrows():
            result = predictor.add_reading(
                {
                    "timestamp_ms": row["timestamp_ms"],
                    "temperature_c": row["temperature_c"],
                    "humidity_pct": row["humidity_pct"],
                    "pressure_pa": row["pressure_pa"],
                    "gas_resistance_ohm": row["gas_resistance_ohm"],
                    "sraw": row["sraw"],
                }
            )

        self.assertEqual(result["status"], "research_monitoring_only")
        self.assertIn(result["risk_level"], {"low", "watch", "elevated", "high"})
        self.assertIn(result["pattern"], {"baseline_like_pattern", "elevated_voc_pattern"})
