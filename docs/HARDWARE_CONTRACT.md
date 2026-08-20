# Hardware Contract

The canonical packet and command contracts are defined in Sections 6 and 7 of
`CODEX_MASTER_REFERENCE.md`.

All controller communication will use one complete, versioned JSON object per
serial line at 115200 baud. Missing physical sensors are represented as `null`,
never as fabricated values or silent zeroes.

## Topology decision still open

The current hardware inventory contains two ESP32 boards, while the target
architecture can support a field node per zone plus a controller. Software must
therefore keep `node_id` and `zone_id` separate and must not assume a one-to-one
relationship until the physical topology is frozen.

No firmware pin mapping is defined during Milestone 1.
