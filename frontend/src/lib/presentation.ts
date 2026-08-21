import type {
  DashboardSnapshot,
  IrrigationNeedResult,
  WaterQualityResult,
  ZoneId,
  ZoneState,
} from "@/types";

export type ProductView = "overview" | "zones" | "water" | "insights" | "system";
export type ConditionTone = "stable" | "attention" | "critical" | "unknown";

const urgencyRank: Record<IrrigationNeedResult["status"], number> = {
  CRITICAL: 6,
  NEEDED: 5,
  SENSOR_UNAVAILABLE: 4,
  CONFIG_REQUIRED: 3,
  DEFER_FOR_RAIN: 2,
  NOT_NEEDED: 1,
};

export function primaryZone(snapshot: DashboardSnapshot): ZoneId {
  return urgencyRank[snapshot.irrigation.A.status] >= urgencyRank[snapshot.irrigation.B.status]
    ? "A"
    : "B";
}

export function irrigationFarmerLabel(result: IrrigationNeedResult): string {
  const labels: Record<IrrigationNeedResult["status"], string> = {
    CRITICAL: "Water needed now",
    NEEDED: "Irrigation recommended",
    NOT_NEEDED: "Moisture is healthy",
    DEFER_FOR_RAIN: "Rain expected — wait",
    SENSOR_UNAVAILABLE: "Soil reading unavailable",
    CONFIG_REQUIRED: "Farm setup needed",
  };
  return labels[result.status];
}

export function irrigationTone(result: IrrigationNeedResult): ConditionTone {
  if (result.status === "CRITICAL") return "critical";
  if (["NEEDED", "DEFER_FOR_RAIN"].includes(result.status)) return "attention";
  if (["SENSOR_UNAVAILABLE", "CONFIG_REQUIRED"].includes(result.status)) return "unknown";
  return "stable";
}

export function strategyFarmerLabel(result: WaterQualityResult): string {
  const labels: Record<WaterQualityResult["strategy"], string> = {
    CONTROLLED_BLEND: "A safe water blend is available",
    FRESH_ONLY: "Use freshwater only",
    MARGINAL_ONLY: "Marginal water is suitable",
    NO_IRRIGATION_REQUEST: "No water plan needed",
    SOURCE_QUALITY_UNKNOWN: "Water quality needs checking",
    CONFIG_REQUIRED: "Water limits need setup",
    NOT_FEASIBLE: "No safe water plan available",
  };
  return labels[result.strategy];
}

export function farmCondition(snapshot: DashboardSnapshot, stale: boolean) {
  const zoneId = primaryZone(snapshot);
  const result = snapshot.irrigation[zoneId];
  const quality = snapshot.waterQuality[zoneId];

  if (stale) {
    return {
      tone: "unknown" as const,
      eyebrow: "Connection interrupted",
      headline: "Showing the last known farm plan",
      explanation: "Live updates are unavailable. No sensor value has been replaced or guessed.",
      action: "View system status",
      view: "system" as ProductView,
      zoneId,
    };
  }
  if (result.status === "CRITICAL") {
    return {
      tone: "critical" as const,
      eyebrow: "Immediate attention",
      headline: `Zone ${zoneId} needs water now`,
      explanation: `${irrigationFarmerLabel(result)}. ${strategyFarmerLabel(quality)}.`,
      action: `View Zone ${zoneId}`,
      view: "zones" as ProductView,
      zoneId,
    };
  }
  if (result.status === "NEEDED") {
    return {
      tone: "attention" as const,
      eyebrow: "Irrigation planning",
      headline: `Zone ${zoneId} needs irrigation`,
      explanation: `${irrigationFarmerLabel(result)}. ${strategyFarmerLabel(quality)}.`,
      action: "View water plan",
      view: "water" as ProductView,
      zoneId,
    };
  }
  if (snapshot.allocation.scarcity_active) {
    return {
      tone: "attention" as const,
      eyebrow: "Freshwater bank",
      headline: "Freshwater is limited",
      explanation: "The current plan preserves safe source ratios while prioritising the farm’s needs.",
      action: "View allocation",
      view: "water" as ProductView,
      zoneId,
    };
  }
  if (result.status === "DEFER_FOR_RAIN") {
    return {
      tone: "stable" as const,
      eyebrow: "Weather-assisted plan",
      headline: "Rain is expected — irrigation can wait",
      explanation: "The backend has deferred the moderate need; no hardware action has been started.",
      action: `View Zone ${zoneId}`,
      view: "zones" as ProductView,
      zoneId,
    };
  }
  if (["SENSOR_UNAVAILABLE", "CONFIG_REQUIRED"].includes(result.status)) {
    return {
      tone: "unknown" as const,
      eyebrow: "Farm setup attention",
      headline: `Zone ${zoneId} needs a reliable reading`,
      explanation: irrigationFarmerLabel(result),
      action: "View system status",
      view: "system" as ProductView,
      zoneId,
    };
  }
  return {
    tone: "stable" as const,
    eyebrow: "Farm overview",
    headline: "Farm condition is stable",
    explanation: "Current soil readings do not require irrigation. The system continues to monitor both zones.",
    action: "No action needed",
    view: "overview" as ProductView,
    zoneId,
  };
}

export function attentionZoneCount(snapshot: DashboardSnapshot): number {
  return (["A", "B"] as ZoneId[]).filter((zoneId) =>
    ["CRITICAL", "NEEDED", "SENSOR_UNAVAILABLE", "CONFIG_REQUIRED"].includes(
      snapshot.irrigation[zoneId].status,
    ),
  ).length;
}

export function zoneDisplayName(zone: ZoneState): string {
  return zone.config.name || `Zone ${zone.zone_id}`;
}
