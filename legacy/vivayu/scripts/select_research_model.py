"""Select Vivayu's strongest current research model with day-grouped validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from model_components import GasThresholdClassifier


FEATURES = [
    "temperature_c",
    "humidity_pct",
    "pressure_pa",
    "gas_resistance_ohm",
    "sraw",
]
ELIGIBLE_DAYS = [1, 2, 3]


def build_candidates() -> dict[str, object]:
    """Keep candidates small and interpretable for the available dataset size."""
    return {
        "gas_threshold": GasThresholdClassifier(),
        "logistic_regression": Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=0.5,
                        class_weight="balanced",
                        max_iter=1_000,
                        solver="liblinear",
                        random_state=42,
                    ),
                ),
            ]
        ),
        "rbf_svm": Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    SVC(C=1.0, kernel="rbf", probability=True, class_weight="balanced", random_state=42),
                ),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=3,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=300,
            max_depth=4,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        ),
    }


def prepare_data(data: pd.DataFrame) -> pd.DataFrame:
    """Keep only unflagged rows from days that have both classes."""
    data = data.copy()
    data["quality_flag"] = data["quality_flag"].fillna("")
    eligible = data[
        (data["quality_flag"] == "") & (data["experimental_day"].isin(ELIGIBLE_DAYS))
    ].copy()
    if eligible[FEATURES].isna().any().any():
        raise ValueError("Eligible data has missing model features.")
    return eligible


def score(y_true: pd.Series, predictions: np.ndarray) -> dict[str, float]:
    """Use balanced accuracy so both classes matter equally."""
    return {
        "accuracy": float(accuracy_score(y_true, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "sensitivity": float(recall_score(y_true, predictions, zero_division=0)),
    }


def evaluate_candidates(data: pd.DataFrame) -> tuple[dict[str, object], dict[str, object]]:
    """Leave one experiment day out for each candidate model."""
    eligible = prepare_data(data)
    fold_rows: list[dict[str, object]] = []
    aggregates: list[dict[str, object]] = []

    for name in build_candidates():
        candidate_scores: list[dict[str, float]] = []
        for held_out_day in ELIGIBLE_DAYS:
            training = eligible[eligible["experimental_day"] != held_out_day]
            testing = eligible[eligible["experimental_day"] == held_out_day]
            model = build_candidates()[name]
            model.fit(training[FEATURES], training["infected"])
            predictions = model.predict(testing[FEATURES])
            metrics = score(testing["infected"], predictions)
            candidate_scores.append(metrics)
            fold_rows.append(
                {
                    "candidate": name,
                    "held_out_day": held_out_day,
                    "training_rows": int(len(training)),
                    "test_rows": int(len(testing)),
                    **metrics,
                }
            )

        aggregates.append(
            {
                "candidate": name,
                "mean_balanced_accuracy": float(np.mean([item["balanced_accuracy"] for item in candidate_scores])),
                "min_balanced_accuracy": float(np.min([item["balanced_accuracy"] for item in candidate_scores])),
                "mean_accuracy": float(np.mean([item["accuracy"] for item in candidate_scores])),
                "mean_sensitivity": float(np.mean([item["sensitivity"] for item in candidate_scores])),
            }
        )

    aggregates.sort(
        key=lambda item: (item["mean_balanced_accuracy"], item["min_balanced_accuracy"]), reverse=True
    )
    winner = aggregates[0]
    selected_model = build_candidates()[winner["candidate"]]
    selected_model.fit(eligible[FEATURES], eligible["infected"])

    report = {
        "selection_status": "research_candidate_only",
        "selection_method": "leave_one_experiment_day_out on unflagged Days 1-3",
        "eligible_days": ELIGIBLE_DAYS,
        "eligible_rows": int(len(eligible)),
        "features": FEATURES,
        "candidate_summary": aggregates,
        "fold_results": fold_rows,
        "selected_candidate": str(winner["candidate"]),
        "selected_candidate_mean_balanced_accuracy": float(winner["mean_balanced_accuracy"]),
        "selection_boundary": (
            "This score selects a research candidate from one small experiment. It is not an external "
            "field-accuracy claim and must not be used for automated crop treatment decisions."
        ),
    }
    bundle = {
        "model": selected_model,
        "features": FEATURES,
        "positive_class": "diseased_pattern",
        "model_name": str(winner["candidate"]),
        "training_days": ELIGIBLE_DAYS,
        "selection_status": "research_candidate_only",
    }
    return report, bundle


def write_markdown_report(report: dict[str, object], output_path: Path) -> None:
    """Write the model comparison in a readable table."""
    candidate_rows = "\n".join(
        f"| {row['candidate']} | {row['mean_balanced_accuracy']:.1%} | {row['min_balanced_accuracy']:.1%} | {row['mean_sensitivity']:.1%} |"
        for row in report["candidate_summary"]
    )
    markdown = f"""# Vivayu Research Model Selection

## Selected candidate

`{report['selected_candidate']}` was selected using mean balanced accuracy
across leave-one-day-out validation on unflagged Days 1-3 data.

## Candidate comparison

| Candidate | Mean balanced accuracy | Lowest day score | Mean sensitivity |
| --- | ---: | ---: | ---: |
{candidate_rows}

## Boundary

{report['selection_boundary']}
"""
    output_path.write_text(markdown, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/vivayu_readings.csv"))
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, bundle = evaluate_candidates(pd.read_csv(args.input))
    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.model_dir / "vivayu_research_candidate.joblib")
    (args.report_dir / "model_selection_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_markdown_report(report, args.report_dir / "model_selection_report.md")
    print(json.dumps(report, indent=2))
    print(f"\nModel: {args.model_dir / 'vivayu_research_candidate.joblib'}")
    print(f"Report: {args.report_dir / 'model_selection_report.md'}")


if __name__ == "__main__":
    main()
