# VIVAYU Aqua field telemetry firmware

This firmware implements the frozen `field_telemetry` input contract in
`docs/HARDWARE_CONTRACT.md`. It does not actuate pumps or valves.

## Hardware roles

- `field_node/field_node.ino`: one ESP32 per zone, reading a capacitive soil
  probe and BME280, then transmitting a fixed internal frame over ESP-NOW.
- `gateway_node/gateway_node.ino`: receives both identified field-node frames
  and writes canonical newline-delimited JSON to the backend USB serial port.
- Direct USB smoke mode: compile a field node with
  `VIVAYU_DIRECT_USB_SERIAL=1` to bypass ESP-NOW and emit the same JSON itself.

The sketches require the ESP32 Arduino core, ArduinoJson, and Adafruit BME280
library. Serial is always 115200 baud. Production serial output contains JSON
lines only; do not add debug text to that channel.

## Per-node build configuration

Set these build macros for each physical field node:

```text
VIVAYU_NODE_ID="field-node-a"   # unique, configured in the backend zone
VIVAYU_ZONE_ID='A'              # A or B; never inferred by the gateway
VIVAYU_I2C_SDA_PIN=21
VIVAYU_I2C_SCL_PIN=22
VIVAYU_SOIL_ADC_PIN=34          # ADC1 pin; suitable while Wi-Fi is active
VIVAYU_SOIL_DRY_RAW=<measured dry reference>
VIVAYU_SOIL_WET_RAW=<measured wet reference>
```

Also replace `kGatewayMac` in `field_node.ino` with the actual gateway station
MAC before ESP-NOW testing. Build Zone B with a distinct node ID and its own
probe calibration.

The firmware defaults both calibration references to zero on purpose. In that
state the real filtered ADC raw value is sent, while `soil_moisture_pct` is
`null`. This prevents an uncalibrated probe from being presented as calibrated.

## Soil calibration

1. Flash direct USB mode and observe `soil_moisture_raw` using
   `scripts/watch_telemetry.py` through the backend.
2. Record a stable median raw value in the chosen dry/reference condition.
3. Record a stable median raw value in the chosen wet/reference condition.
4. Compile those two measurements into that node and copy the same references
   into its `ZONE_*_SOIL_DRY_RAW` and `ZONE_*_SOIL_WET_RAW` backend environment
   settings for dashboard provenance.
5. Verify dry approaches 0%, wet approaches 100%, and intermediate readings
   move monotonically. The displayed percentage is a prototype calibrated
   moisture index, not volumetric water content.

The node takes seven ADC samples and uses their median. Values outside the
usable 12-bit range are treated as unavailable. The calibrated index is clamped
to 0-100%.

## BME280 behavior

The node tries I2C addresses `0x76` and `0x77`. Adafruit BME280 pressure is
already in pascals and is transmitted as `pressure_pa`; the dashboard alone
converts it to hPa for display. If initialization or an individual channel read
fails, that channel is emitted as JSON `null`. Soil telemetry continues.

## Bench smoke test

1. Configure the backend with `DATA_MODE=hardware`, the USB `SERIAL_PORT`, and
   the exact node/pin/calibration metadata in `.env`.
2. Start the backend and dashboard normally.
3. Run `python3 scripts/watch_telemetry.py` from the repository root.
4. Confirm each zone reports its own node ID at about one packet per second.
5. Disconnect only the BME280: temperature, humidity, and pressure must become
   unavailable while soil remains live.
6. Disconnect only the soil probe: soil fields must become unavailable while
   the BME280 channels remain live.
7. Stop one field node for longer than `ZONE_STALE_SECONDS`: only that zone must
   become stale and retain its values as last readings.
8. Open a dashboard scenario: the permanent demo label must appear. Return to
   live hardware and confirm the hardware readings were not replaced.

Software tests cannot establish wiring correctness, sensor calibration, RF
range, USB device identity, or physical packet stability. Those remain bench
acceptance checks.
