# VIVAYU Aqua - InnoHack 2.0
## Codex Master Reference and Complete Software Implementation Specification

**Target hackathon problem:** HTAD-05 - Solar-Powered Smart Irrigation System for Water-Scarce Regions  
**Primary implementation repository:** `Shaurya002800/Vivayu-innohack`  
**Existing Vivayu reference repository:** `Shaurya002800/Vivayu`  
**Existing Vivayu snapshot inspected:** `cc8008a36838fba97f289876a49d599f5d7dea25`  
**Document purpose:** This is the single source of truth for Codex while building the InnoHack version. Codex should read this file completely before changing code.

---

# 0. Instruction to Codex

You are implementing **VIVAYU Aqua**, a hackathon prototype that extends the existing Vivayu research sensing/ML work into a solar-powered, multi-zone irrigation intelligence and control system for water-scarce farms.

Follow these rules throughout implementation:

1. **Do not treat this as a generic smart-irrigation dashboard.** The hero feature is intelligent use of limited freshwater and marginal/higher-salinity water.
2. **Do not rewrite or reinterpret the existing Vivayu ML model.** Reuse it as a research-only plant/VOC monitoring signal.
3. **Do not let the current Vivayu research model autonomously trigger irrigation.** The existing repo explicitly marks the model as research-only/not deployable. Irrigation control must be governed by soil moisture, crop configuration, weather, water availability, source TDS, final mixed TDS, and explicit safety rules.
4. **Do not fake sensor data in live mode.** A simulation mode is required, but it must be visibly labelled everywhere.
5. **Fail safe.** Pumps/valves must default OFF. Stale/missing telemetry, unsafe TDS, invalid crop config, controller disconnect, or invalid commands must block automatic actuation.
6. **Build in milestones.** After each milestone: run tests, confirm the acceptance criteria, update `docs/STATUS.md`, then proceed.
7. **Preserve explainability.** Every irrigation decision must include machine-readable and human-readable reasons.
8. **Support Zone A and Zone B independently.** Never mix their telemetry buffers, crop configuration, model windows, irrigation history, or decisions.
9. **Keep all agronomic thresholds configurable and sourced.** Never hard-code a number and present it as a universal crop truth.
10. **Optimize for a reliable hackathon demo.** Working core behavior beats extra features.

---

# 1. Project in One Minute

VIVAYU Aqua has two field zones and two water qualities.

Each field zone sends soil and environmental data. The software knows the crop, sowing date/growth stage, weather forecast, available freshwater, and quality/TDS of the available water sources.

The system decides:

- Does Zone A or Zone B need irrigation?
- How much water is needed?
- Which zone is more urgent when freshwater is scarce?
- Should the system use **freshwater only**, **marginal water only**, or a **controlled blend**?
- If blending, how much of each source should be used?
- Is the final mixed water quality acceptable before it reaches the crop?
- Did irrigation actually improve soil moisture afterward?

The complete loop is:

**Sense -> Understand -> Decide -> Select/Blend Water -> Verify TDS -> Irrigate -> Verify Soil Response -> Log/Learn**

The farmer should not manually calculate ratios. The farmer primarily configures the crop, sowing date, zone name, water-source information, and available freshwater. The system calculates the rest.

---

# 2. What Makes This Different

Do not pitch the project as "AI + solar + soil sensor + pump". Those are supporting technologies.

The core innovation for the hackathon is:

> **VIVAYU Aqua treats freshwater as a scarce strategic resource and water quality as a control variable. It decides not only when/how much to irrigate, but which available water quality should be used for each crop zone, verifies the final TDS before irrigation, and preserves higher-quality freshwater where it is most valuable.**

The system can choose one of three modes for each irrigation event:

- `FRESH_ONLY`
- `MARGINAL_ONLY`
- `CONTROLLED_BLEND`

At farm scale this is intended as a **retrofit intelligence layer** on top of existing pumps, tanks, mainlines, surface-drip lines, and zone valves.

---

# 3. Important Reality About Existing Vivayu

The current `Shaurya002800/Vivayu` repository is primarily a **research ML/data pipeline**, not a production dashboard/backend.

The inspected repository currently contains:

- raw and processed tomato experiment data;
- data cleaning and EDA scripts;
- threshold, Random Forest, Extra Trees, logistic-regression and SVM research comparisons;
- a saved `vivayu_research_candidate.joblib` model bundle;
- a small local dashboard implemented with Python `ThreadingHTTPServer` and inline HTML;
- `vivayu_runtime.py`, which validates a six-value ESP32 payload and keeps a five-reading rolling window;
- tests covering data processing and runtime behavior.

The current runtime expects exactly these fields for the legacy Vivayu health signal:

```text
timestamp_ms
temperature_c
humidity_pct
pressure_pa
gas_resistance_ohm
sraw
```

The existing research selection currently chooses a **gas-resistance threshold classifier** as the strongest research candidate on the small experiment. The existing repo itself marks the model as **research-only** and says it must not be used as a field treatment decision system.

## Critical hardware compatibility rule

The selected current Vivayu research model depends on `gas_resistance_ohm` from the BME680-style gas channel.

Therefore:

- **BME680 -> compatible with the current gas-resistance input.**
- **BME280 alone -> not compatible with the current Vivayu model**, because it has no gas-resistance measurement.
- **SGP40 `sraw` -> compatible only if the same type/processing is used as during the original experiment.**
- **AGS10 cannot simply be substituted into the existing `sraw` field.** A different VOC sensor changes the measurement distribution and would require new data/retraining.

If a zone does not have the full legacy sensor signature, the dashboard must show the Vivayu health model as **Unavailable / insufficient compatible sensors**, not invent a result.

## Critical software compatibility rule

The saved joblib model contains a custom `GasThresholdClassifier` originally imported from `model_components.py`. Moving/refactoring that class carelessly can break unpickling.

For the hackathon, keep the original Vivayu model-related files unchanged in a legacy/reference folder and make that directory importable before loading the joblib bundle. Do not rename the legacy model class/module until after the hackathon.

---

# 4. Repository Strategy

The new repo `Shaurya002800/Vivayu-innohack` is currently essentially empty, so use a clean monorepo structure.

## Do NOT create an accidental nested Git repository

Do not simply clone `Vivayu` inside `Vivayu-innohack` and leave the inner `.git` directory. Git will treat it as an embedded repository/gitlink-like object and this becomes annoying during a hackathon.

Recommended quick approach:

```bash
git clone https://github.com/Shaurya002800/Vivayu-innohack.git
cd Vivayu-innohack

mkdir -p legacy

git clone --depth 1 https://github.com/Shaurya002800/Vivayu.git legacy/vivayu
rm -rf legacy/vivayu/.git

git add legacy/vivayu
git commit -m "vendor current Vivayu research snapshot for InnoHack"
```

Create `legacy/vivayu/UPSTREAM.md` containing:

```text
Upstream: https://github.com/Shaurya002800/Vivayu
Snapshot commit: cc8008a36838fba97f289876a49d599f5d7dea25
Purpose: preserve original Vivayu research pipeline/model for InnoHack integration.
Do not modify legacy code unless a compatibility fix is absolutely necessary.
```

## Final recommended repository tree

