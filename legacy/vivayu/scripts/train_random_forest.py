"""Train and evaluate Vivayu's first multifeature Random Forest model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, precision_score, recall_score


# Timestamp and experimental day are intentionally excluded to prevent leakage.
FEATURES = [
    "temperature_c",
    "humidity_pct",
    "pressure_pa",
    "gas_resistance_ohm",
    "sraw",
]


def prepare_split(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use unflagged Days 1-2 for training and Day 3 as a future holdout."""
    data = data.copy()
    data["quality_flag"] = data["quality_flag"].fillna("")
    unflagged = data[data["quality_flag"] == ""].copy()
    training = unflagged[unflagged["experimental_day"].isin([1, 2])].copy()
    testing = unflagged[unflagged["experimental_day"] == 3].copy()

    for name, frame in (("training", training), ("testing", testing)):
        if set(frame["infected"]) != {0, 1}:
            raise ValueError(f"{name.title()} data must contain both controlled and diseased rows.")
        if frame[FEATURES].isna().any().any():
            raise ValueError(f"{name.title()} data has missing model features.")

    return training, testing


def build_model() -> RandomForestClassifier:
    """Return a deliberately small forest suited to this small first dataset."""
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )


def evaluate(y_true: pd.Series, y_pred: pd.Series) -> dict[str, object]:
    """Calculate binary classification metrics where 1 means diseased."""
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    true_negative, false_positive, false_negative, true_positive = matrix.ravel()
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "sensitivity": float(recall_score(y_true, y_pred, zero_division=0)),
        "specificity": float(true_negative / (true_negative + false_positive)),
        "confusion_matrix": {
            "true_negative": int(true_negative),
            "false_positive": int(false_positive),
            "false_negative": int(false_negative),
            "true_positive": int(true_positive),
        },
    }


def train_and_evaluate(
    data: pd.DataFrame,
) -> tuple[dict[str, object], dict[str, object], pd.DataFrame]:
    """Train the forest and return a report plus its serializable model bundle."""
    training, testing = prepare_split(data)
    model = build_model()
    model.fit(training[FEATURES], training["infected"])

    training_predictions = model.predict(training[FEATURES])
    predictions = model.predict(testing[FEATURES])
    probabilities = model.predict_proba(testing[FEATURES])[:, 1]
    result = {
        "model_type": "random_forest_binary_classifier",
        "features": FEATURES,
        "excluded_columns": ["sample_id", "source_row", "source_cell", "experimental_day", "timestamp_ms", "condition", "label", "infection_days", "quality_flag"],
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
        "model_parameters": {
            "n_estimators": 300,
            "max_depth": 4,
            "min_samples_leaf": 3,
            "class_weight": "balanced",
            "random_state": 42,
            "decision_threshold": 0.5,
        },
        "training_metrics": evaluate(training["infected"], training_predictions),
        "test_metrics": evaluate(testing["infected"], predictions),
        "test_prediction_counts": {
            "predicted_controlled": int((predictions == 0).sum()),
            "predicted_diseased": int((predictions == 1).sum()),
        },
        "mean_test_disease_probability": float(probabilities.mean()),
        "feature_importance": {
            feature: float(importance)
            for feature, importance in sorted(
                zip(FEATURES, model.feature_importances_), key=lambda item: item[1], reverse=True
            )
        },
        "interpretation_boundary": (
            "This is a time-ordered within-experiment holdout, not external validation. "
            "Feature importance describes this model's reliance on variables; it does not prove causal disease biomarkers."
        ),
    }
    bundle = {
        "model": model,
        "features": FEATURES,
        "positive_class": "diseased",
        "training_days": [1, 2],
        "quality_rule": "quality_flag must be empty",
    }
    prediction_audit = testing[
        ["sample_id", "source_row", "experimental_day", "condition", "infected"]
    ].copy()
    prediction_audit["predicted_infected"] = predictions
    prediction_audit["disease_probability"] = probabilities
    return result, bundle, prediction_audit


def write_markdown_report(result: dict[str, object], output_path: Path) -> None:
    """Create a human-readable companion for the JSON metrics report."""
    metrics = result["test_metrics"]
    training_metrics = result["training_metrics"]
    matrix = metrics["confusion_matrix"]
    importance_lines = "\n".join(
        f"| `{feature}` | {importance:.1%} |"
        for feature, importance in result["feature_importance"].items()
    )
    report = f"""# Vivayu Random Forest: First Multifeature Model

## What it learned from

The model trained on unflagged Day 1-2 records and was evaluated once on
unflagged Day 3 records. It used these sensor features:

{', '.join(f'`{feature}`' for feature in result['features'])}

It did not use timestamp, experiment day, labels, or source-row metadata.

## Day 3 holdout result

- Accuracy: {metrics['accuracy']:.1%}
- Balanced accuracy: {metrics['balanced_accuracy']:.1%}
- Precision: {metrics['precision']:.1%}
- Sensitivity: {metrics['sensitivity']:.1%}
- Specificity: {metrics['specificity']:.1%}
- True positive / false negative: {matrix['true_positive']} / {matrix['false_negative']}
- True negative / false positive: {matrix['true_negative']} / {matrix['false_positive']}

The model predicted `{result['test_prediction_counts']['predicted_controlled']}` controlled and
`{result['test_prediction_counts']['predicted_diseased']}` diseased records on the holdout day.

## Training-versus-holdout check

- Training balanced accuracy: {training_metrics['balanced_accuracy']:.1%}
- Day 3 holdout balanced accuracy: {metrics['balanced_accuracy']:.1%}

Large disagreement between these scores is a warning sign of overfitting or
environmental shift. The per-record Day 3 prediction audit is stored separately
as `reports/random_forest_day3_predictions.csv`.

## Model feature importance

| Feature | Relative importance |
| --- | ---: |
{importance_lines}

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
        "--model-dir",
        type=Path,
        default=Path("models"),
        help="Directory for the saved model bundle.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for the JSON and Markdown reports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = pd.read_csv(args.input)
    result, bundle, prediction_audit = train_and_evaluate(data)
    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(bundle, args.model_dir / "vivayu_binary_random_forest_day1_2.joblib")
    (args.report_dir / "random_forest_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    prediction_audit.to_csv(args.report_dir / "random_forest_day3_predictions.csv", index=False)
    write_markdown_report(result, args.report_dir / "random_forest_report.md")

    print(json.dumps(result, indent=2))
    print(f"\nModel: {args.model_dir / 'vivayu_binary_random_forest_day1_2.joblib'}")
    print(f"Report: {args.report_dir / 'random_forest_report.md'}")


if __name__ == "__main__":
    main()
