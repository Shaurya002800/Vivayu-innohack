export type DataMode = "simulation" | "hardware";
export type ZoneId = "A" | "B";
export type WeatherStatus = "SIMULATED" | "LIVE" | "CACHED" | "OFFLINE";
export type IrrigationStatus =
  | "NOT_NEEDED"
  | "NEEDED"
  | "CRITICAL"
  | "DEFER_FOR_RAIN"
  | "CONFIG_REQUIRED"
  | "SENSOR_UNAVAILABLE";
export type IrrigationUrgency = "none" | "low" | "moderate" | "high" | "blocked";
export type WaterQualityStrategy =
  | "MARGINAL_ONLY"
  | "CONTROLLED_BLEND"
  | "FRESH_ONLY"
  | "NOT_FEASIBLE"
  | "CONFIG_REQUIRED"
  | "SOURCE_QUALITY_UNKNOWN"
  | "NO_IRRIGATION_REQUEST";
export type AllocationStatus =
  | "FULLY_SERVED"
  | "PARTIALLY_SERVED"
  | "DEFERRED_NO_FRESHWATER"
  | "DEFERRED_NO_SAFE_WATER"
  | "NO_IRRIGATION"
  | "BLOCKED";
export type VivayuStatus = "UNAVAILABLE" | "COLLECTING" | "READY" | "ERROR";

export interface HealthResponse {
  status: "ok";
  service: string;
  data_mode: DataMode;
  schema_version: "1.0";
}

export interface PrototypeIrrigationParameters {
  target_moisture_pct: number | null;
  critical_moisture_pct: number | null;
  ml_per_moisture_point: number | null;
  calibration_basis: "prototype_field_response";
}

export interface PrototypeWaterQualityParameters {
  max_irrigation_tds_ppm: number | null;
  constraint_basis: "prototype_or_sourced";
}

export interface VivayuSensorConfiguration {
  environment_sensor: "BME680" | "BME280" | "UNKNOWN";
  voc_sensor: "SGP40_COMPATIBLE" | "AGS10" | "UNKNOWN";
}

export interface ZoneConfig {
  zone_id: ZoneId;
  name: string;
  crop_id: string | null;
  sowing_date: string | null;
  growth_stage_mode: "AUTO" | "MANUAL";
  manual_growth_stage: string | null;
  soil_sensor_id: string | null;
  field_node_id: string | null;
  enabled: boolean;
  irrigation_parameters: PrototypeIrrigationParameters;
  water_quality_parameters: PrototypeWaterQualityParameters;
  vivayu_sensors: VivayuSensorConfiguration;
}

export interface ZoneTelemetry {
  schema_version: "1.0";
  type: "field_telemetry";
  node_id: string | null;
  zone_id: ZoneId;
  timestamp_ms: number | null;
  soil_moisture_raw: number | null;
  soil_moisture_pct: number | null;
  temperature_c: number | null;
  humidity_pct: number | null;
  pressure_pa: number | null;
  gas_resistance_ohm: number | null;
  sraw: number | null;
  battery_voltage_v: number | null;
  battery_pct: number | null;
  signal_rssi_dbm: number | null;
  received_at: string | null;
}

export interface CropContext {
  zone_id: ZoneId;
  crop_id: string | null;
  crop_name: string | null;
  sowing_date: string | null;
  days_after_sowing: number | null;
  growth_stage: string | null;
  stage_source: "AUTO" | "MANUAL" | null;
  status: "READY" | "CROP_UNCONFIGURED" | "SOWING_DATE_MISSING" | "OUTSIDE_REFERENCE_CALENDAR";
  crop_coefficient_kc: number | null;
  water_stress_sensitivity: "low" | "moderate" | "high" | null;
  target_moisture_pct: number | null;
  critical_moisture_pct: number | null;
  max_irrigation_tds_ppm: number | null;
  source_ids: string[];
  warnings: string[];
}