```text
Vivayu-innohack/
|
|-- README.md
|-- AGENTS.md
|-- .gitignore
|-- .env.example
|
|-- docs/
|   |-- CODEX_MASTER_REFERENCE.md
|   |-- STATUS.md
|   |-- HARDWARE_CONTRACT.md
|   |-- DEMO_RUNBOOK.md
|   `-- DECISIONS.md
|
|-- legacy/
|   `-- vivayu/
|       |-- data/
|       |-- models/
|       |-- reports/
|       |-- scripts/
|       `-- tests/
|
|-- backend/
|   |-- requirements.txt
|   |-- app/
|   |   |-- main.py
|   |   |-- config.py
|   |   |-- schemas.py
|   |   |-- state.py
|   |   |
|   |   |-- api/
|   |   |   |-- health.py
|   |   |   |-- zones.py
|   |   |   |-- water.py
|   |   |   |-- decisions.py
|   |   |   |-- irrigation.py
|   |   |   |-- weather.py
|   |   |   `-- simulation.py
|   |   |
|   |   |-- services/
|   |   |   |-- serial_bridge.py
|   |   |   |-- telemetry_service.py
|   |   |   |-- weather_service.py
|   |   |   |-- crop_service.py
|   |   |   |-- vivayu_health_service.py
|   |   |   |-- irrigation_need.py
|   |   |   |-- water_quality.py
|   |   |   |-- freshwater_allocator.py
|   |   |   |-- decision_engine.py
|   |   |   |-- actuation_service.py
|   |   |   |-- verification_service.py
|   |   |   `-- event_logger.py
|   |   |
|   |   |-- data/
|   |   |   |-- crop_profiles.json
|   |   |   `-- demo_scenarios.json
|   |   |
|   |   `-- db/
|   |       |-- database.py
|   |       `-- models.py
|   |
|   `-- tests/
|       |-- test_serial_protocol.py
|       |-- test_irrigation_need.py
|       |-- test_water_quality.py
|       |-- test_decision_engine.py
|       |-- test_zone_isolation.py
|       `-- test_fail_safe.py
|
|-- frontend/
|   |-- package.json
|   |-- src/
|   |   |-- app/
|   |   |-- components/
|   |   |-- lib/
|   |   `-- types/
|   `-- public/
|
|-- firmware/
|   |-- field_node/
|   |   `-- field_node.ino
|   `-- controller_node/
|       `-- controller_node.ino
|
|-- scripts/
|   |-- run_dev.sh
|   |-- seed_demo.py
|   `-- calibrate_pumps.py
|
`-- runtime/
    |-- vivayu_aqua.db
    `-- logs/
```

The `runtime/` directory should be ignored by Git except perhaps an empty `.gitkeep`.

---

# 5. High-Level System Architecture

```text
                 ZONE A FIELD NODE
         soil + environment + Vivayu sensors
                         |
                         | ESP-NOW
                         v
                 CENTRAL ESP32 / GATEWAY
                         ^
                         | ESP-NOW
                         |
                 ZONE B FIELD NODE
         soil + environment + Vivayu sensors

                         |
                         | USB serial, line-delimited JSON
                         v
                 FASTAPI BACKEND
                         |
     +-------------------+-----------------------+
     |                   |                       |
     v                   v                       v
Vivayu health       irrigation logic       weather service
research signal     + crop database        + freshwater budget
     |                   |                       |
     +-------------------+-----------------------+
                         |
                         v
                  DECISION ENGINE
                         |
          fresh / marginal / controlled blend
                         |
                         v
                  CONTROLLER COMMAND
                         |
                         v
              SOURCE PUMPS / VALVES
                         |
                         v
                    MIXING TANK
                         |
                   final TDS sensor
                         |
             approve / correct / block
                         |
                         v
                 irrigation pump
                         |
                    zone valve
                         |
                  surface drip line
                         |
                         v
                soil feedback reading
                         |
                         v
                     log event

FASTAPI <-------------------------> NEXT.JS DASHBOARD
```

---

# 6. Hardware-to-Software Contract

Software must not depend on undocumented serial text. Define a versioned JSON contract now and make firmware conform to it.

Use **one complete JSON object per serial line** at `115200` baud.

## 6.1 Field telemetry packet

Each zone must identify itself explicitly.

```json
{
  "schema_version": "1.0",
  "type": "field_telemetry",
  "node_id": "field-node-a",
  "zone_id": "A",
  "timestamp_ms": 1181072,
  "soil_moisture_raw": 2510,
  "soil_moisture_pct": 24.3,
  "temperature_c": 30.6,
  "humidity_pct": 62.4,
  "pressure_pa": 97481.0,
  "gas_resistance_ohm": 62070.0,
  "sraw": 29005,
  "battery_voltage_v": 3.91,
  "battery_pct": 74.0,
  "signal_rssi_dbm": -62
}
```

Fields that are not physically available should be `null`, never fabricated.

Example when a zone only has BME280 + soil sensor:

```json
{
  "schema_version": "1.0",
  "type": "field_telemetry",
  "node_id": "field-node-b",
  "zone_id": "B",
  "timestamp_ms": 1181082,
  "soil_moisture_raw": 2300,
  "soil_moisture_pct": 31.5,
  "temperature_c": 30.4,
  "humidity_pct": 61.9,
  "pressure_pa": 97479.0,
  "gas_resistance_ohm": null,
  "sraw": null,
  "battery_voltage_v": 3.88,
  "battery_pct": 69.0,
  "signal_rssi_dbm": -65
}
```

In that case the legacy Vivayu ML health result must be marked unavailable for Zone B.

## 6.2 Water-source telemetry

```json
{
  "schema_version": "1.0",
  "type": "water_source_telemetry",
  "source_id": "fresh",
  "tds_ppm": 220.0,
  "temperature_c": 25.5,
  "timestamp_ms": 1181090
}
```

And:

```json
{
  "schema_version": "1.0",
  "type": "water_source_telemetry",
  "source_id": "marginal",
  "tds_ppm": 820.0,
  "temperature_c": 25.7,
  "timestamp_ms": 1181100
}
```

## 6.3 Mixing-tank telemetry

```json
{
  "schema_version": "1.0",
  "type": "mix_telemetry",
  "tds_ppm": 468.0,
  "temperature_c": 25.8,
  "volume_estimate_ml": 405.0,
  "timestamp_ms": 1181200
}
```

## 6.4 Optional power telemetry

Only publish values that hardware can genuinely measure.

```json
{
  "schema_version": "1.0",
  "type": "power_telemetry",
  "solar_power_w": 7.2,
  "battery_voltage_v": 3.94,
  "battery_pct": 81.0,
  "load_current_a": 0.42,
  "timestamp_ms": 1181250
}
```

If there is no current/power sensor, do **not** show fake solar watts. Show `Not connected` in the UI.

## 6.5 Controller status packet

```json
{
  "schema_version": "1.0",
  "type": "controller_status",
  "controller_id": "irrigation-controller",
  "state": "IDLE",
  "emergency_stop": false,
  "last_command_id": null,
  "timestamp_ms": 1181300
}
```

---

# 7. Backend-to-Controller Command Contract

Use line-delimited JSON in the opposite direction too.

Every command must contain a unique `command_id` so retries do not cause duplicate irrigation.

## 7.1 Mix water

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-20260820-0001",
  "action": "MIX_WATER",
  "fresh_ml": 250,
  "marginal_ml": 150,
  "max_runtime_s": 45
}
```

## 7.2 Add correction freshwater

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-20260820-0002",
  "action": "ADD_FRESH_WATER",
  "fresh_ml": 30,
  "max_runtime_s": 15
}
```

## 7.3 Irrigate a zone

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-20260820-0003",
  "action": "IRRIGATE_ZONE",
  "zone_id": "A",
  "volume_ml": 430,
  "max_runtime_s": 60
}
```

## 7.4 Stop everything

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-20260820-stop",
  "action": "STOP_ALL"
}
```

## 7.5 Acknowledgement

Controller must reply quickly:

```json
{
  "schema_version": "1.0",
  "type": "ack",
  "command_id": "cmd-20260820-0001",
  "status": "accepted"
}
```

Then it publishes completion/fault events.

