"""Convert the Vivayu experiment workbook into machine-learning-ready CSV files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
PAYLOAD_PATTERN = re.compile(
    rf"^\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*,"
    rf"\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*$"
)
DAY_PATTERN = re.compile(r"day\s*(\d+)", re.IGNORECASE)

CONDITION_COLUMNS = {
    2: "controlled",  # Excel column C
    10: "diseased",  # Excel column K
}

OUTPUT_COLUMNS = [
    "sample_id",
    "source_row",
    "source_cell",
    "experimental_day",
    "condition",
    "infected",
    "infection_days",
    "label",
    "timestamp_ms",
    "temperature_c",
    "humidity_pct",
    "pressure_pa",
    "gas_resistance_ohm",
    "sraw",
    "quality_flag",
]


def excel_column_name(zero_based_column: int) -> str:
    """Convert a zero-based column index to an Excel column name."""
    number = zero_based_column + 1
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def extract_payload(cell_value: object) -> tuple[list[float] | None, str | None]:
    """Extract six sensor values from a raw Excel cell.

    Returns (values, None) for a valid record and (None, reason) for a rejected
    non-empty cell. Empty cells are handled by the caller.
    """
    text = str(cell_value).strip()

    if "->" in text:
        text = text.rsplit("->", maxsplit=1)[1].strip()

    if text == "-":
        return None, "missing_sensor_payload"

    match = PAYLOAD_PATTERN.fullmatch(text)
    if not match:
        return None, "expected_six_comma_separated_numbers"

    return [float(value) for value in match.groups()], None


def basic_sensor_flags(values: list[float]) -> list[str]:
    """Flag impossible or broadly implausible values without deleting them."""
    timestamp, temperature, humidity, pressure, gas_resistance, sraw = values
    flags: list[str] = []

    if timestamp < 0:
        flags.append("negative_timestamp")
    if not -40 <= temperature <= 85:
        flags.append("temperature_out_of_range")
    if not 0 <= humidity <= 100:
        flags.append("humidity_out_of_range")
    if not 30_000 <= pressure <= 110_000:
        flags.append("pressure_out_of_range")
    if gas_resistance <= 0:
        flags.append("nonpositive_gas_resistance")
    if not 0 <= sraw <= 65_535:
        flags.append("sraw_out_of_range")

    return flags


def clean_workbook(input_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the experiment sheet and return accepted and rejected records."""
    raw = pd.read_excel(input_path, sheet_name=0, header=None, dtype=object)

    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    current_day: int | None = None

    for row_index, row in raw.iterrows():
        source_row = row_index + 1
        day_cell = row.iloc[0] if len(row) > 0 else None

        if pd.notna(day_cell):
            day_match = DAY_PATTERN.search(str(day_cell))
            if day_match:
                current_day = int(day_match.group(1))

        for column_index, condition in CONDITION_COLUMNS.items():
            cell_value = row.iloc[column_index]
            if pd.isna(cell_value):
                continue

            text = str(cell_value).strip()
            if not text:
                continue
            if text.lower() in {"controlled", "diseased"}:
                continue

            source_cell = f"{excel_column_name(column_index)}{source_row}"

            if current_day is None:
                rejected.append(
                    {
                        "source_row": source_row,
                        "source_cell": source_cell,
                        "experimental_day": None,
                        "condition": condition,
                        "original_cell": text,
                        "rejection_reason": "missing_day_context",
                    }
                )
                continue

            values, rejection_reason = extract_payload(text)
            if values is None:
                rejected.append(
                    {
                        "source_row": source_row,
                        "source_cell": source_cell,
                        "experimental_day": current_day,
                        "condition": condition,
                        "original_cell": text,
                        "rejection_reason": rejection_reason,
                    }
                )
                continue

            timestamp, temperature, humidity, pressure, gas_resistance, sraw = values
            infected = int(condition == "diseased")
            infection_days = current_day if infected else 0
            label = f"infected_day_{current_day}" if infected else "healthy"

            accepted.append(
                {
                    "source_row": source_row,
                    "source_cell": source_cell,
                    "experimental_day": current_day,
                    "condition": condition,
                    "infected": infected,
                    "infection_days": infection_days,
                    "label": label,
                    "timestamp_ms": int(timestamp),
                    "temperature_c": temperature,
                    "humidity_pct": humidity,
                    "pressure_pa": pressure,
                    "gas_resistance_ohm": gas_resistance,
                    "sraw": int(sraw),
                    "quality_flag": ";".join(basic_sensor_flags(values)),
                }
            )

    clean = pd.DataFrame(accepted)
    rejects = pd.DataFrame(rejected)

    if clean.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), rejects

    measurement_columns = [
        "experimental_day",
        "condition",
        "timestamp_ms",
        "temperature_c",
        "humidity_pct",
        "pressure_pa",
        "gas_resistance_ohm",
        "sraw",
    ]
    duplicate_mask = clean.duplicated(subset=measurement_columns, keep=False)

    previous_timestamp = clean.groupby(
        ["experimental_day", "condition"], sort=False
    )["timestamp_ms"].shift(1)
    nonincreasing_mask = previous_timestamp.notna() & (
        clean["timestamp_ms"] <= previous_timestamp
    )

    for index in clean.index:
        flags = [flag for flag in str(clean.at[index, "quality_flag"]).split(";") if flag]
        if duplicate_mask.at[index]:
            flags.append("exact_duplicate")
        if nonincreasing_mask.at[index]:
            flags.append("nonincreasing_timestamp")
        clean.at[index, "quality_flag"] = ";".join(flags)

    clean.insert(0, "sample_id", [f"VIV-{number:04d}" for number in range(1, len(clean) + 1)])
    return clean[OUTPUT_COLUMNS], rejects


def build_summary(clean: pd.DataFrame, rejects: pd.DataFrame) -> dict[str, object]:
    """Create a compact audit summary for checking the cleaning result."""
    counts = (
        clean.groupby(["experimental_day", "condition"])
        .size()
        .rename("accepted_rows")
        .reset_index()
    )
    rejection_counts = (
        rejects["rejection_reason"].value_counts().to_dict() if not rejects.empty else {}
    )

    flagged_rows = clean[clean["quality_flag"] != ""]
    return {
        "accepted_rows": int(len(clean)),
        "rejected_rows": int(len(rejects)),
        "accepted_by_day_and_condition": counts.to_dict(orient="records"),
        "rejections_by_reason": {str(key): int(value) for key, value in rejection_counts.items()},
        "flagged_rows": int(len(flagged_rows)),
        "labels": {str(key): int(value) for key, value in clean["label"].value_counts().items()},
        "measurement_ranges": {
            column: {
                "min": float(clean[column].min()),
                "max": float(clean[column].max()),
            }
            for column in [
                "temperature_c",
                "humidity_pct",
                "pressure_pa",
                "gas_resistance_ohm",
                "sraw",
            ]
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/Vivayu dataset tomato.xlsx"),
        help="Path to the raw Vivayu Excel workbook.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory for accepted and rejected CSV files.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/cleaning_summary.json"),
        help="Path for the JSON cleaning summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    clean, rejects = clean_workbook(args.input)
    clean.to_csv(args.output_dir / "vivayu_readings.csv", index=False)
    rejects.to_csv(args.output_dir / "rejected_rows.csv", index=False)

    summary = build_summary(clean, rejects)
    args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nClean data: {args.output_dir / 'vivayu_readings.csv'}")
    print(f"Rejected rows: {args.output_dir / 'rejected_rows.csv'}")
    print(f"Summary: {args.report}")


if __name__ == "__main__":
    main()
