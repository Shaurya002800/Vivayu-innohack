"""Create reproducible exploratory analysis for the cleaned Vivayu dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "background": "#FFFFFF",
    "text": "#172033",
    "muted": "#64748B",
    "grid": "#D8E0EA",
    "healthy": "#15803D",
    "diseased": "#C2410C",
}

FEATURES = {
    "temperature_c": "Temperature (C)",
    "humidity_pct": "Humidity (%)",
    "gas_resistance_ohm": "Gas resistance (ohm)",
    "sraw": "SGP40 raw VOC signal (sraw)",
}


def count_by_day_and_condition(data: pd.DataFrame) -> list[dict[str, int | str]]:
    """Return row counts for every day/condition pair, including zeroes."""
    days = range(int(data["experimental_day"].min()), int(data["experimental_day"].max()) + 1)
    rows: list[dict[str, int | str]] = []
    for day in days:
        for condition in ("controlled", "diseased"):
            count = int(
                ((data["experimental_day"] == day) & (data["condition"] == condition)).sum()
            )
            rows.append(
                {"experimental_day": day, "condition": condition, "rows": count}
            )
    return rows


def median_by_day_and_condition(data: pd.DataFrame) -> list[dict[str, float | int | str]]:
    """Calculate medians so adjacent samples do not dominate the trend view."""
    grouped = (
        data.groupby(["experimental_day", "condition"], as_index=False)[list(FEATURES)]
        .median()
        .sort_values(["experimental_day", "condition"])
    )
    return [
        {
            "experimental_day": int(row["experimental_day"]),
            "condition": str(row["condition"]),
            **{feature: float(row[feature]) for feature in FEATURES},
        }
        for _, row in grouped.iterrows()
    ]


def figure_canvas(width: int = 1_280, height: int = 760) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), COLORS["background"])
    return image, ImageDraw.Draw(image)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    return int(draw.textbbox((0, 0), text, font=font)[2])


def draw_title(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    title_font = ImageFont.load_default(size=20)
    subtitle_font = ImageFont.load_default(size=13)
    draw.text((48, 32), title, fill=COLORS["text"], font=title_font)
    draw.text((48, 62), subtitle, fill=COLORS["muted"], font=subtitle_font)


def draw_count_chart(counts: list[dict[str, int | str]], output_path: Path) -> None:
    """Draw grouped bars showing the class balance at each experiment day."""
    image, draw = figure_canvas()
    draw_title(
        draw,
        "Valid readings by experiment day",
        "All accepted records. Uneven bars are a dataset limitation, not a disease result.",
    )
    chart_left, chart_top, chart_right, chart_bottom = 90, 150, 1_210, 650
    font = ImageFont.load_default(size=13)
    small_font = ImageFont.load_default(size=11)
    max_count = max(int(item["rows"]) for item in counts)
    days = sorted({int(item["experimental_day"]) for item in counts})

    for tick in range(0, max_count + 6, 5):
        y = chart_bottom - (tick / max_count) * (chart_bottom - chart_top)
        draw.line((chart_left, y, chart_right, y), fill=COLORS["grid"], width=1)
        draw.text((42, y - 6), str(tick), fill=COLORS["muted"], font=small_font)

    by_key = {(int(item["experimental_day"]), str(item["condition"])): int(item["rows"]) for item in counts}
    group_width = (chart_right - chart_left) / len(days)
    bar_width = 42
    for index, day in enumerate(days):
        centre = chart_left + group_width * (index + 0.5)
        for offset, condition in [(-bar_width - 4, "controlled"), (4, "diseased")]:
            value = by_key[(day, condition)]
            x0 = int(centre + offset)
            x1 = x0 + bar_width
            y1 = chart_bottom
            y0 = y1 - int((value / max_count) * (chart_bottom - chart_top)) if value else y1
            color = COLORS["healthy"] if condition == "controlled" else COLORS["diseased"]
            draw.rectangle((x0, y0, x1, y1), fill=color)
            draw.text((x0 + 8, y0 - 20), str(value), fill=COLORS["text"], font=small_font)
        label = f"Day {day}"
        draw.text((int(centre - text_width(draw, label, font) / 2), 675), label, fill=COLORS["text"], font=font)

    draw.rectangle((920, 96, 938, 112), fill=COLORS["healthy"])
    draw.text((946, 96), "Controlled", fill=COLORS["text"], font=small_font)
    draw.rectangle((1_060, 96, 1_078, 112), fill=COLORS["diseased"])
    draw.text((1_086, 96), "Diseased", fill=COLORS["text"], font=small_font)
    image.save(output_path)


def draw_line_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    feature: str,
    medians: list[dict[str, float | int | str]],
) -> None:
    """Draw one feature's day-by-day median for controlled and diseased samples."""
    left, top, right, bottom = box
    label_font = ImageFont.load_default(size=13)
    tick_font = ImageFont.load_default(size=10)
    draw.rectangle(box, outline=COLORS["grid"], width=1)
    draw.text((left + 12, top + 10), FEATURES[feature], fill=COLORS["text"], font=label_font)

    values = [float(row[feature]) for row in medians]
    low, high = min(values), max(values)
    padding = (high - low) * 0.12 or max(abs(high) * 0.05, 1)
    low, high = low - padding, high + padding
    chart_top, chart_bottom = top + 52, bottom - 42
    chart_left, chart_right = left + 58, right - 18
    days = [1, 2, 3, 4, 5]

    for fraction in (0, 0.5, 1):
        value = low + (high - low) * fraction
        y = chart_bottom - fraction * (chart_bottom - chart_top)
        draw.line((chart_left, y, chart_right, y), fill=COLORS["grid"], width=1)
        draw.text((left + 8, y - 5), f"{value:.1f}", fill=COLORS["muted"], font=tick_font)

    for index, day in enumerate(days):
        x = chart_left + index * (chart_right - chart_left) / (len(days) - 1)
        draw.text((x - 15, bottom - 26), f"D{day}", fill=COLORS["muted"], font=tick_font)

    for condition, color in [("controlled", COLORS["healthy"]), ("diseased", COLORS["diseased"])]:
        points: list[tuple[float, float]] = []
        for index, day in enumerate(days):
            matching = [row for row in medians if row["experimental_day"] == day and row["condition"] == condition]
            if not matching:
                if len(points) >= 2:
                    draw.line(points, fill=color, width=3)
                points = []
                continue
            value = float(matching[0][feature])
            x = chart_left + index * (chart_right - chart_left) / (len(days) - 1)
            y = chart_bottom - ((value - low) / (high - low)) * (chart_bottom - chart_top)
            points.append((x, y))
        if len(points) >= 2:
            draw.line(points, fill=color, width=3)
        for x, y in points:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)


