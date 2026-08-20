# Vivayu Threshold Baseline

This first model uses one feature only: `gas_resistance_ohm`.

## Rule learned from Day 1 and Day 2

predict diseased when gas resistance is below **107380.5 ohm**.

The threshold was selected using Day 1-2 training data only, by maximizing
balanced accuracy. Day 3 was held back until the final evaluation.

## Day 3 holdout result

- Accuracy: 79.6%
- Balanced accuracy: 78.8%
- Sensitivity (find diseased): 57.7%
- Specificity (recognize controlled): 100.0%
- True positive / false negative: 15 / 11
- True negative / false positive: 28 / 0

## Boundary

This is a within-experiment, time-ordered baseline. It is not external validation because the dataset has no independent plant, chamber, or experimental-run identifier.
