"""Summarize whether the current Vivayu dataset supports deployment-grade ML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


WINDOW_METADATA = {
    "window_id",
    "experimental_day",
    "condition",
    "infected",
    "infection_days",
    "label",
    "readings_in_window",
    "source_row_start",
    "source_row_end",
    "timestamp_start_ms",
    "timestamp_end_ms",
}


def assess_readiness(
    readings: pd.DataFrame, windows: pd.DataFrame, random_forest_summary: dict[str, object]
) -> dict[str, object]:
    """Make the current evidence and its limitations machine-readable."""
    readings = readings.copy()
    readings["quality_flag"] = readings["quality_flag"].fillna("")
    unflagged = readings[readings["quality_flag"] == ""]
    window_features = [column for column in windows.columns if column not in WINDOW_METADATA]
    train_windows = windows[windows["experimental_day"].isin([1, 2])]
    test_windows = windows[windows["experimental_day"] == 3]
    days = sorted(int(day) for day in readings["experimental_day"].unique())

    coverage = []
    missing_controlled_days = []
    for day in days:
        controlled = int(
            ((unflagged["experimental_day"] == day) & (unflagged["condition"] == "controlled")).sum()
        )
        diseased = int(
            ((unflagged["experimental_day"] == day) & (unflagged["condition"] == "diseased")).sum()
        )
        coverage.append({"experimental_day": day, "controlled": controlled, "diseased": diseased})
        if controlled == 0:
            missing_controlled_days.append(day)

    test_metrics = random_forest_summary["test_metrics"]
    reasons = [
        "The saved multifeature Random Forest has poor Day 3 holdout performance.",
        "The dataset has no independent plant, chamber, or experimental-run identifier for external validation.",
        "Window features outnumber available training windows, making a window model prone to memorization.",
    ]
    if missing_controlled_days:
        reasons.append(
            "Controlled readings are missing for experiment day(s): "
            + ", ".join(str(day) for day in missing_controlled_days)
            + "."
        )

    return {
        "status": "research_only_not_deployable",
        "row_level_data": {
            "accepted_readings": int(len(readings)),
            "unflagged_readings": int(len(unflagged)),
            "unflagged_coverage_by_day": coverage,
        },
        "window_level_data": {
            "windows": int(len(windows)),
            "window_features": int(len(window_features)),
            "training_windows_days_1_2": int(len(train_windows)),
            "test_windows_day_3": int(len(test_windows)),
        },
        "random_forest_holdout": {
            "balanced_accuracy": float(test_metrics["balanced_accuracy"]),
            "sensitivity": float(test_metrics["sensitivity"]),
            "specificity": float(test_metrics["specificity"]),
        },
        "reasons": reasons,
        "next_data_needed": [
            "Collect controlled and diseased data for every experiment day under the same sampling protocol.",
            "Record plant_id, chamber_id, sensor_id, experimental_run_id, and an infection ground-truth label.",
            "Use multiple plants per condition and repeat the experiment on separate runs.",
            "Keep sampling rate, sensor warm-up, heater settings, compensation, distance, and airflow consistent.",
        ],
    }


def write_markdown_report(readiness: dict[str, object], output_path: Path) -> None:
    """Write the readiness decision in plain language for the project record."""
    row_data = readiness["row_level_data"]
    window_data = readiness["window_level_data"]
    metrics = readiness["random_forest_holdout"]
    reasons = "\n".join(f"- {reason}" for reason in readiness["reasons"])
    next_data = "\n".join(f"- {item}" for item in readiness["next_data_needed"])
    report = f"""# Vivayu Model Readiness

## Status: research only, not deployable

The current code pipeline works, but the data evidence does not support using a
model as a real crop-disease decision system yet.

## Evidence

- Accepted readings: {row_data['accepted_readings']}
- Unflagged readings: {row_data['unflagged_readings']}
- Five-reading windows: {window_data['windows']}
- Window features: {window_data['window_features']}
- Training windows from Day 1-2: {window_data['training_windows_days_1_2']}
- Day 3 Random Forest balanced accuracy: {metrics['balanced_accuracy']:.1%}
- Day 3 Random Forest sensitivity / specificity: {metrics['sensitivity']:.1%} / {metrics['specificity']:.1%}

## Why deployment is blocked

{reasons}

## Next data collection requirements

{next_data}
"""
    output_path.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readings",
        type=Path,
        default=Path("data/processed/vivayu_readings.csv"),
    )
    parser.add_argument(
        "--windows",
        type=Path,
        default=Path("data/processed/vivayu_windows_5.csv"),
    )
    parser.add_argument(
        "--random-forest-summary",
        type=Path,
        default=Path("reports/random_forest_summary.json"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    readings = pd.read_csv(args.readings)
    windows = pd.read_csv(args.windows)
    random_forest_summary = json.loads(args.random_forest_summary.read_text(encoding="utf-8"))
    readiness = assess_readiness(readings, windows, random_forest_summary)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "model_readiness.json").write_text(
        json.dumps(readiness, indent=2), encoding="utf-8"
    )
    write_markdown_report(readiness, args.report_dir / "model_readiness.md")

    print(json.dumps(readiness, indent=2))
    print(f"\nReport: {args.report_dir / 'model_readiness.md'}")


if __name__ == "__main__":
    main()
