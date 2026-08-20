import { formatUpdatedAt } from "@/lib/formatting";
import type { DataMode, SimulationScenarioSummary } from "@/types";

import { StatusPill } from "./status-pill";

interface DashboardHeaderProps {
  dataMode: DataMode | null;
  activeScenarioId: string | null;
  scenarios: SimulationScenarioSummary[];
  connected: boolean;
  stale: boolean;
  updatedAt: string | null;
}

export function DashboardHeader({
  dataMode,
  activeScenarioId,
  scenarios,
  connected,
  stale,
  updatedAt,
}: DashboardHeaderProps) {
  const scenario = scenarios.find((item) => item.id === activeScenarioId);

  return (
    <header className="dashboard-header">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 48 48" role="img">
            <path d="M24 5C14 15 10 23 10 31a14 14 0 0 0 28 0C38 23 34 15 24 5Z" />
            <path d="M17 32c5-1 10-5 14-12" />
          </svg>
        </div>
        <div>
          <div className="brand-row">
            <h1>VIVAYU <span>Aqua</span></h1>
            <span className="hackathon-tag">INNOHACK 2.0</span>
          </div>
          <p>Scarcity-aware, water-quality-aware irrigation</p>
        </div>
      </div>

      <div className="header-statuses">
        <div className="header-status-copy">
          <span>Current environment</span>
          <strong>{scenario?.name ?? (activeScenarioId ? activeScenarioId : "Baseline state")}</strong>
          <small>{stale ? "Last known data" : formatUpdatedAt(updatedAt)}</small>
        </div>
        <div className="header-pills">
          <StatusPill
            label={dataMode ? dataMode.toUpperCase() : "MODE UNKNOWN"}
            tone={dataMode === "simulation" ? "warning" : dataMode === "hardware" ? "positive" : "neutral"}
          />
          <StatusPill
            label={connected ? "Backend connected" : "Backend unavailable"}
            tone={connected ? "positive" : "critical"}
            pulse={connected}
          />
        </div>
      </div>
    </header>
  );
}
