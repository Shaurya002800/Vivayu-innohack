"""Convert consecutive Vivayu readings into non-overlapping ML feature windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


SENSOR_COLUMNS = [
    "temperature_c",
    "humidity_pct",
    "pressure_pa",
    "gas_resistance_ohm",
    "sraw",
]


def slope(values: pd.Series) -> float:
    """Calculate the change per reading within one short sensor window."""
    if len(values) < 2:
        return 0.0
    positions = np.arange(len(values))
    return float(np.polyfit(positions, values.to_numpy(dtype=float), deg=1)[0])


def summarize_window(segment: pd.DataFrame, window_id: str) -> dict[str, object]:
    """Create one ML row from a fixed-size sequence of sensor readings."""
    first = segment.iloc[0]
    result: dict[str, object] = {
        "window_id": window_id,
        "experimental_day": int(first["experimental_day"]),
        "condition": str(first["condition"]),
        "infected": int(first["infected"]),
        "infection_days": int(first["infection_days"]),
        "label": str(first["label"]),
        "readings_in_window": int(len(segment)),
        "source_row_start": int(segment["source_row"].min()),
        "source_row_end": int(segment["source_row"].max()),
        "timestamp_start_ms": int(segment["timestamp_ms"].iloc[0]),
        "timestamp_end_ms": int(segment["timestamp_ms"].iloc[-1]),
    }

    for column in SENSOR_COLUMNS:
        values = segment[column]
        result[f"{column}_mean"] = float(values.mean())
        result[f"{column}_std"] = float(values.std(ddof=0))
        result[f"{column}_min"] = float(values.min())
        result[f"{column}_max"] = float(values.max())
        result[f"{column}_range"] = float(values.max() - values.min())
        result[f"{column}_slope"] = slope(values)

    result["sraw_per_humidity_mean"] = float((segment["sraw"] / segment["humidity_pct"]).mean())
    result["gas_per_humidity_mean"] = float(
        (segment["gas_resistance_ohm"] / segment["humidity_pct"]).mean()
    )
    result["sraw_gas_ratio_mean"] = float(
        (segment["sraw"] / segment["gas_resistance_ohm"]).mean()
    )
    return result


def build_windows(data: pd.DataFrame, window_size: int = 5) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build non-overlapping windows separately for each day and condition."""
    if window_size < 2:
        raise ValueError("window_size must be at least 2.")

    data = data.copy()
    data["quality_flag"] = data["quality_flag"].fillna("")
    usable = data[data["quality_flag"] == ""].copy()
    usable = usable.sort_values(["experimental_day", "condition", "source_row"])

    windows: list[dict[str, object]] = []
    group_summary: list[dict[str, object]] = []
    window_number = 1

    for (day, condition), group in usable.groupby(["experimental_day", "condition"], sort=True):
        group = group.reset_index(drop=True)
        complete_windows = len(group) // window_size
        used_rows = complete_windows * window_size
        group_summary.append(
            {
                "experimental_day": int(day),
                "condition": str(condition),
                "usable_readings": int(len(group)),
                "windows": int(complete_windows),
                "unused_remainder_readings": int(len(group) - used_rows),
            }
        )

        for start in range(0, used_rows, window_size):
            segment = group.iloc[start : start + window_size]
            windows.append(summarize_window(segment, f"WIN-{window_number:03d}"))
            window_number += 1

    window_data = pd.DataFrame(windows)
    summary = {
        "window_size_readings": window_size,
        "accepted_readings": int(len(data)),
        "unflagged_readings_available": int(len(usable)),
        "readings_used_in_windows": int(len(window_data) * window_size),
        "unused_remainder_readings": int(len(usable) - len(window_data) * window_size),
        "windows_created": int(len(window_data)),
        "windows_by_day_and_condition": group_summary,
        "important_boundary": (
            "Windows are consecutive readings within one day and condition, ordered by source row. "
            "They are non-overlapping to avoid creating near-duplicate training examples."
        ),
    }
    return window_data, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/vivayu_readings.csv"),
        help="Path to the cleaned readings CSV.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=5,
        help="Number of sequential readings per non-overlapping window.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/vivayu_windows_5.csv"),
        help="Path for the window feature CSV.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/window_summary.json"),
        help="Path for the JSON window-building summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = pd.read_csv(args.input)
    windows, summary = build_windows(data, args.window_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    windows.to_csv(args.output, index=False)
    args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWindow features: {args.output}")


if __name__ == "__main__":
    main()