export interface VivayuHealthState {
  status: VivayuStatus;
  available: boolean;
  risk_level: "low" | "watch" | "elevated" | "high" | null;
  pattern: string | null;
  research_score: number | null;
  research_score_note: string | null;
  confidence_pct: number | null;
  confidence_note: string | null;
  model_name: string | null;
  readings_received: number;
  readings_required: number;
  readings_in_window: number;
  last_updated_at: string | null;
  source_mode: "SIMULATION" | "HARDWARE" | null;
  research_only: true;
  reason_code: string | null;
  reason: string | null;
  warnings: string[];
}

export interface ZoneState {
  zone_id: ZoneId;
  config: ZoneConfig;
  telemetry: ZoneTelemetry;
  growth_stage: string | null;
  days_after_sowing: number | null;
  crop_context: CropContext | null;
  telemetry_age_s: number | null;
  online: boolean;
  vivayu_health: VivayuHealthState;
}

export interface WaterSourceState {
  source_id: "fresh" | "marginal";
  display_name: string;
  tds_ppm: number | null;
  temperature_c: number | null;
  available_l: number | null;
  last_measured_at: string | null;
  measurement_age_s: number | null;
  quality_status: "SIMULATED" | "MEASURED" | "STALE" | "UNKNOWN" | "INVALID";
}

export interface MixWaterState {
  tds_ppm: number | null;
  temperature_c: number | null;
  volume_estimate_ml: number | null;
  last_measured_at: string | null;
}

export interface WeatherState {
  status: WeatherStatus;
  rain_probability_6h_pct: number | null;
  rain_6h_mm: number | null;
  et0_6h_mm: number | null;
  temperature_max_6h_c: number | null;
  fetched_at: string | null;
  age_s: number | null;
  stale: boolean;
  provider: string | null;
  provider_status: "SIMULATED" | "OK" | "ERROR" | "NOT_CONFIGURED" | "NOT_FETCHED" | null;
  error: string | null;
}

export interface PowerState {
  connected: boolean;
  solar_power_w: number | null;
  battery_voltage_v: number | null;
  battery_pct: number | null;
  load_current_a: number | null;
  measured_at: string | null;
}

export interface SerialConnectionState {
  status: "DISABLED" | "CONNECTING" | "CONNECTED" | "DISCONNECTED" | "ERROR";
  enabled: boolean;
  configured_port: string | null;
  baud_rate: number;
  last_connected_at: string | null;
  last_disconnected_at: string | null;
  last_valid_packet_at: string | null;
  last_error: string | null;
  reconnect_attempt_count: number;
  reconnect_pending: boolean;
  packets_received: number;
  packets_rejected: number;
}

export interface SystemState {
  schema_version: "1.0";
  data_mode: DataMode;
  active_scenario_id: string | null;
  updated_at: string;
  zones: Record<ZoneId, ZoneState>;
  water: {
    fresh: WaterSourceState;
    marginal: WaterSourceState;
    mix: MixWaterState;
  };
  weather: WeatherState;
  power: PowerState;
  telemetry_connection: SerialConnectionState;
}

export interface IrrigationNeedPolicy {
  stale_telemetry_after_s: number;
  strong_rain_probability_pct: number;
  meaningful_rain_6h_mm: number;
  high_et0_6h_mm: number;
  soil_deficit_weight: number;
  critical_moisture_boost: number;
  high_stage_sensitivity_boost: number;
  moderate_stage_sensitivity_boost: number;
  high_et0_boost: number;
}

export interface IrrigationNeedResult {
  zone_id: ZoneId;
  status: IrrigationStatus;
  urgency: IrrigationUrgency;
  urgency_score: number | null;
  urgency_components: {
    soil_deficit: number;
    critical_moisture: number;
    stage_sensitivity: number;
    high_et0: number;
  } | null;
  needs_irrigation: boolean;
  actionable: boolean;
  current_moisture_pct: number | null;
  target_moisture_pct: number | null;
  critical_moisture_pct: number | null;
  moisture_deficit_pct: number | null;
  ml_per_moisture_point: number | null;
  base_requested_ml: number | null;
  requested_water_ml: number | null;
  telemetry_age_s: number | null;
  crop_context_status: CropContext["status"] | null;
  growth_stage: string | null;
  stage_sensitivity: "low" | "moderate" | "high" | null;
  weather_status: WeatherStatus;
  weather_assistance_available: boolean;
  rain_deferral_applied: boolean;
  et0_urgency_applied: boolean;
  stage_urgency_applied: boolean;
  policy: IrrigationNeedPolicy;
  reason_codes: string[];
  reasons: string[];
  warning_codes: string[];
  warnings: string[];
}

