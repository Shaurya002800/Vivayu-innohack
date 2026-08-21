#pragma once

#include <stdint.h>

namespace vivayu {

constexpr uint32_t kFieldFrameMagic = 0x56415141;
constexpr uint8_t kFieldFrameVersion = 1;

enum FieldChannelFlag : uint16_t {
  kSoilRawAvailable = 1U << 0,
  kSoilPercentAvailable = 1U << 1,
  kTemperatureAvailable = 1U << 2,
  kHumidityAvailable = 1U << 3,
  kPressureAvailable = 1U << 4,
};

// Internal fixed-width ESP-NOW frame. The gateway converts this to the frozen
// newline-delimited JSON contract without inferring a zone from arrival order.
struct __attribute__((packed)) FieldTelemetryFrame {
  uint32_t magic;
  uint8_t version;
  char node_id[24];
  char zone_id;
  uint32_t timestamp_ms;
  uint16_t available_flags;
  int32_t soil_moisture_raw;
  float soil_moisture_pct;
  float temperature_c;
  float humidity_pct;
  float pressure_pa;
};

}  // namespace vivayu