def draw_median_trends(medians: list[dict[str, float | int | str]], output_path: Path) -> None:
    """Draw four day-by-day median plots using only unflagged measurements."""
    image, draw = figure_canvas(height=880)
    draw_title(
        draw,
        "Median sensor trends by day",
        "Unflagged records only. Missing Day 5 controlled data is intentionally shown as a gap.",
    )
    boxes = [(48, 130, 632, 465), (648, 130, 1_232, 465), (48, 500, 632, 835), (648, 500, 1_232, 835)]
    for box, feature in zip(boxes, FEATURES):
        draw_line_panel(draw, box, feature, medians)

    legend_font = ImageFont.load_default(size=12)
    draw.line((48, 102, 72, 102), fill=COLORS["healthy"], width=3)
    draw.text((80, 95), "Controlled", fill=COLORS["text"], font=legend_font)
    draw.line((180, 102, 204, 102), fill=COLORS["diseased"], width=3)
    draw.text((212, 95), "Diseased", fill=COLORS["text"], font=legend_font)
    image.save(output_path)


def draw_scatter(data: pd.DataFrame, output_path: Path) -> None:
    """Draw the relationship between the two VOC-related signals."""
    image, draw = figure_canvas()
    draw_title(
        draw,
        "Gas resistance versus SGP40 raw VOC signal",
        "Unflagged records only. This is a visual comparison, not a proof of disease causation.",
    )
    left, top, right, bottom = 105, 140, 1_220, 665
    small_font = ImageFont.load_default(size=11)
    x_values = data["gas_resistance_ohm"]
    y_values = data["sraw"]
    x_low, x_high = float(x_values.min()), float(x_values.max())
    y_low, y_high = float(y_values.min()), float(y_values.max())
    x_padding = (x_high - x_low) * 0.05
    y_padding = (y_high - y_low) * 0.05
    x_low, x_high = x_low - x_padding, x_high + x_padding
    y_low, y_high = y_low - y_padding, y_high + y_padding

    for fraction in (0, 0.25, 0.5, 0.75, 1):
        x = left + fraction * (right - left)
        y = bottom - fraction * (bottom - top)
        draw.line((x, top, x, bottom), fill=COLORS["grid"], width=1)
        draw.line((left, y, right, y), fill=COLORS["grid"], width=1)
        draw.text((x - 18, bottom + 10), f"{x_low + fraction * (x_high - x_low):.0f}", fill=COLORS["muted"], font=small_font)
        draw.text((25, y - 5), f"{y_low + fraction * (y_high - y_low):.0f}", fill=COLORS["muted"], font=small_font)

    for _, row in data.iterrows():
        x = left + ((float(row["gas_resistance_ohm"]) - x_low) / (x_high - x_low)) * (right - left)
        y = bottom - ((float(row["sraw"]) - y_low) / (y_high - y_low)) * (bottom - top)
        color = COLORS["healthy"] if row["condition"] == "controlled" else COLORS["diseased"]
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)

    draw.text((520, 715), "Gas resistance (ohm)", fill=COLORS["text"], font=ImageFont.load_default(size=13))
    draw.text((105, 96), "SGP40 raw VOC signal (sraw)", fill=COLORS["text"], font=ImageFont.load_default(size=13))
    draw.rectangle((930, 92, 946, 108), fill=COLORS["healthy"])
    draw.text((954, 92), "Controlled", fill=COLORS["text"], font=small_font)
    draw.rectangle((1_070, 92, 1_086, 108), fill=COLORS["diseased"])
    draw.text((1_094, 92), "Diseased", fill=COLORS["text"], font=small_font)
    image.save(output_path)


