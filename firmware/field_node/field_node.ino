#include <Adafruit_BME280.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <Wire.h>
#include <esp_now.h>

#include "../common/field_telemetry_frame.h"
#include "../common/telemetry_math.h"

// Override these build flags per physical node. Never flash two field nodes
// with the same identity. Replace the placeholder gateway MAC before testing.
#ifndef VIVAYU_NODE_ID
#define VIVAYU_NODE_ID "field-node-a"
#endif
#ifndef VIVAYU_ZONE_ID
#define VIVAYU_ZONE_ID 'A'
#endif
#ifndef VIVAYU_DIRECT_USB_SERIAL
#define VIVAYU_DIRECT_USB_SERIAL 0
#endif

// ESP32 DevKit defaults. GPIO 34 is ADC1/input-only and remains usable with Wi-Fi.
#ifndef VIVAYU_I2C_SDA_PIN
#define VIVAYU_I2C_SDA_PIN 21
#endif
#ifndef VIVAYU_I2C_SCL_PIN
#define VIVAYU_I2C_SCL_PIN 22
#endif
#ifndef VIVAYU_SOIL_ADC_PIN
#define VIVAYU_SOIL_ADC_PIN 34
#endif

// Prototype soil-index calibration (not volumetric water content):
// 1. Read the filtered value in dry/reference soil.
// 2. Read it again in fully wet/reference soil.
// 3. Replace both constants for this exact probe, board and supply voltage.
#ifndef VIVAYU_SOIL_DRY_RAW
#define VIVAYU_SOIL_DRY_RAW 0
#endif
#ifndef VIVAYU_SOIL_WET_RAW
#define VIVAYU_SOIL_WET_RAW 0
#endif
#ifndef VIVAYU_SOIL_SENSOR_ENABLED
#define VIVAYU_SOIL_SENSOR_ENABLED 1
#endif

constexpr uint32_t kTelemetryIntervalMs = 1000;
constexpr size_t kSoilSampleCount = 7;
constexpr int kSoilValidMinRaw = 10;
constexpr int kSoilValidMaxRaw = 4085;
constexpr uint8_t kGatewayMac[6] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x01};

Adafruit_BME280 bme280;
bool bme280_connected = false;
uint32_t last_telemetry_ms = 0;

bool validZoneIdentity() {
  return (VIVAYU_ZONE_ID == 'A' || VIVAYU_ZONE_ID == 'B') &&
         VIVAYU_NODE_ID[0] != '\0';
}

bool initializeBme280() {
  if (bme280.begin(0x76, &Wire)) return true;
  return bme280.begin(0x77, &Wire);
}

bool initializeEspNow() {
  WiFi.mode(WIFI_STA);
  if (esp_now_init() != ESP_OK) return false;
  esp_now_peer_info_t peer{};
  memcpy(peer.peer_addr, kGatewayMac, sizeof(kGatewayMac));
  peer.channel = 0;
  peer.encrypt = false;
  return esp_now_add_peer(&peer) == ESP_OK;
}

bool readFilteredSoilRaw(int32_t& raw) {
#if !VIVAYU_SOIL_SENSOR_ENABLED
  (void)raw;
  return false;
#else
  int samples[kSoilSampleCount];
  for (size_t index = 0; index < kSoilSampleCount; ++index) {
    samples[index] = analogRead(VIVAYU_SOIL_ADC_PIN);
    delayMicroseconds(2000);
  }
  for (size_t i = 1; i < kSoilSampleCount; ++i) {
    const int candidate = samples[i];
    size_t j = i;
    while (j > 0 && samples[j - 1] > candidate) {
      samples[j] = samples[j - 1];
      --j;
    }
    samples[j] = candidate;
  }
  raw = samples[kSoilSampleCount / 2];
  return raw >= kSoilValidMinRaw && raw <= kSoilValidMaxRaw;
#endif
}

