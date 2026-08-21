#!/usr/bin/env python3
"""Watch canonical backend telemetry without opening or parsing the serial port."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


def _value(value: Any, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "Unavailable"
    return f"{float(value):.{decimals}f}{suffix}"


def render_state(state: dict[str, Any]) -> str:
    lines = [
        f"VIVAYU Aqua telemetry | {state['data_mode'].upper()}",
        "=" * 48,
    ]
    for zone_id in ("A", "B"):
        zone = state["zones"][zone_id]
        telemetry = zone["telemetry"]
        pressure = telemetry["pressure_pa"]
        lines.extend(
            [
                f"Zone {zone_id} | {telemetry['node_id'] or 'No node'} | "
                f"{'LIVE' if zone['online'] else 'STALE/OFFLINE'}",
                f"  Soil raw:   {_value(telemetry['soil_moisture_raw'], decimals=0)}",
                f"  Soil index: {_value(telemetry['soil_moisture_pct'], '%')}",
                f"  Temperature:{_value(telemetry['temperature_c'], ' °C')}",
                f"  Humidity:   {_value(telemetry['humidity_pct'], '%')}",
                f"  Pressure:   {_value(None if pressure is None else pressure / 100, ' hPa')}",
                f"  Age:        {_value(zone['telemetry_age_s'], ' s')}",
                "",
            ]
        )
    connection = state["telemetry_connection"]
    lines.append(
        f"Gateway {connection['status']} | accepted {connection['packets_received']} | "
        f"rejected {connection['packets_rejected']}"
    )
    return "\n".join(lines)


def fetch_state(api_base_url: str, timeout_s: float) -> dict[str, Any]:
    with urlopen(f"{api_base_url.rstrip('/')}/api/v1/state", timeout=timeout_s) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("VIVAYU_API_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval <= 0 or args.timeout <= 0:
        parser.error("interval and timeout must be positive")

    while True:
        try:
            state = fetch_state(args.api_base_url, args.timeout)
            print("\033[2J\033[H" + render_state(state), flush=True)
        except (URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
            print(f"Telemetry API unavailable: {error}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
