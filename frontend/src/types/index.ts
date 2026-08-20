export type DataMode = "simulation" | "hardware";

export interface HealthResponse {
  status: "ok";
  service: string;
  data_mode: DataMode;
  schema_version: "1.0";
}