Do not make the laptop responsible for millisecond pump timing. The controller receives a volume or duration and executes locally so a serial/network delay cannot leave a pump stuck on.

---

# 8. Physical Water-Quality Setup and Two-TDS-Sensor Reality

The prototype has:

- Freshwater source tank
- Marginal/higher-TDS source tank
- Mixing tank
- Source pump A
- Source pump B
- Final irrigation pump or gravity outlet
- Zone valves

The important practical limitation: **two TDS sensors cannot continuously measure fresh source + marginal source + final mixture at three separate places at the same time.**

Use this hackathon arrangement:

### TDS sensor 1 - source characterization

At startup, use it to measure Source A and Source B sequentially. Store:

```text
fresh_tds_ppm
marginal_tds_ppm
measured_at
```

For the demo, the source tanks are stable enough that these values can be cached for the session.

### TDS sensor 2 - live final-mix verification

Keep this probe in the mixing tank. It is the authoritative safety feedback before irrigation.

The UI must show when source values were last measured. If the source quality is stale or unknown, automatic blending should be disabled or require re-characterization.

At real farm scale, source EC/TDS can be continuously measured with dedicated inline probes or through an automated sample-routing arrangement. The hackathon prototype does not need to implement that plumbing.

---

# 9. Data Model

The backend owns a single current application state plus persistent event/history records.

## 9.1 Zone configuration

```json
{
  "zone_id": "A",
  "name": "Zone A",
  "crop_id": "tomato",
  "sowing_date": "2026-07-10",
  "growth_stage_mode": "AUTO",
  "manual_growth_stage": null,
  "soil_sensor_id": "soil-a",
  "field_node_id": "field-node-a",
  "enabled": true
}
```

## 9.2 Derived zone state

```json
{
  "zone_id": "A",
  "crop_id": "tomato",
  "growth_stage": "flowering",
  "days_after_sowing": 41,
  "soil_moisture_pct": 24.3,
  "temperature_c": 30.6,
  "humidity_pct": 62.4,
  "vivayu_health": {
    "available": true,
    "risk_level": "watch",
    "pattern": "baseline_like_pattern",
    "research_only": true,
    "confidence_pct": 31.0
  },
  "telemetry_age_s": 1.4,
  "online": true
}
```

## 9.3 Water-source state

```json
{
  "fresh": {
    "tds_ppm": 220,
    "available_l": 1000,
    "last_measured_at": "2026-08-20T16:15:00+05:30"
  },
  "marginal": {
    "tds_ppm": 820,
    "available_l": 2500,
    "last_measured_at": "2026-08-20T16:16:00+05:30"
  },
  "mix": {
    "tds_ppm": 468,
    "last_measured_at": "2026-08-20T16:30:00+05:30"
  }
}
```

## 9.4 Weather state

```json
{
  "status": "LIVE",
  "rain_probability_6h_pct": 15,
  "rain_6h_mm": 0.2,
  "et0_6h_mm": 0.9,
  "temperature_max_6h_c": 33.2,
  "fetched_at": "2026-08-20T16:10:00+05:30"
}
```

## 9.5 Decision record

```json
{
  "decision_id": "dec-20260820-A-001",
  "zone_id": "A",
  "created_at": "2026-08-20T16:31:00+05:30",
  "needs_irrigation": true,
  "priority_score": 0.87,
  "requested_water_ml": 420,
  "strategy": "CONTROLLED_BLEND",
  "fresh_ml": 225,
  "marginal_ml": 195,
  "predicted_tds_ppm": 500,
  "max_allowed_tds_ppm": 500,
  "safety_target_tds_ppm": 450,
  "reasons": [
    "soil moisture below configured target",
    "low rain probability in next six hours",
    "crop is in a high-sensitivity stage",
    "freshwater budget is constrained",
    "marginal source cannot be used alone"
  ],
  "warnings": [
    "crop salinity threshold is literature/config derived, not a universal safety guarantee"
  ]
}
```

---

# 10. Crop Configuration Database

Do not make crop knowledge an opaque ML model during the hackathon.

Create `backend/app/data/crop_profiles.json`.

Each crop profile should contain:

```json
{
  "id": "tomato",
  "display_name": "Tomato",
  "stage_durations_days": {
    "initial": 30,
    "development": 40,
    "mid": 40,
    "late": 25
  },
  "stages": {
    "initial": {
      "kc": 0.60,
      "water_sensitivity_weight": 0.8
    },
    "development": {
      "kc": 0.85,
      "water_sensitivity_weight": 1.0
    },
    "mid": {
      "kc": 1.15,
      "water_sensitivity_weight": 1.25
    },
    "late": {
      "kc": 0.80,
      "water_sensitivity_weight": 0.9
    }
  },
  "prototype": {
    "target_soil_moisture_pct": 45,
    "critical_soil_moisture_pct": 25,
    "max_irrigation_tds_ppm": 500
  },
  "sources": [
    {
      "name": "FAO / verified agronomic source",
      "url": "REPLACE_WITH_VERIFIED_SOURCE_URL"
    }
  ],
  "notes": "Prototype moisture/TDS thresholds must be verified before claiming agronomic validity."
}
```

The numbers above are **example configuration values for software scaffolding**, not a claim that they are universal tomato thresholds. Before judging, replace/verify the demo crop values against the chosen source and preserve the source URL in the profile.

## Growth-stage calculation

Farmer enters crop + sowing date once.

Backend calculates:

```text
days_after_sowing = today - sowing_date
```

Then walks through `stage_durations_days` to estimate the current stage.

Because real crop development varies, the UI must allow a **manual stage override**.

---

# 11. Weather Service

Use a simple weather adapter. For the hackathon, Open-Meteo is suitable because the project needs forecast values such as rain and reference evapotranspiration.

Required derived fields:

- rain probability for next 6 hours;
- total expected precipitation next 6 hours;
- summed/reference ET0 next 6 hours;
- forecast temperature as supporting context.

Implementation requirements:

1. Weather service accepts farm latitude/longitude from environment/config.
2. Cache a successful response for 15-30 minutes.
3. Never call the weather API on every dashboard refresh.
4. If the API fails, use the last cached response and mark it `CACHED`.
5. If there is no cached response, mark weather `OFFLINE` and continue local irrigation logic with a conservative fallback.
6. Weather failure must not crash the dashboard.

Example adapter interface:

```python
class WeatherService:
    def get_current_forecast(self) -> WeatherSnapshot:
        ...
```

---

# 12. Existing Vivayu ML Integration

Create `vivayu_health_service.py` as a wrapper around the legacy repo.

## 12.1 Add legacy scripts directory to Python import path

At service startup:

```python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCRIPTS = ROOT / "legacy" / "vivayu" / "scripts"
if str(LEGACY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(LEGACY_SCRIPTS))

from vivayu_runtime import RollingPredictor, ReadingValidationError
```

Load the model from:

```text
legacy/vivayu/models/vivayu_research_candidate.joblib
```

## 12.2 One predictor PER ZONE

The current `RollingPredictor` stores a deque internally. Therefore do **not** share one instance across Zone A and Zone B.

Correct:

```python
predictors = {
    "A": RollingPredictor(MODEL_PATH),
    "B": RollingPredictor(MODEL_PATH),
}
```

Wrong:

```python
predictor = RollingPredictor(MODEL_PATH)
# then feed A, B, A, B into the same five-reading window
```

That would create scientifically meaningless mixed-zone windows.

## 12.3 Compatibility check before prediction

Only feed a zone into the legacy model when all required fields exist and are compatible:

```text
timestamp_ms
temperature_c
humidity_pct
pressure_pa
gas_resistance_ohm
sraw
```

If not:

```json
{
  "available": false,
  "reason": "legacy_vivayu_sensor_signature_incomplete",
  "research_only": true
}
```

