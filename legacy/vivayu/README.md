# Vivayu ML Pipeline

This repository converts the raw Vivayu tomato experiment workbook into a
reproducible dataset for machine learning.

## Current stage: raw data cleaning

The source workbook is formatted like experiment notes: day markers are in
column A, controlled readings are in column C, and diseased readings are in
column K. A model cannot train directly on that layout, so the cleaning script
creates one row per sensor reading.

The six sensor values are interpreted in this order:

1. `timestamp_ms`
2. `temperature_c`
3. `humidity_pct`
4. `pressure_pa`
5. `gas_resistance_ohm`
6. `sraw`

`sraw` is treated as the SGP40 raw VOC signal. It is not treated as VOC ppm or
as a direct measurement of ethylene.

## Setup once

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## Run the complete pipeline

```bash
./.venv/bin/python scripts/run_pipeline.py
```

This regenerates cleaned data, EDA, baseline and Random Forest reports, window
features, grouped model selection, and the readiness report.

## Run the cleaner by itself

```bash
./.venv/bin/python scripts/clean_dataset.py
```

Outputs:

- `data/processed/vivayu_readings.csv`: accepted sensor readings and labels.
- `data/processed/rejected_rows.csv`: non-empty cells that could not become a
  reading, with a reason.
- `reports/cleaning_summary.json`: row counts, label balance, flags, and ranges.

The cleaner does not silently delete duplicate or suspicious readings. It adds
a `quality_flag` so we can study them before deciding whether they should be
excluded from model training.

## Run the parsing tests

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

## Explore the cleaned data

```bash
./.venv/bin/python scripts/explore_data.py
```

This produces an analysis report and three figures in `reports/`. Trend and
scatter plots use only unflagged records so repeated measurements do not
visually dominate the result. The count chart uses every accepted record to
show the real class balance.

## Train the first baseline

```bash
./.venv/bin/python scripts/train_threshold_baseline.py
```

The baseline is deliberately simple: it learns one gas-resistance threshold
from unflagged Day 1-2 readings and evaluates it once on unflagged Day 3
readings. It does not use timestamp or experiment day as an ML feature.

## Train the first Random Forest

```bash
./.venv/bin/python scripts/train_random_forest.py
```

This model combines the five sensor features and saves a model bundle in
`models/`. It uses the same time-ordered Day 1-2 / Day 3 split as the threshold
baseline, so their results are directly comparable. The generated Day 3
prediction audit lets you inspect errors one record at a time.

## Build short sensor windows

```bash
./.venv/bin/python scripts/build_windows.py
```

The window builder summarizes five consecutive unflagged readings from the same
experiment day and condition into one feature row. It creates means, variation,
ranges, slopes, and humidity-normalized VOC-related ratios. The generated
`vivayu_windows_5.csv` is the right shape for a future real-time window model,
but this first dataset yields only 37 non-overlapping windows, so it is not
enough independent data for a trustworthy production model.

## Check model readiness

```bash
./.venv/bin/python scripts/assess_model_readiness.py
```

This creates a data-backed readiness decision. With the current experiment, the
correct status is `research_only_not_deployable`: the pipeline is ready for
additional data, but the observed model behavior is not safe for real crop
decisions.

## Select the current research candidate

```bash
./.venv/bin/python scripts/select_research_model.py
```

The selection stage uses leave-one-day-out validation on Days 1-3. With the
current dataset, the transparent gas-resistance threshold is the best candidate
and is saved as `models/vivayu_research_candidate.joblib`.

## Run the local real-time dashboard

```bash
./.venv/bin/python scripts/run_dashboard.py
```

Open `http://127.0.0.1:8765` in a browser. Paste five sensor payloads in the
same six-value format emitted by the ESP32. The dashboard averages the selected
research model's five reading scores and returns a VOC-pattern monitoring result.
It deliberately labels results as research-only rather than disease diagnoses.
