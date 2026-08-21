#pragma once

#include <math.h>

namespace vivayu {

inline float soilMoisturePercent(int raw, int dry_raw, int wet_raw) {
  if (dry_raw == wet_raw) return NAN;
  const float percent = 100.0F * static_cast<float>(raw - dry_raw) /
                        static_cast<float>(wet_raw - dry_raw);
  if (!isfinite(percent)) return NAN;
  if (percent < 0.0F) return 0.0F;
  if (percent > 100.0F) return 100.0F;
  return percent;
}

// Adafruit_BME280::readPressure() already returns Pascals. Keeping this boundary
// explicit prevents accidental multiplication of a Pa reading by 100.
inline float bme280PressurePa(float library_pressure_pa) {
  return isfinite(library_pressure_pa) && library_pressure_pa > 0.0F
             ? library_pressure_pa
             : NAN;
}

}  // namespace vivayu