## 12.4 Preserve original semantics

The legacy runtime returns a monitoring pattern/risk level after five readings. Preserve its wording.

Do not relabel it as:

- confirmed disease;
- crop diagnosis;
- treatment recommendation;
- calibrated field confidence.

The current code explicitly calls its confidence a **decision separation only**, not calibrated field confidence.

## 12.5 How Aqua may use this result

For the hackathon:

- Show it on the dashboard.
- Include it in the written explanation/context.
- Log it alongside irrigation decisions.
- Do **not** use it as a hard actuator trigger.

If later experimentation establishes a validated link between a health signal and irrigation priority, that can become a future version.

---

# 13. Soil Moisture Handling

Each soil sensor must be calibrated independently.

Firmware should send both:

- raw ADC;
- calibrated percentage.

Keep calibration constants in firmware or a backend config file:

```json
{
  "sensor_id": "soil-a",
  "dry_raw": 3150,
  "wet_raw": 1450
}
```

Convert approximately:

```python
pct = 100 * (raw - dry_raw) / (wet_raw - dry_raw)
pct = max(0, min(100, pct))
```

Use a median or rolling filter rather than one raw sample.

Do not claim this percentage is universal volumetric water content unless the sensor/soil has been calibrated for that purpose. In the dashboard call it **calibrated soil-moisture index (%)** or **prototype soil moisture (%)**.

---

# 14. Irrigation-Water Requirement Engine

Do not start with a neural network. The current hackathon does not have a validated multi-crop irrigation training dataset.

Use a transparent hybrid calculation.

## 14.1 Demo soil-response calibration

For each zone, determine how much water changes the prototype moisture reading.

Example:

```text
Before irrigation: 24%
Add: 100 mL
After stabilization: 29%
Observed change: +5 percentage points
ml_per_moisture_point = 100 / 5 = 20 mL/%
```

Store per zone:

```json
{
  "zone_id": "A",
  "ml_per_moisture_point": 20.0,
  "calibration_confidence": "prototype"
}
```

## 14.2 Base need

```python
def base_water_need_ml(moisture_pct, target_pct, ml_per_point):
    deficit = max(0.0, target_pct - moisture_pct)
    return deficit * ml_per_point
```

## 14.3 Weather adjustment

Keep this configurable and explainable.

Example policy:

```text
if strong rain expected soon and zone is not critical:
    reduce/defer irrigation

if ET0 is high:
    increase urgency slightly

if soil moisture is below critical threshold:
    critical safety takes priority over forecast rain
```

Do not bury these rules in magic constants. Put them in `config.py` and include the effect in decision reasons.

## 14.4 Growth-stage adjustment

The crop profile provides a stage sensitivity weight. Apply it to urgency/priority, not blindly to exact water volume unless the crop model supports that.

---

# 15. Multi-Zone Priority and Freshwater Allocation

The system has Zone A and Zone B. Both may request irrigation at the same time.

Freshwater may be insufficient.

Create a normalized priority score from explainable factors:

```text
soil deficit severity
+ whether below critical moisture
+ crop-stage sensitivity
+ ET0 / near-term atmospheric demand
+ time since last irrigation
```

The existing Vivayu ML signal can be displayed as supporting context but should not dominate or directly trigger actuation.

Example conceptual score:

```python
priority = (
    0.50 * soil_deficit_score
    + 0.20 * stage_sensitivity_score
    + 0.15 * et0_score
    + 0.15 * time_since_irrigation_score
)

if below_critical_moisture:
    priority = min(1.0, priority + 0.25)
```

All weights belong in configuration.

## Freshwater allocation rule

When freshwater is insufficient for all requested blends:

1. Give minimum survival allocation to critically dry zones where possible.
2. Prefer scarce freshwater for higher-priority and more salinity-sensitive crop/stage configurations.
3. Let lower-priority/tolerant zones use more marginal water when their quality constraint allows it.
4. If no safe blend exists, reduce/defer that irrigation rather than exceed the configured TDS limit.
5. Never silently exceed available freshwater.

The dashboard should make this visible as a **Freshwater Bank**.

---

# 16. Water-Quality / TDS Engine

The hackathon prototype uses TDS in ppm as a practical low-cost water-quality proxy.

All TDS thresholds must remain configurable.

## 16.1 Inputs

```text
required_water_ml
fresh_tds_ppm
marginal_tds_ppm
fresh_available_ml
marginal_available_ml
crop_max_tds_ppm
safety_margin
```

## 16.2 Three operating modes

### Fresh only

Use when:

- marginal water is too saline to blend usefully;
- crop/stage config requires high-quality water;
- user forces fresh-only mode;
- mixture verification repeatedly fails.

### Marginal only

Use when:

```text
marginal_tds <= configured safe target
```

and marginal water is available.

### Controlled blend

Use when:

```text
fresh_tds < target_tds < marginal_tds
```

and enough freshwater exists to create an acceptable mix.

## 16.3 Weighted mixing equation

For fresh volume `Vf`, marginal volume `Vm`, source TDS `Tf` and `Tm`:

```text
Tmix = (Vf * Tf + Vm * Tm) / (Vf + Vm)
```

If the target final TDS is `Ttarget`, the maximum marginal fraction is approximately:

```text
marginal_fraction = (Ttarget - Tf) / (Tm - Tf)
```

Clamp to `[0, 1]`.

Use a **safety target below the configured maximum** to allow for sensor and pump error.

Example:

```text
configured maximum = 500 ppm
safety target = 450 ppm
```

Do not intentionally mix exactly to the hard limit.

## 16.4 Required water + source availability

The mixing function must also respect:

```text
fresh_available
marginal_available
```

Return a structured error/partial decision when resources are insufficient.

Example result:

```json
{
  "strategy": "CONTROLLED_BLEND",
  "fresh_ml": 245,
  "marginal_ml": 175,
  "predicted_tds_ppm": 448,
  "requested_total_ml": 420,
  "deliverable_total_ml": 420,
  "safe": true
}
```

---

# 17. Post-Mix TDS Feedback Loop

This is a hero engineering feature.

After the source pumps create the mix:

1. Wait a short configured settling/mixing interval.
2. Read several TDS samples.
3. Filter them (median recommended).
4. Compare measured TDS with the configured maximum/safety target.

## If measured TDS is acceptable

```text
APPROVE -> irrigation may start
```

## If measured TDS is too high

```text
BLOCK irrigation
-> calculate a small freshwater correction
-> add freshwater
-> mix/wait
-> re-measure
```

Limit correction attempts, for example 3.

If still too high:

```text
FAULT_TDS_UNSAFE
-> pumps/valves off
-> require operator attention
```

## If measured TDS is much LOWER than predicted

Do not immediately add more marginal water and oscillate around the target during the hackathon.

Instead:

- accept the safe water;
- log that freshwater was overused;
- adjust the next decision/calibration if desired.

Safety is more important than achieving an exact ratio.

---

# 18. Pump Calibration and Actuation

Do not assume two identical mini pumps deliver identical flow.

Calibrate each pump independently with at least 3 trials.

Example config:

```json
{
  "fresh_source_pump": {
    "flow_ml_per_s": 18.2,
    "max_continuous_runtime_s": 45
  },
  "marginal_source_pump": {
    "flow_ml_per_s": 15.4,
    "max_continuous_runtime_s": 45
  },
  "irrigation_pump": {
    "flow_ml_per_s": 17.1,
    "max_continuous_runtime_s": 60
  }
}
```

The controller converts requested volume to runtime locally:

```text
runtime_s = requested_ml / calibrated_flow_ml_per_s
```

All pumps must be OFF on boot/reset.

Add hard maximum runtime protection in firmware independent of backend logic.

