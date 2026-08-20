import type {
  DashboardSnapshot,
  FreshwaterAllocationResult,
  IrrigationNeedResult,
  PrototypeIrrigationParameters,
  PrototypeWaterQualityParameters,
  SimulationScenarioSummary,
  SystemState,
  WaterQualityResult,
  ZoneId,
} from "@/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const API_TIMEOUT_MS = 4_000;

const DEMO_IRRIGATION_PARAMETERS: PrototypeIrrigationParameters = {
  target_moisture_pct: 45,
  critical_moisture_pct: 25,
  ml_per_moisture_point: 20,
  calibration_basis: "prototype_field_response",
};

const DEMO_WATER_QUALITY_PARAMETERS: PrototypeWaterQualityParameters = {
  max_irrigation_tds_ppm: 450,
  constraint_basis: "prototype_or_sourced",
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ApiError(`Backend returned ${response.status}`, response.status);
    }
    return (await response.json()) as T;
  } catch (error: unknown) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError("Backend request timed out");
    }
    throw new ApiError("Backend is unavailable");
  } finally {
    window.clearTimeout(timer);
  }
}

export async function fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
  const [state, irrigationA, irrigationB, qualityA, qualityB, allocation] =
    await Promise.all([
      requestJson<SystemState>("/api/v1/state"),
      requestJson<IrrigationNeedResult>("/api/v1/zones/A/irrigation-need"),
      requestJson<IrrigationNeedResult>("/api/v1/zones/B/irrigation-need"),
      requestJson<WaterQualityResult>("/api/v1/water/zones/A/strategy"),
      requestJson<WaterQualityResult>("/api/v1/water/zones/B/strategy"),
      requestJson<FreshwaterAllocationResult>("/api/v1/water/allocation-preview"),
    ]);

  return {
    state,
    irrigation: { A: irrigationA, B: irrigationB },
    waterQuality: { A: qualityA, B: qualityB },
    allocation,
    receivedAt: Date.now(),
  };
}

export function fetchSimulationScenarios(): Promise<SimulationScenarioSummary[]> {
  return requestJson<SimulationScenarioSummary[]>("/api/v1/simulation/scenarios");
}

async function configureDemoZone(zoneId: ZoneId): Promise<void> {
  await Promise.all([
    requestJson<PrototypeIrrigationParameters>(
      `/api/v1/zones/${zoneId}/irrigation-parameters`,
      {
        method: "PUT",
        body: JSON.stringify(DEMO_IRRIGATION_PARAMETERS),
      },
    ),
    requestJson<PrototypeWaterQualityParameters>(
      `/api/v1/water/zones/${zoneId}/constraint`,
      {
        method: "PUT",
        body: JSON.stringify(DEMO_WATER_QUALITY_PARAMETERS),
      },
    ),
  ]);
}

export async function activateSimulationScenario(scenarioId: string): Promise<void> {
  await requestJson<SystemState>("/api/v1/simulation/load", {
    method: "POST",
    body: JSON.stringify({ scenario_id: scenarioId }),
  });
  await Promise.all([configureDemoZone("A"), configureDemoZone("B")]);
}

export async function resetSimulation(): Promise<void> {
  await requestJson<SystemState>("/api/v1/simulation/reset", { method: "POST" });
}
