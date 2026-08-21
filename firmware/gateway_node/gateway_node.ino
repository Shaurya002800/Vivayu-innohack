#include <ArduinoJson.h>
#include <WiFi.h>
#include <esp_idf_version.h>
#include <esp_now.h>

#include "../common/field_telemetry_frame.h"

struct QueuedTelemetry {
  vivayu::FieldTelemetryFrame frame;
  bool has_rssi;
  int16_t rssi_dbm;
};

QueueHandle_t telemetry_queue = nullptr;

bool validFrame(const vivayu::FieldTelemetryFrame& frame) {
  if (frame.magic != vivayu::kFieldFrameMagic ||
      frame.version != vivayu::kFieldFrameVersion) return false;
  if (frame.zone_id != 'A' && frame.zone_id != 'B') return false;
  if (frame.node_id[0] == '\0' ||
      frame.node_id[sizeof(frame.node_id) - 1] != '\0') return false;
  if ((frame.available_flags & vivayu::kSoilRawAvailable) &&
      frame.soil_moisture_raw < 0)
    return false;
  if ((frame.available_flags & vivayu::kSoilPercentAvailable) &&
      (!isfinite(frame.soil_moisture_pct) ||
       frame.soil_moisture_pct < 0.0F || frame.soil_moisture_pct > 100.0F))
    return false;
  if ((frame.available_flags & vivayu::kTemperatureAvailable) &&
      !isfinite(frame.temperature_c)) return false;
  if ((frame.available_flags & vivayu::kHumidityAvailable) &&
      (!isfinite(frame.humidity_pct) || frame.humidity_pct < 0.0F ||
       frame.humidity_pct > 100.0F)) return false;
  if ((frame.available_flags & vivayu::kPressureAvailable) &&
      (!isfinite(frame.pressure_pa) || frame.pressure_pa <= 0.0F)) return false;
  return true;
}

void enqueueFrame(const uint8_t* data, int length, bool has_rssi,
                  int16_t rssi_dbm) {
  if (telemetry_queue == nullptr ||
      length != static_cast<int>(sizeof(vivayu::FieldTelemetryFrame))) return;
  QueuedTelemetry queued{};
  memcpy(&queued.frame, data, sizeof(queued.frame));
  if (!validFrame(queued.frame)) return;
  queued.has_rssi = has_rssi;
  queued.rssi_dbm = rssi_dbm;
  xQueueSend(telemetry_queue, &queued, 0);
}

#if ESP_IDF_VERSION_MAJOR >= 5
void onEspNowReceive(const esp_now_recv_info_t* info, const uint8_t* data,
                     int length) {
  const bool has_rssi = info != nullptr && info->rx_ctrl != nullptr;
  const int16_t rssi = has_rssi ? info->rx_ctrl->rssi : 0;
  enqueueFrame(data, length, has_rssi, rssi);
}
#else
void onEspNowReceive(const uint8_t*, const uint8_t* data, int length) {
  enqueueFrame(data, length, false, 0);
}
#endif

void writeNullable(JsonDocument& document, const char* key, bool available,
                   float value) {
  if (available && isfinite(value)) document[key] = value;
  else document[key] = nullptr;
}

void emitCanonicalLine(const QueuedTelemetry& queued) {
  const auto& frame = queued.frame;
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
  if (queued.has_rssi) document["signal_rssi_dbm"] = queued.rssi_dbm;
  else document["signal_rssi_dbm"] = nullptr;
  serializeJson(document, Serial);
  Serial.write('\n');
}

void setup() {
  Serial.begin(115200);
  telemetry_queue = xQueueCreate(12, sizeof(QueuedTelemetry));
  WiFi.mode(WIFI_STA);
  if (telemetry_queue == nullptr || esp_now_init() != ESP_OK) return;
  esp_now_register_recv_cb(onEspNowReceive);
}

void loop() {
  if (telemetry_queue == nullptr) return;
  QueuedTelemetry queued{};
  if (xQueueReceive(telemetry_queue, &queued, pdMS_TO_TICKS(20)) == pdTRUE) {
    emitCanonicalLine(queued);
  }
}