---

# 19. Irrigation State Machine

Do not allow arbitrary overlapping commands.

Use this state machine:

```text
IDLE
  |
  v
SENSING
  |
  v
DECIDING
  |
  +---- no irrigation needed ----> IDLE
  |
  v
MIXING
  |
  v
VERIFYING_TDS
  |
  +---- unsafe after retries ----> FAULT
  |
  v
IRRIGATING
  |
  v
VERIFYING_SOIL
  |
  v
COMPLETE
  |
  v
IDLE
```

Additional states:

```text
PAUSED
EMERGENCY_STOP
CONTROLLER_OFFLINE
FIELD_NODE_OFFLINE
FAULT_TDS_UNSAFE
FAULT_ACTUATION_TIMEOUT
FAULT_SENSOR_INVALID
```

Only valid transitions are allowed.

---

# 20. Soil Feedback and Adaptive Field Response

Before irrigation, store:

```text
moisture_before
```

After irrigation, wait a configurable demo stabilization interval and store:

```text
moisture_after
```

Calculate:

```text
delta_moisture = moisture_after - moisture_before
```

If water was delivered but the soil reading barely changes, report:

```text
ABNORMAL_IRRIGATION_RESPONSE
```

Do not claim a specific fault unless hardware can distinguish it. Possible causes include probe location, runoff, tubing/pump issue, or sensor error.

## Adaptive zone calibration

If `delta_moisture` is valid and positive:

```text
observed_ml_per_point = delivered_ml / delta_moisture
```

Update slowly with an exponential moving average:

```text
new = 0.8 * old + 0.2 * observed
```

This lets each demo zone develop a different water-response coefficient.

Do not call this a full soil hydraulic ML model. Call it **adaptive field-response calibration**.

---

# 21. Backend Architecture

Use FastAPI for the new backend instead of extending the legacy inline-HTML server.

The legacy dashboard can remain in `legacy/vivayu` for reference/debugging.

## `main.py`

Responsibilities:

- instantiate app;
- configure CORS for local frontend;
- startup/shutdown services;
- register routers;
- start serial bridge/background telemetry worker;
- expose WebSocket or polling state endpoint.

## `state.py`

Maintain current in-memory state with a lock/async-safe access strategy.

Persistent history goes to SQLite.

## `serial_bridge.py`

Responsibilities:

- discover/open configured serial port;
- reconnect on disconnect;
- read one line at a time;
- parse JSON;
- validate schema/version;
- dispatch by `type`;
- write commands;
- track ACK timeouts;
- never crash the whole backend because of one malformed line.

## `telemetry_service.py`

Responsibilities:

- update latest zone values;
- track telemetry age;
- mark nodes offline after timeout;
- maintain short history buffers for charts;
- feed compatible readings to the correct zone-specific Vivayu predictor.

## `decision_engine.py`

Orchestrates:

1. zone config/crop stage;
2. soil state;
3. weather;
4. irrigation need;
5. zone priority;
6. freshwater budget;
7. water-quality strategy;
8. reasons/warnings;
9. safety validation.

It should not directly toggle pumps. It returns a `Decision` object.

## `actuation_service.py`

Responsibilities:

- execute a previously approved decision;
- send commands to controller;
- wait for ACK/event with timeout;
- manage state-machine transition;
- emergency stop;
- never execute stale decisions.

## `verification_service.py`

Responsibilities:

- TDS verification/correction loop;
- post-irrigation soil response;
- adaptive response update;
- final result record.

---

# 22. Suggested Backend API

Prefix all endpoints with `/api/v1`.

## Health/system

```text
GET /api/v1/health
GET /api/v1/state
GET /api/v1/events?limit=100
```

## Zones

```text
GET  /api/v1/zones
GET  /api/v1/zones/{zone_id}
PUT  /api/v1/zones/{zone_id}/config
POST /api/v1/zones/{zone_id}/stage-override
```

## Water

```text
GET  /api/v1/water
PUT  /api/v1/water/freshwater-budget
POST /api/v1/water/source-characterization
GET  /api/v1/water/mix-status
```

## Weather

```text
GET  /api/v1/weather
POST /api/v1/weather/refresh
```

## Decisions

```text
POST /api/v1/zones/{zone_id}/decision
POST /api/v1/decisions/all
GET  /api/v1/decisions/latest
```

## Actuation

```text
POST /api/v1/decisions/{decision_id}/execute
POST /api/v1/system/stop-all
```

## Simulation

```text
GET  /api/v1/simulation/scenarios
POST /api/v1/simulation/activate
POST /api/v1/simulation/deactivate
```

## Live updates

Preferred after the basic app works:

```text
WebSocket /api/v1/ws
```

For first implementation, one-second frontend polling of `/state` is acceptable and safer. Upgrade to WebSocket only after core logic is stable.

---

# 23. SQLite Persistence

Use SQLite because this is local/offline-friendly and requires no infrastructure.

Persist at minimum:

## `zone_config`

```text
zone_id
crop_id
sowing_date
manual_stage
updated_at
```

## `telemetry_log`

```text
id
timestamp
zone_id
soil_moisture_pct
temperature_c
humidity_pct
pressure_pa
gas_resistance_ohm
sraw
battery_pct
```

Do not insert every extremely high-frequency raw packet forever. For the hackathon, 1 row every 2-5 seconds is enough.

## `water_source_log`

```text
timestamp
source_id
tds_ppm
temperature_c
```

## `decisions`

Store the full decision JSON.

## `irrigation_events`

```text
event_id
decision_id
zone_id
started_at
completed_at
requested_ml
fresh_ml
marginal_ml
predicted_tds
measured_tds
moisture_before
moisture_after
result
failure_reason
```

## `system_events`

Structured event/fault log.

---

# 24. Dashboard Requirements

Build a new modern dashboard in `frontend/` and pull data from the new backend.

The dashboard's job is **not** to dump sensor values. It must make the decision understandable to a judge in seconds.

## 24.1 Header

Show:

```text
VIVAYU Aqua
Scarcity-aware, water-quality-aware irrigation
LIVE / SIMULATION badge
Controller status
Emergency STOP button
```

The simulation badge must be visually obvious when enabled.

## 24.2 Hero cards

Show:

```text
Freshwater remaining
Marginal water available
Current mixed-water TDS
Rain next 6h
Solar/battery status
```

If power measurement hardware is unavailable, show `Not connected`; never fabricate a watt value.

## 24.3 Zone A and Zone B cards

Each zone card must be independent and contain:

```text
Zone name
Crop
Estimated/manual growth stage
Days after sowing
Soil moisture
Temperature
Humidity
Node online/offline
Vivayu health signal (research-only)
Last irrigation
Water requirement
Priority
Current decision
```

Example:

```text
ZONE A - TOMATO
Stage: Flowering
Moisture: 23% - Critical
Temperature: 31.2 C
Humidity: 58%
Vivayu: Watch (research-only)
Water need: 420 mL
Priority: High
Decision: Controlled Blend
```

## 24.4 Water-quality panel

```text
Fresh source TDS
Marginal source TDS
Source measurement age
Configured crop TDS limit
Safety target
Predicted mix TDS
Measured mix TDS
Verification state
```

## 24.5 Decision explanation panel

Display the exact reasons returned by backend.

Example:

```text
Why Zone A is being irrigated:
- moisture below target
- currently below critical threshold
- no meaningful rain expected in next 6 h
- flowering stage has high priority

Why controlled blend:
- marginal water alone exceeds configured limit
- freshwater is scarce
- calculated blend stays inside safety target
```

## 24.6 State-machine timeline

```text
SENSE -> DECIDE -> MIX -> VERIFY TDS -> IRRIGATE -> VERIFY SOIL
```

