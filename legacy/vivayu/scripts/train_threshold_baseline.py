"""Train a transparent gas-resistance threshold baseline for Vivayu."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


FEATURE = "gas_resistance_ohm"


def confusion_counts(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, int]:
    """Return binary confusion-matrix counts where 1 means diseased."""
    return {
        "true_negative": int(np.sum((y_true == 0) & (y_pred == 0))),
        "false_positive": int(np.sum((y_true == 0) & (y_pred == 1))),
        "false_negative": int(np.sum((y_true == 1) & (y_pred == 0))),
        "true_positive": int(np.sum((y_true == 1) & (y_pred == 1))),
    }


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int]:
    """Calculate accuracy plus class-balanced metrics from predictions."""
    counts = confusion_counts(y_true, y_pred)
    sensitivity = counts["true_positive"] / (counts["true_positive"] + counts["false_negative"])
    specificity = counts["true_negative"] / (counts["true_negative"] + counts["false_positive"])
    precision_denominator = counts["true_positive"] + counts["false_positive"]
    precision = counts["true_positive"] / precision_denominator if precision_denominator else 0.0

    return {
        **counts,
        "accuracy": (counts["true_positive"] + counts["true_negative"]) / len(y_true),
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "precision": precision,
    }


def predict_with_threshold(values: np.ndarray, threshold: float, direction: str) -> np.ndarray:
    """Classify a row as diseased (1) using an explicitly stated rule."""
    if direction == "lower_is_diseased":
        return (values < threshold).astype(int)
    if direction == "higher_is_diseased":
        return (values > threshold).astype(int)
    raise ValueError(f"Unknown direction: {direction}")


def find_best_threshold(feature_values: np.ndarray, y_train: np.ndarray) -> dict[str, float | str]:
    """Fit one threshold using training data only.

    Every candidate is a midpoint between two observed feature values. We choose
    the candidate with the highest balanced accuracy because it gives equal
    importance to controlled and diseased samples even when class counts differ.
    """
    unique_values = np.unique(feature_values)
    if len(unique_values) < 2:
        raise ValueError("A threshold baseline needs at least two distinct feature values.")

    candidates = (unique_values[:-1] + unique_values[1:]) / 2
    best: dict[str, float | str] | None = None
    for threshold in candidates:
        for direction in ("lower_is_diseased", "higher_is_diseased"):
            predicted = predict_with_threshold(feature_values, float(threshold), direction)
            score = metrics(y_train, predicted)
            candidate = {
                "threshold": float(threshold),
                "direction": direction,
                "training_balanced_accuracy": float(score["balanced_accuracy"]),
            }
            if best is None or candidate["training_balanced_accuracy"] > best["training_balanced_accuracy"]:
                best = candidate

    if best is None:
        raise RuntimeError("No threshold candidates were evaluated.")
    return best


def train_and_evaluate(data: pd.DataFrame) -> dict[str, object]:
    """Train on Day 1-2, then evaluate once on the unseen Day 3 records."""
    data = data.copy()
    data["quality_flag"] = data["quality_flag"].fillna("")
    unflagged = data[data["quality_flag"] == ""].copy()
    training = unflagged[unflagged["experimental_day"].isin([1, 2])].copy()
    testing = unflagged[unflagged["experimental_day"] == 3].copy()

    for name, frame in (("training", training), ("testing", testing)):
        if set(frame["infected"]) != {0, 1}:
            raise ValueError(f"{name.title()} data must contain both controlled and diseased rows.")

    model = find_best_threshold(
        training[FEATURE].to_numpy(dtype=float), training["infected"].to_numpy(dtype=int)
    )
    test_predictions = predict_with_threshold(
        testing[FEATURE].to_numpy(dtype=float),
        float(model["threshold"]),
        str(model["direction"]),
    )
    test_metrics = metrics(testing["infected"].to_numpy(dtype=int), test_predictions)

    return {
        "model_type": "single_feature_threshold_baseline",
        "feature": FEATURE,
        "training_days": [1, 2],
        "test_day": 3,
        "training_rows": int(len(training)),
        "test_rows": int(len(testing)),
        "training_class_counts": {
            "controlled": int((training["infected"] == 0).sum()),
            "diseased": int((training["infected"] == 1).sum()),
        },
        "test_class_counts": {
            "controlled": int((testing["infected"] == 0).sum()),
            "diseased": int((testing["infected"] == 1).sum()),
        },
        "threshold": model,
        "test_metrics": test_metrics,
        "interpretation_boundary": (
            "This is a within-experiment, time-ordered baseline. It is not external validation "
            "because the dataset has no independent plant, chamber, or experimental-run identifier."
        ),
    }


def write_markdown_report(result: dict[str, object], output_path: Path) -> None:
    """Write a short explanation beside the machine-readable JSON output."""
    threshold = result["threshold"]
    metrics_result = result["test_metrics"]
    direction_text = (
        "predict diseased when gas resistance is below"
        if threshold["direction"] == "lower_is_diseased"
        else "predict diseased when gas resistance is above"
    )
    report = f"""# Vivayu Threshold Baseline

This first model uses one feature only: `gas_resistance_ohm`.

## Rule learned from Day 1 and Day 2

{direction_text} **{threshold['threshold']:.1f} ohm**.

The threshold was selected using Day 1-2 training data only, by maximizing
balanced accuracy. Day 3 was held back until the final evaluation.

## Day 3 holdout result

- Accuracy: {metrics_result['accuracy']:.1%}
- Balanced accuracy: {metrics_result['balanced_accuracy']:.1%}
- Sensitivity (find diseased): {metrics_result['sensitivity']:.1%}
- Specificity (recognize controlled): {metrics_result['specificity']:.1%}
- True positive / false negative: {metrics_result['true_positive']} / {metrics_result['false_negative']}
- True negative / false positive: {metrics_result['true_negative']} / {metrics_result['false_positive']}

## Boundary

{result['interpretation_boundary']}
"""
    output_path.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/vivayu_readings.csv"),
        help="Path to the cleaned readings CSV.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for baseline reports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = pd.read_csv(args.input)
    result = train_and_evaluate(data)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "threshold_baseline_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    write_markdown_report(result, args.report_dir / "threshold_baseline_report.md")

    print(json.dumps(result, indent=2))
    print(f"\nReport: {args.report_dir / 'threshold_baseline_report.md'}")


if __name__ == "__main__":
    main()
