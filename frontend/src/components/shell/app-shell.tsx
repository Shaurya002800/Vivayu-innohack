import { Icon } from "@/components/ui/icon";
import { formatUpdatedAt } from "@/lib/formatting";
import type { ProductView } from "@/lib/presentation";
import type { DashboardContext, DataMode, SimulationScenarioSummary } from "@/types";
import type { ReactNode } from "react";

import { ProductNavigation } from "./product-navigation";

interface AppShellProps {
  activeView: ProductView;
  onViewChange: (view: ProductView) => void;
  dataMode: DataMode;
  activeScenarioId: string | null;
  scenarios: SimulationScenarioSummary[];
  connected: boolean;
  stale: boolean;
  updatedAt: string;
  dashboardContext: DashboardContext;
  onReturnLive: () => void;
  children: ReactNode;
}

export function AppShell({
  activeView,
  onViewChange,
  dataMode,
  activeScenarioId,
  scenarios,
  connected,
  stale,
  updatedAt,
  dashboardContext,
  onReturnLive,
  children,
}: AppShellProps) {
  const scenario = scenarios.find((item) => item.id === activeScenarioId);

  return (
    <div className="app-shell">
      <header className="product-header">
        <button type="button" className="brand" onClick={() => onViewChange("overview")} aria-label="Go to farm overview">
          <span className="brand-symbol"><Icon name="leaf" /></span>
          <span className="brand-copy">
            <strong>VIVAYU <em>Aqua</em></strong>
            <small>Farm water intelligence</small>
          </span>
        </button>

        <ProductNavigation activeView={activeView} onChange={onViewChange} />

        <div className="header-truth">
          <div className={`mode-badge mode-${dashboardContext === "demo" ? "demo" : dataMode}`}>
            <span />
            {dashboardContext === "demo"
              ? "Demo · Simulated"
              : dataMode === "simulation"
                ? "Simulation mode"
                : "Live hardware"}
          </div>
          <div className="update-truth">
            <strong>{scenario ? `Demo: ${scenario.name}` : connected ? "Farm data connected" : "Backend unavailable"}</strong>
            <small>{stale ? "Last known data" : formatUpdatedAt(updatedAt)}</small>
          </div>
        </div>
      </header>

      {stale && (
        <div className="global-connection-alert" role="status">
          <Icon name="alert" />
          Live updates are interrupted. The interface is showing the last valid backend snapshot.
        </div>
      )}

      {dashboardContext === "demo" && (
        <div className="demo-context-banner" role="status">
          <span><Icon name="alert" /><strong>DEMO MODE</strong> · SIMULATED DATA · physical telemetry is untouched</span>
          <button type="button" onClick={onReturnLive}>Return to live hardware</button>
        </div>
      )}

      <main className="product-main" id="main-content">
        <div className="view-enter" key={activeView}>{children}</div>
      </main>

      <ProductNavigation mobile activeView={activeView} onChange={onViewChange} />
    </div>
  );
}