Highlight the current active step.

## 24.7 Freshwater Bank

Show:

```text
Freshwater at start
Freshwater used today/demo
Freshwater remaining
Freshwater substituted by marginal water
```

Only call it `water saved` if you have a real baseline comparison. Otherwise call it **freshwater substituted/avoided in this run**.

## 24.8 Live charts

Small charts only:

- Zone A moisture over time;
- Zone B moisture over time;
- final TDS over time;
- optional battery/solar telemetry.

Do not overload the main screen with research plots from the legacy repo.

## 24.9 Manual controls

Keep behind an "Advanced / Manual" section:

```text
Refresh weather
Re-characterize water sources
Run decision only
Execute approved decision
Stop all
Simulation scenario selector
```

Manual pump toggles should be restricted and include automatic timeouts.

---

# 25. Frontend Data Types

Create TypeScript types matching backend schemas.

Example:

```ts
export type ZoneId = "A" | "B";

export interface ZoneState {
  zone_id: ZoneId;
  crop_id: string;
  growth_stage: string | null;
  days_after_sowing: number | null;
  soil_moisture_pct: number | null;
  temperature_c: number | null;
  humidity_pct: number | null;
  online: boolean;
  telemetry_age_s: number | null;
  vivayu_health: VivayuHealthState;
}

export interface VivayuHealthState {
  available: boolean;
  risk_level?: "low" | "watch" | "elevated" | "high";
  pattern?: string;
  confidence_pct?: number;
  research_only: true;
  reason?: string;
}
```

Do not use `any` for core domain state.

---

# 26. Simulation Mode - Mandatory

Hardware integration must not block software development.

Create a simulation provider that produces the exact same schemas as the live serial provider.

At startup:

```text
DATA_MODE=simulation
```

or:

```text
DATA_MODE=hardware
```

Never mix fake/live values silently.

Required scenarios:

## Scenario 1 - Zone A critical

```text
Zone A moisture: 22%
Zone B moisture: 38%
Low rain forecast
Fresh TDS: 220 ppm
Marginal TDS: 820 ppm
Freshwater limited
```

Expected: A high priority, blend or fresh allocation depending crop limit.

## Scenario 2 - Rain soon

Moderately dry zone + high rain probability.

Expected: reduce/defer irrigation unless below critical threshold.

## Scenario 3 - TDS correction

Backend predicts acceptable blend; simulated final TDS reports too high.

Expected: irrigation blocked, fresh correction command generated, re-check, then approve.

## Scenario 4 - Freshwater shortage

Both zones need water but freshwater budget is lower than combined fresh requirements.

Expected: priority allocator preserves freshwater for higher-priority/sensitive zone.

## Scenario 5 - Sensor offline

Zone A telemetry becomes stale.

Expected: Zone A automatic actuation blocked, dashboard clearly says offline.

## Scenario 6 - Legacy ML unavailable

Zone B lacks gas resistance/SGP data.

Expected: irrigation still works from soil/weather/crop logic; health model shows unavailable.

---

# 27. Safety and Fail-Safe Rules

These are P0, not optional polish.

1. Pumps OFF on boot.
2. Controller has a maximum runtime per pump.
3. Backend has command timeout.
4. Every command has `command_id`.
5. Repeated identical command ID must not execute twice.
6. Stale field telemetry blocks automatic irrigation for that zone.
7. Invalid soil reading blocks automatic irrigation for that zone.
8. Unknown crop profile blocks automatic blend calculation.
9. Unknown/stale source TDS blocks automatic controlled blending.
10. Final mix TDS above configured maximum blocks irrigation.
11. TDS correction loop has a maximum number of attempts.
12. Emergency STOP immediately disables pumps/valves.
13. Controller disconnect during actuation must cause local timeout shutdown.
14. Weather API failure must not crash local control.
15. The UI must never show `SAFE` based on a missing TDS reading.
16. Simulation mode must never send real pump commands unless an explicit developer override is enabled.

---

# 28. Error and Status Vocabulary

Use stable machine codes plus readable descriptions.

Examples:

```text
OK
WAITING_FOR_TELEMETRY
ZONE_OFFLINE
SOIL_SENSOR_INVALID
LEGACY_ML_UNAVAILABLE
WEATHER_OFFLINE
SOURCE_TDS_UNKNOWN
MIX_TDS_UNSAFE
MIX_CORRECTION_FAILED
FRESHWATER_INSUFFICIENT
MARGINAL_WATER_INSUFFICIENT
NO_SAFE_WATER_STRATEGY
CONTROLLER_OFFLINE
COMMAND_ACK_TIMEOUT
ACTUATION_TIMEOUT
ABNORMAL_IRRIGATION_RESPONSE
EMERGENCY_STOP
```

Do not use random strings in different parts of the code.

---

# 29. Testing Requirements

Every core domain function needs tests before hardware integration.

## 29.1 Water-quality tests

Test:

1. marginal water already below target -> `MARGINAL_ONLY`;
2. controlled blend calculated correctly;
3. fresh water itself above limit -> `NO_SAFE_WATER_STRATEGY`;
4. equal source TDS values -> no divide-by-zero;
5. insufficient freshwater;
6. insufficient marginal water;
7. safety margin below hard maximum;
8. final measured TDS high -> correction required;
9. final measured TDS safe -> irrigation approved;
10. correction retries exhausted -> fault.

## 29.2 Zone isolation tests

Feed A and B different sensor streams.

Assert:

- A telemetry never overwrites B;
- B crop never appears in A;
- A rolling Vivayu window contains only A readings;
- B rolling window contains only B readings;
- irrigation events persist correct zone ID.

## 29.3 Fail-safe tests

- stale zone -> no actuation;
- controller offline -> no actuation;
- TDS missing -> no blend actuation;
- simulation mode -> no hardware actuation;
- duplicate command ID -> exactly-once behavior at controller service level.

## 29.4 Decision-engine tests

- critical dry beats moderate dry;
- rain suppresses moderate irrigation;
- critical dryness is not blindly skipped because rain is forecast;
- fresh shortage prioritizes according to configured priority;
- every result has `reasons`.

## 29.5 Legacy ML wrapper tests

- full compatible reading reaches correct predictor;
- missing gas resistance -> unavailable, not crash;
- A/B predictor windows remain isolated;
- legacy result remains `research_only`.

## 29.6 End-to-end simulation test

One automated test should run:

```text
telemetry -> decision -> mix command -> simulated measured TDS -> irrigation -> soil feedback -> completed event
```

and assert final event is `COMPLETE`.

---

# 30. Development Environment

## Backend

Create `backend/requirements.txt` with a minimal stack such as:

```text
fastapi
uvicorn[standard]
pydantic
pyserial
httpx
joblib
numpy
pandas
scikit-learn==1.5.2
```

Pin `scikit-learn==1.5.2` to match the current Vivayu repo unless the model is regenerated and compatibility is verified.

For SQLite, either use standard `sqlite3` for speed/simplicity or add SQLAlchemy if Codex can keep the code clean. Do not add a cloud DB during the hackathon.

## Frontend

Use:

```text
Next.js
TypeScript
Tailwind CSS
```

Optional only if helpful:

```text
Recharts for simple charts
```

Do not add a heavy UI/design system unless it genuinely speeds development.

## Environment file

`.env.example`:

```text
DATA_MODE=simulation
SERIAL_PORT=/dev/cu.usbserial-0001
SERIAL_BAUD=115200
FARM_LATITUDE=12.9692
FARM_LONGITUDE=79.1559
WEATHER_CACHE_MINUTES=20
ZONE_STALE_SECONDS=10
TDS_SOURCE_STALE_MINUTES=240
MAX_TDS_CORRECTION_ATTEMPTS=3
DATABASE_URL=sqlite:///../runtime/vivayu_aqua.db
```

