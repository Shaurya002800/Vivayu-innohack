# Vivayu Research Model Selection

## Selected candidate

`gas_threshold` was selected using mean balanced accuracy
across leave-one-day-out validation on unflagged Days 1-3 data.

## Candidate comparison

| Candidate | Mean balanced accuracy | Lowest day score | Mean sensitivity |
| --- | ---: | ---: | ---: |
| gas_threshold | 89.6% | 78.8% | 79.2% |
| extra_trees | 63.4% | 40.0% | 79.2% |
| logistic_regression | 56.3% | 40.0% | 45.9% |
| random_forest | 47.9% | 28.8% | 79.2% |
| rbf_svm | 45.6% | 40.0% | 79.2% |

## Boundary

This score selects a research candidate from one small experiment. It is not an external field-accuracy claim and must not be used for automated crop treatment decisions.
