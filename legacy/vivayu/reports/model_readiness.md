# Vivayu Model Readiness

## Status: research only, not deployable

The current code pipeline works, but the data evidence does not support using a
model as a real crop-disease decision system yet.

## Evidence

- Accepted readings: 241
- Unflagged readings: 195
- Five-reading windows: 37
- Window features: 33
- Training windows from Day 1-2: 13
- Day 3 Random Forest balanced accuracy: 28.8%
- Day 3 Random Forest sensitivity / specificity: 57.7% / 0.0%

## Why deployment is blocked

- The saved multifeature Random Forest has poor Day 3 holdout performance.
- The dataset has no independent plant, chamber, or experimental-run identifier for external validation.
- Window features outnumber available training windows, making a window model prone to memorization.
- Controlled readings are missing for experiment day(s): 4, 5.

## Next data collection requirements

- Collect controlled and diseased data for every experiment day under the same sampling protocol.
- Record plant_id, chamber_id, sensor_id, experimental_run_id, and an infection ground-truth label.
- Use multiple plants per condition and repeat the experiment on separate runs.
- Keep sampling rate, sensor warm-up, heater settings, compensation, distance, and airflow consistent.