Do not commit real secrets.

---

# 31. Implementation Milestones - Exact Order

Codex must implement in this order.

## Milestone 1 - Repository scaffold

Create the folders, `.gitignore`, `AGENTS.md`, `.env.example`, backend app, frontend app, docs and test structure.

Acceptance:

- backend starts;
- frontend starts;
- `/api/v1/health` returns 200;
- frontend can reach backend;
- tests can run.

## Milestone 2 - Simulation state + two independent zones

Implement current state, zone configs, crop selection, sowing date, manual stage override and simulation telemetry.

Acceptance:

- Zone A and B show independent values;
- crop/stage config persists;
- dashboard visibly says `SIMULATION`.

## Milestone 3 - Crop + weather service

Implement crop profiles, stage estimation and weather adapter/cache.

Acceptance:

- stage derived from sowing date;
- manual override works;
- weather failure falls back cleanly;
- next-six-hour fields appear in backend state.

## Milestone 4 - Irrigation-need engine

Implement soil-response configuration, base water need, weather adjustment, critical-moisture override and decision reasons.

Acceptance:

- each zone returns water need and reasons;
- critical vs moderate behavior tested.

## Milestone 5 - TDS / water-quality engine

Implement FRESH_ONLY, MARGINAL_ONLY, CONTROLLED_BLEND, weighted TDS, source availability and safety margin.

Acceptance:

- unit tests pass for all water-quality cases;
- dashboard displays predicted mix and source volumes.

## Milestone 6 - Multi-zone freshwater allocation

Implement freshwater bank and priority allocation.

Acceptance:

- when both zones need more fresh water than available, system produces deterministic explainable allocation;
- available freshwater never becomes negative.

## Milestone 7 - Vivayu legacy ML wrapper

Integrate original `RollingPredictor` without modifying legacy model semantics.

Acceptance:

- separate predictor per zone;
- compatible zone returns five-reading result;
- incompatible zone shows unavailable;
- no irrigation decision depends on model output.

## Milestone 8 - Dashboard polish

Build final judge-facing view.

Acceptance:

- water budget understood in <10 seconds;
- two zone states visible;
- selected water strategy + reason visible;
- predicted vs measured TDS visible;
- state-machine stage visible;
- Vivayu health labelled research-only.

## Milestone 9 - Serial adapter

Implement line-delimited JSON reader/writer and reconnect behavior.

Acceptance:

- hardware packets update the same state used by simulation;
- malformed lines do not crash backend;
- stale node detection works.

## Milestone 10 - Controller command + ACK protocol

Implement command IDs, ACK, timeout and `STOP_ALL`.

Acceptance:

- backend can send one command and observe ACK;
- duplicate IDs handled safely;
- controller timeout leaves pump off.

## Milestone 11 - TDS feedback state machine

Implement MIX -> VERIFY_TDS -> correction/retry -> approve/fault.

Acceptance:

- simulated high TDS triggers fresh correction;
- irrigation cannot start while mix is unsafe.

## Milestone 12 - Irrigation + post-soil verification

Implement zone irrigation event, before/after moisture, abnormal response and adaptive field coefficient.

Acceptance:

- one complete end-to-end physical or simulated run reaches COMPLETE;
- event saved to SQLite;
- dashboard shows before/after.

## Milestone 13 - Hardware and demo hardening

No new architecture here.

Acceptance:

- 5 consecutive end-to-end demo runs;
- no crash;
- no accidental pump overlap;
- STOP button works;
- hardware disconnect is recoverable;
- simulation fallback still works.

---

# 32. Immediate P0 vs Later Features

## P0 - must work to win

- two independent zones;
- soil moisture;
- crop + sowing date + stage;
- weather/rain/ET0 context;
- freshwater budget;
- source TDS values;
- water strategy selection;
- controlled blend calculation;
- final mixed TDS verification;
- actuation state machine;
- post-irrigation soil feedback;
- clean dashboard;
- simulation mode;
- fail-safe stop;
- existing Vivayu health signal shown where compatible.

## P1 - if time permits

- live solar/battery telemetry with actual sensor hardware;
- historical charts;
- load-cell/flow verification;
- better adaptive pump-flow calibration;
- CSV export.

## P2 - do not sacrifice P0 for these

- GenAI chatbot;
- voice assistant;
- blockchain;
- mobile app;
- cloud deployment;
- complex deep learning;
- disease diagnosis claims;
- dozens of crop profiles;
- digital twin visualization.

---

# 33. Dashboard Demo Scenario to Build Around

Prepare one deterministic scenario that can also be reproduced in simulation.

Example:

```text
Zone A
Crop: Tomato
Stage: high-sensitivity stage
Soil moisture: 22%

Zone B
Crop: another configured crop/stage
Soil moisture: 34%

Fresh source: 220 ppm
Marginal source: 820 ppm
Freshwater available: limited
Rain next 6 h: low
```

Expected dashboard behavior:

1. Both zones visible.
2. Zone A becomes higher priority.
3. Water requirement calculated.
4. Freshwater bank shown.
5. System chooses one of the three water modes.
6. For blend: predicted fresh/marginal volumes shown.
7. Controller mixes.
8. TDS verification appears live.
9. If a deliberately high TDS reading is produced, irrigation is blocked and fresh correction occurs.
10. Once acceptable, irrigation starts.
11. Soil moisture after irrigation is compared with before.
12. Event becomes COMPLETE and freshwater budget updates.

---

# 34. Judge-Facing Terminology

Use these terms consistently in UI/code/docs:

Preferred:

```text
marginal-quality water
higher-TDS water
water-quality-aware irrigation
freshwater bank
configured/literature-derived salinity constraint
controlled blend
final water-quality verification
adaptive field-response calibration
Vivayu research health signal
```

Avoid:

```text
dirty water
AI knows exact disease
TDS proves water is safe for every crop
100% safe
universal salinity threshold
our model diagnoses infection
we save X% water (unless measured against a baseline)
```

---

# 35. Important Scientific/Engineering Boundaries

Codex should preserve these boundaries in labels and comments.

1. TDS is a proxy for overall dissolved solids/salinity, not identification of individual ions.
2. Crop salinity response also depends on soil, drainage, climate, long-term salt accumulation and management.
3. The hackathon mixing model controls **incoming irrigation-water quality**; it does not by itself prove long-term root-zone salinity safety.
4. Long-term production deployment should include soil/root-zone salinity monitoring or a validated salt-balance model.
5. The existing Vivayu model is research-only and based on a small tomato experiment.
6. SGP40/AGS10/BME sensors must not be interchanged inside the ML pipeline without compatibility evidence/retraining.
7. Low-cost TDS readings require calibration and have a limited range; prototype logic must not pretend otherwise.
8. Soil-moisture percentages are sensor/soil-calibrated prototype values unless independently validated.

---

# 36. Codex Coding Rules

1. Use typed Pydantic models for API payloads.
2. Use TypeScript types in frontend.
3. Keep decision logic in pure functions where possible so it is easily testable.
4. Keep hardware I/O behind adapters/interfaces.
5. Simulation and hardware adapters must emit the same domain schemas.
6. Never access serial hardware directly from React.
7. Never put crop logic in UI components.
8. Never put pump safety only in backend; firmware needs independent timeout protection.
9. Use structured logging.
10. Store timestamps in ISO 8601 with timezone for backend records.
11. Keep units in field names (`_ml`, `_l`, `_ppm`, `_pct`, `_c`, `_w`).
12. Never mix litres and millilitres implicitly.
13. Keep a single canonical state enum.
14. Every decision object must contain `reasons` and `warnings`.
15. Never silently substitute missing sensors with zero.
16. For legacy ML, preserve exact required feature names.
17. Add tests before refactoring a working hardware path.
18. Avoid introducing infrastructure not needed for the hackathon.

