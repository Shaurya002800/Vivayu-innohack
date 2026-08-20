# Vivayu Random Forest: First Multifeature Model

## What it learned from

The model trained on unflagged Day 1-2 records and was evaluated once on
unflagged Day 3 records. It used these sensor features:

`temperature_c`, `humidity_pct`, `pressure_pa`, `gas_resistance_ohm`, `sraw`

It did not use timestamp, experiment day, labels, or source-row metadata.

## Day 3 holdout result

- Accuracy: 27.8%
- Balanced accuracy: 28.8%
- Precision: 34.9%
- Sensitivity: 57.7%
- Specificity: 0.0%
- True positive / false negative: 15 / 11
- True negative / false positive: 0 / 28

The model predicted `11` controlled and
`43` diseased records on the holdout day.

## Training-versus-holdout check

- Training balanced accuracy: 100.0%
- Day 3 holdout balanced accuracy: 28.8%

Large disagreement between these scores is a warning sign of overfitting or
environmental shift. The per-record Day 3 prediction audit is stored separately
as `reports/random_forest_day3_predictions.csv`.

## Model feature importance

| Feature | Relative importance |
| --- | ---: |
| `sraw` | 39.1% |
| `gas_resistance_ohm` | 32.7% |
| `temperature_c` | 14.9% |
| `humidity_pct` | 8.3% |
| `pressure_pa` | 5.1% |

## Boundary

This is a time-ordered within-experiment holdout, not external validation. Feature importance describes this model's reliance on variables; it does not prove causal disease biomarkers.
