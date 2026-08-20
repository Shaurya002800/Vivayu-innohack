# Architecture Decisions

## D-001 - Two logical zones are independent

**Status:** Accepted

Zone A and Zone B use isolated configuration, telemetry, decisions, history,
and future Vivayu rolling windows. This is independent of whether one or two
physical field nodes transmit the data.

## D-002 - Simulation is the default development mode

**Status:** Accepted

Hardware availability must not block software development. Simulation and
hardware adapters will emit the same typed domain schemas.

## D-003 - Legacy Vivayu is research-only

**Status:** Accepted

Legacy model results may be displayed and logged but cannot directly trigger
or veto irrigation.

## D-004 - Physical ESP32 topology

**Status:** Open

Choose between one combined field node plus controller (two ESP32s total) and
one field node per zone plus controller (three ESP32s total) before firmware
implementation. Shared environmental measurements must be labelled as shared.
