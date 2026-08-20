# Vivayu Exploratory Data Analysis

## Dataset snapshot

- Accepted sensor readings: 241
- Unflagged readings used for trend and scatter plots: 195
- Rows flagged as exact duplicates: 44
- Rows flagged for non-increasing timestamps: 43

## Accepted readings by day and condition

| Experiment day | Condition | Readings |
| --- | --- | ---: |
| 1 | controlled | 32 |
| 1 | diseased | 22 |
| 2 | controlled | 26 |
| 2 | diseased | 26 |
| 3 | controlled | 28 |
| 3 | diseased | 27 |
| 4 | controlled | 7 |
| 4 | diseased | 35 |
| 5 | controlled | 0 |
| 5 | diseased | 38 |

## Interpretation boundaries

- Day 5 has no controlled readings, so direct healthy-versus-diseased comparison is unavailable for that day.
- Day 4 has only seven controlled readings versus 35 diseased readings.
- No plant, chamber, or experimental-run identifier exists in this dataset; a random row split would risk time-series leakage.
- Plots use unflagged records for trends and scatter plots; the count chart uses all accepted records.

These figures describe this experiment. They do not prove that a sensor measures a
specific VOC compound or that the observed difference is caused only by infection.