export interface WaterQualityPolicy {
  tds_safety_margin_ppm: number | null;
  source_stale_after_s: number;
  volume_rounding_decimals: number;
  volume_tolerance_ml: number;
  predicted_tds_tolerance_ppm: number;
}

export interface WaterQualityResult {
  zone_id: ZoneId;
  strategy: WaterQualityStrategy;
  requested_water_ml: number | null;
  fresh_ml: number | null;
  marginal_ml: number | null;
  fresh_fraction: number | null;
  marginal_fraction: number | null;
  fresh_tds_ppm: number | null;
  marginal_tds_ppm: number | null;
  configured_max_tds_ppm: number | null;
  safety_margin_ppm: number | null;
  safety_target_tds_ppm: number | null;
  predicted_tds_ppm: number | null;
  measured_tds_ppm: null;
  safe: boolean;
  physical_verification_required: boolean;
  fresh_available_ml: number | null;
  marginal_available_ml: number | null;
  source_volume_sufficient: boolean | null;
  currently_satisfiable: boolean;
  policy: WaterQualityPolicy;
  reason_codes: string[];
  reasons: string[];
  warning_codes: string[];
  warnings: string[];
}

export interface ZoneWaterAllocation {
  zone_id: ZoneId;
  status: AllocationStatus;
  irrigation_status: IrrigationStatus;
  water_quality_strategy: WaterQualityStrategy;
  urgency_score: number | null;
  critical: boolean;
  stage_sensitivity: "low" | "moderate" | "high" | null;
  requested_water_ml: number | null;
  full_request_fresh_ml: number | null;
  full_request_marginal_ml: number | null;
  required_fresh_fraction: number | null;
  required_marginal_fraction: number | null;
  allocated_fresh_ml: number;
  allocated_marginal_ml: number;
  deliverable_water_ml: number;
  service_fraction: number | null;
  allocated_fresh_fraction: number | null;
  allocated_marginal_fraction: number | null;
  full_request_predicted_tds_ppm: number | null;
  safe_ratio_preserved: boolean | null;
  critical_minimum_target_ml: number | null;
  critical_minimum_met: boolean | null;
  reason_codes: string[];
  reasons: string[];
  warning_codes: string[];
  warnings: string[];
}

export interface FreshwaterAllocationResult {
  zones: Record<ZoneId, ZoneWaterAllocation>;
  freshwater_available_ml: number | null;
  freshwater_required_for_full_service_ml: number;
  freshwater_allocated_ml: number;
  freshwater_remaining_ml: number | null;
  marginal_available_ml: number | null;
  marginal_required_for_full_service_ml: number;
  marginal_allocated_ml: number;
  marginal_remaining_ml: number | null;
  scarcity_active: boolean | null;
  total_requested_water_ml: number;
  total_deliverable_water_ml: number;
  unserved_water_ml: number;
  critical_phase_order: ZoneId[];
  remaining_phase_order: ZoneId[];
  policy: {
    critical_minimum_delivery_fraction: number;
    volume_rounding_decimals: number;
    volume_tolerance_ml: number;
    ratio_tolerance: number;
  };
  reason_codes: string[];
  reasons: string[];
  warning_codes: string[];
  warnings: string[];
}

export interface SimulationScenarioSummary {
  id: string;
  name: string;
  description: string;
}

export interface DashboardSnapshot {
  state: SystemState;
  irrigation: Record<ZoneId, IrrigationNeedResult>;
  waterQuality: Record<ZoneId, WaterQualityResult>;
  allocation: FreshwaterAllocationResult;
  receivedAt: number;
}
