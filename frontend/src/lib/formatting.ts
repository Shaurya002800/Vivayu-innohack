export const UNAVAILABLE = "—";

export function formatNumber(
  value: number | null | undefined,
  decimals = 0,
  suffix = "",
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return UNAVAILABLE;
  }
  return `${value.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${suffix}`;
}

export function formatMl(value: number | null | undefined): string {
  return formatNumber(value, 0, " mL");
}

export function formatLitres(value: number | null | undefined): string {
  return formatNumber(value, 2, " L");
}

export function formatPercent(value: number | null | undefined, decimals = 0): string {
  return formatNumber(value, decimals, "%");
}

export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) return UNAVAILABLE;
  return formatPercent(value * 100, 0);
}

export function titleCaseCode(value: string | null | undefined): string {
  if (!value) return UNAVAILABLE;
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function compactCode(value: string | null | undefined): string {
  if (!value) return UNAVAILABLE;
  return value.replaceAll("_", " ");
}

export function formatUpdatedAt(value: string | null | undefined): string {
  if (!value) return "Update unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Update unavailable";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function clampPercent(value: number | null | undefined): number {
  if (value === null || value === undefined || !Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

export function toneForStatus(status: string | null | undefined): StatusTone {
  if (!status) return "neutral";
  if (["READY", "LIVE", "OK", "FULLY_SERVED", "MARGINAL_ONLY", "NOT_NEEDED"].includes(status)) return "positive";
  if (["COLLECTING", "SIMULATED", "CONTROLLED_BLEND", "NEEDED", "CACHED"].includes(status)) return "info";
  if (["PARTIALLY_SERVED", "DEFER_FOR_RAIN", "FRESH_ONLY", "STALE", "watch", "elevated"].includes(status)) return "warning";
  if (["CRITICAL", "ERROR", "OFFLINE", "NOT_FEASIBLE", "BLOCKED", "high"].includes(status)) return "critical";
  return "neutral";
}

export type StatusTone = "positive" | "info" | "warning" | "critical" | "neutral";