---

# 37. `docs/STATUS.md` Template

Codex should update this after each milestone.

```markdown
# Implementation Status

## Current milestone
Milestone X - ...

## Working
- [x] ...

## Not working / blocked
- [ ] ...

## Hardware assumptions
- ...

## Tests
- Backend: X passed
- Frontend: build/lint status

## Last end-to-end run
- Mode: simulation / hardware
- Result: ...
- Failure: ...

## Next exact task
1. ...
2. ...
```

---

# 38. Recommended `AGENTS.md`

Place a short instruction file at repository root containing at least:

```markdown
# VIVAYU Aqua Codex Instructions

Read `docs/CODEX_MASTER_REFERENCE.md` before implementing anything.
Treat it as the source of truth.

Work milestone-by-milestone and update `docs/STATUS.md` after every milestone.
Do not change legacy Vivayu ML semantics.
Do not use legacy health output as an actuator trigger.
Do not fabricate live telemetry.
Simulation mode must be clearly labelled.
Pumps default OFF and all actuation must be fail-safe.
Zone A and Zone B must remain isolated in telemetry, ML windows, decisions and history.
Run tests after each meaningful change.
Do not start P1/P2 features until all P0 acceptance criteria pass.
```

---

# 39. Minimum README Setup Commands

The final repo README should eventually provide something close to:

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Simulation should be the default developer mode so the dashboard works without hardware.

For hardware mode:

```text
DATA_MODE=hardware
SERIAL_PORT=<actual-port>
```

---

# 40. Final Acceptance Checklist

Before calling the system complete, all items below must be true.

## Repository

- [ ] Existing Vivayu is preserved under `legacy/vivayu` without a nested `.git`.
- [ ] Upstream commit/reference documented.
- [ ] New backend/frontend/firmware are cleanly separated.

## Two zones

- [ ] Zone A and Zone B have independent config and telemetry.
- [ ] Zone A and B do not share ML windows.
- [ ] Missing sensors do not create fake values.

## Vivayu

- [ ] Existing model loads successfully.
- [ ] Model is only enabled for compatible sensor signature.
- [ ] UI labels result research-only.
- [ ] ML output does not directly command irrigation.

## Crop/weather

- [ ] Farmer can set crop and sowing date per zone.
- [ ] Growth stage is estimated and can be overridden.
- [ ] Crop profile records source information.
- [ ] Weather is cached and gracefully handles offline mode.

## Water

- [ ] Fresh and marginal source TDS are stored with measurement timestamp.
- [ ] Freshwater budget is tracked.
- [ ] FRESH_ONLY works.
- [ ] MARGINAL_ONLY works.
- [ ] CONTROLLED_BLEND works.
- [ ] Weighted predicted TDS is correct.
- [ ] Source availability is enforced.

## TDS feedback

- [ ] Final mixed TDS is measured.
- [ ] Unsafe mix blocks irrigation.
- [ ] Fresh correction works.
- [ ] Correction attempts are limited.
- [ ] Missing TDS never displays SAFE.

## Actuation

- [ ] Pumps OFF at boot.
- [ ] Local max runtime exists.
- [ ] Command IDs + ACK exist.
- [ ] STOP_ALL works.
- [ ] Controller disconnect fails safe.

## Feedback

- [ ] Moisture before is recorded.
- [ ] Moisture after is recorded.
- [ ] Abnormal response is detectable.
- [ ] Adaptive field coefficient updates conservatively.

## Dashboard

- [ ] Freshwater bank visible.
- [ ] Both zone cards visible.
- [ ] Weather visible.
- [ ] Water strategy visible.
- [ ] Predicted and measured TDS visible.
- [ ] Decision reasons visible.
- [ ] State machine visible.
- [ ] Live/simulation mode obvious.
- [ ] Emergency stop obvious.

## Testing/demo

- [ ] Backend unit tests pass.
- [ ] End-to-end simulation passes.
- [ ] Five consecutive demo runs succeed or failures are understood.
- [ ] No unverified percentage-saving claims are shown.

---

# 41. Final One-Line Definition for the Codebase

> **VIVAYU Aqua is a two-zone, solar-compatible irrigation intelligence platform that combines field sensing, weather, crop stage, freshwater scarcity and irrigation-water TDS to select and verify the safest practical water strategy before irrigation, while reusing the existing Vivayu model only as a research-level plant-health signal.**

---

# 42. Existing Vivayu Files Codex Must Inspect First

Before coding the legacy integration, read these exact files in the vendored repo:

```text
legacy/vivayu/README.md
legacy/vivayu/scripts/vivayu_runtime.py
legacy/vivayu/scripts/model_components.py
legacy/vivayu/scripts/select_research_model.py
legacy/vivayu/scripts/run_dashboard.py
legacy/vivayu/reports/model_selection_summary.json
legacy/vivayu/reports/model_readiness.md
legacy/vivayu/tests/test_vivayu_runtime.py
```

Important facts Codex should confirm from them:

- six legacy raw fields;
- five-reading rolling predictor;
- research-only model boundary;
- custom joblib model class dependency;
- current selected research candidate;
- dashboard output wording;
- existing test behavior.

---

# 43. Source Repositories

- Existing Vivayu: `https://github.com/Shaurya002800/Vivayu`
- InnoHack repo: `https://github.com/Shaurya002800/Vivayu-innohack`
- Existing Vivayu snapshot inspected for this specification: `cc8008a36838fba97f289876a49d599f5d7dea25`

For external agronomic values and sensor limits, Codex must prefer official manufacturer/agriculture sources and store the source URL next to configurable data instead of inventing values.

---

# 44. First Prompt to Give Codex After This File Is in the Repo

```text
Read docs/CODEX_MASTER_REFERENCE.md completely and inspect the existing legacy/vivayu files listed in Section 42. Do not implement everything at once.

Start with Milestone 1 and Milestone 2 only:
1. create the monorepo scaffold exactly as specified;
2. create FastAPI backend and Next.js/TypeScript frontend;
3. implement a typed application state with independent Zone A and Zone B;
4. implement clearly-labelled simulation mode with the six required demo scenarios defined in the reference;
5. expose GET /api/v1/health and GET /api/v1/state;
6. render Zone A and Zone B on the dashboard;
7. add tests for zone isolation and simulation state;
8. run all tests/build checks;
9. write docs/STATUS.md with what works, what does not, and the next exact milestone.

Do not touch pump actuation, TDS correction, or legacy ML integration until these acceptance criteria pass.
```

---

# 45. Official Implementation References

Codex should use these as implementation references when wiring external services/hardware:

- Open-Meteo Forecast API: `https://open-meteo.com/en/docs` - provides hourly precipitation probability, precipitation, reference evapotranspiration (ET0), and solar-radiation variables.
- Espressif Arduino ESP-NOW documentation: `https://docs.espressif.com/projects/arduino-esp32/en/latest/api/espnow.html` - peer registration, channels, sending, receiving, and callbacks.
- DFRobot Gravity Analog TDS Sensor SEN0244: `https://wiki.dfrobot.com/sen0244` - official sensor specifications, example code and calibration/temperature-compensation guidance.
- FastAPI WebSockets: `https://fastapi.tiangolo.com/advanced/websockets/` - use only after the polling-based core is stable.
- pySerial API: `https://pyserial.readthedocs.io/en/latest/pyserial_api.html` - serial-port configuration, read/write and timeout behavior.

When a scientific crop value is added to `crop_profiles.json`, store the exact agronomic source URL in that crop profile and distinguish verified source values from prototype configuration values.

---

**End of Codex Master Reference.**