vivayu::FieldTelemetryFrame readTelemetry() {
  vivayu::FieldTelemetryFrame frame{};
  frame.magic = vivayu::kFieldFrameMagic;
  frame.version = vivayu::kFieldFrameVersion;
  strncpy(frame.node_id, VIVAYU_NODE_ID, sizeof(frame.node_id) - 1);
  frame.node_id[sizeof(frame.node_id) - 1] = '\0';
  frame.zone_id = VIVAYU_ZONE_ID;
  frame.timestamp_ms = millis();

  int32_t soil_raw = 0;
  if (readFilteredSoilRaw(soil_raw)) {
    frame.available_flags |= vivayu::kSoilRawAvailable;
    frame.soil_moisture_raw = soil_raw;
    const float soil_pct = vivayu::soilMoisturePercent(
        soil_raw, VIVAYU_SOIL_DRY_RAW, VIVAYU_SOIL_WET_RAW);
    if (isfinite(soil_pct)) {
      frame.available_flags |= vivayu::kSoilPercentAvailable;
      frame.soil_moisture_pct = soil_pct;
    }
  }

  if (bme280_connected) {
    const float temperature = bme280.readTemperature();
    const float humidity = bme280.readHumidity();
    const float pressure = vivayu::bme280PressurePa(bme280.readPressure());
    if (isfinite(temperature)) {
      frame.available_flags |= vivayu::kTemperatureAvailable;
      frame.temperature_c = temperature;
    }
    if (isfinite(humidity) && humidity >= 0.0F && humidity <= 100.0F) {
      frame.available_flags |= vivayu::kHumidityAvailable;
      frame.humidity_pct = humidity;
    }
    if (isfinite(pressure)) {
      frame.available_flags |= vivayu::kPressureAvailable;
      frame.pressure_pa = pressure;
    }
  }
  return frame;
}

void writeNullable(JsonDocument& document, const char* key, bool available,
                   float value) {
  if (available && isfinite(value)) document[key] = value;
  else document[key] = nullptr;
}

void writeDirectSerial(const vivayu::FieldTelemetryFrame& frame) {
  StaticJsonDocument<768> document;
  document["schema_version"] = "1.0";
  document["type"] = "field_telemetry";
  document["node_id"] = frame.node_id;
  char zone[2] = {frame.zone_id, '\0'};
  document["zone_id"] = zone;
  document["timestamp_ms"] = frame.timestamp_ms;
  if (frame.available_flags & vivayu::kSoilRawAvailable) {
    document["soil_moisture_raw"] = frame.soil_moisture_raw;
  } else {
    document["soil_moisture_raw"] = nullptr;
  }
  if (frame.available_flags & vivayu::kSoilPercentAvailable) {
    document["soil_moisture_pct"] = frame.soil_moisture_pct;
  } else {
    document["soil_moisture_pct"] = nullptr;
  }
  writeNullable(document, "temperature_c",
                frame.available_flags & vivayu::kTemperatureAvailable,
                frame.temperature_c);
  writeNullable(document, "humidity_pct",
                frame.available_flags & vivayu::kHumidityAvailable,
                frame.humidity_pct);
  writeNullable(document, "pressure_pa",
                frame.available_flags & vivayu::kPressureAvailable,
                frame.pressure_pa);
  document["gas_resistance_ohm"] = nullptr;
  document["sraw"] = nullptr;
  document["battery_voltage_v"] = nullptr;
  document["battery_pct"] = nullptr;
  document["signal_rssi_dbm"] = nullptr;
  serializeJson(document, Serial);
  Serial.write('\n');
}

void setup() {
  Serial.begin(115200);
  if (!validZoneIdentity()) return;
  Wire.begin(VIVAYU_I2C_SDA_PIN, VIVAYU_I2C_SCL_PIN);
  bme280_connected = initializeBme280();
  analogReadResolution(12);
  analogSetPinAttenuation(VIVAYU_SOIL_ADC_PIN, ADC_11db);
#if !VIVAYU_DIRECT_USB_SERIAL
  initializeEspNow();
#endif
}

void loop() {
  const uint32_t now = millis();
  if (now - last_telemetry_ms < kTelemetryIntervalMs) return;
  last_telemetry_ms = now;
  const vivayu::FieldTelemetryFrame frame = readTelemetry();
#if VIVAYU_DIRECT_USB_SERIAL
  writeDirectSerial(frame);
#else
  esp_now_send(kGatewayMac, reinterpret_cast<const uint8_t*>(&frame),
               sizeof(frame));
#endif
}