def build_summary(data: pd.DataFrame) -> dict[str, object]:
    """Return the numbers behind the figures in JSON-serializable form."""
    data = data.copy()
    data["quality_flag"] = data["quality_flag"].fillna("")
    unflagged = data[data["quality_flag"] == ""].copy()
    all_counts = count_by_day_and_condition(data)
    unflagged_medians = median_by_day_and_condition(unflagged)

    return {
        "accepted_rows": int(len(data)),
        "unflagged_rows": int(len(unflagged)),
        "quality_flags": {
            "exact_duplicate_rows": int(data["quality_flag"].str.contains("exact_duplicate").sum()),
            "nonincreasing_timestamp_rows": int(data["quality_flag"].str.contains("nonincreasing_timestamp").sum()),
            "any_flagged_rows": int((data["quality_flag"] != "").sum()),
        },
        "accepted_counts_by_day_and_condition": all_counts,
        "unflagged_medians_by_day_and_condition": unflagged_medians,
        "overall_medians_by_condition": [
            {
                "condition": str(condition),
                **{feature: float(value) for feature, value in group[list(FEATURES)].median().items()},
            }
            for condition, group in unflagged.groupby("condition")
        ],
        "analysis_notes": [
            "Day 5 has no controlled readings, so direct healthy-versus-diseased comparison is unavailable for that day.",
            "Day 4 has only seven controlled readings versus 35 diseased readings.",
            "No plant, chamber, or experimental-run identifier exists in this dataset; a random row split would risk time-series leakage.",
            "Plots use unflagged records for trends and scatter plots; the count chart uses all accepted records.",
        ],
    }


def write_markdown_report(summary: dict[str, object], output_path: Path) -> None:
    """Write a short human-readable companion to the JSON summary."""
    counts = summary["accepted_counts_by_day_and_condition"]
    count_lines = "\n".join(
        f"| {item['experimental_day']} | {item['condition']} | {item['rows']} |" for item in counts
    )
    flags = summary["quality_flags"]
    notes = "\n".join(f"- {note}" for note in summary["analysis_notes"])
    report = f"""# Vivayu Exploratory Data Analysis

## Dataset snapshot

- Accepted sensor readings: {summary['accepted_rows']}
- Unflagged readings used for trend and scatter plots: {summary['unflagged_rows']}
- Rows flagged as exact duplicates: {flags['exact_duplicate_rows']}
- Rows flagged for non-increasing timestamps: {flags['nonincreasing_timestamp_rows']}

## Accepted readings by day and condition

| Experiment day | Condition | Readings |
| --- | --- | ---: |
{count_lines}

## Interpretation boundaries

{notes}

These figures describe this experiment. They do not prove that a sensor measures a
specific VOC compound or that the observed difference is caused only by infection.
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
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for JSON, Markdown, and PNG analysis outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = pd.read_csv(args.input)
    data["quality_flag"] = data["quality_flag"].fillna("")
    unflagged = data[data["quality_flag"] == ""].copy()

    if data.empty or unflagged.empty:
        raise ValueError("EDA needs at least one accepted and one unflagged reading.")

    figures_dir = args.report_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(data)

    (args.report_dir / "eda_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    write_markdown_report(summary, args.report_dir / "eda_report.md")
    draw_count_chart(summary["accepted_counts_by_day_and_condition"], figures_dir / "records_by_day_and_condition.png")
    draw_median_trends(summary["unflagged_medians_by_day_and_condition"], figures_dir / "median_sensor_trends.png")
    draw_scatter(unflagged, figures_dir / "gas_vs_sraw_scatter.png")

    print(json.dumps(summary, indent=2))
    print(f"\nReport: {args.report_dir / 'eda_report.md'}")
    print(f"Figures: {figures_dir}")


if __name__ == "__main__":
    main()
