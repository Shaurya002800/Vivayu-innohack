#include <assert.h>
#include <math.h>

#include "../common/telemetry_math.h"

int main() {
  assert(fabs(vivayu::bme280PressurePa(97481.0F) - 97481.0F) < 0.01F);
  assert(isnan(vivayu::bme280PressurePa(NAN)));
  assert(isnan(vivayu::bme280PressurePa(-1.0F)));
  assert(fabs(vivayu::soilMoisturePercent(3200, 3200, 1400)) < 0.01F);
  assert(fabs(vivayu::soilMoisturePercent(1400, 3200, 1400) - 100.0F) < 0.01F);
  assert(fabs(vivayu::soilMoisturePercent(2300, 3200, 1400) - 50.0F) < 0.01F);
  assert(vivayu::soilMoisturePercent(4095, 3200, 1400) == 0.0F);
  assert(vivayu::soilMoisturePercent(0, 3200, 1400) == 100.0F);
  assert(isnan(vivayu::soilMoisturePercent(2000, 2000, 2000)));
  return 0;
}
