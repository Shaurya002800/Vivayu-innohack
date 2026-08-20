"use client";

import { useDashboardData } from "@/hooks/use-dashboard-data";

import { AllocationOverview } from "./allocation-overview";
import { DashboardHeader } from "./dashboard-header";
import { ExplanationPanel } from "./explanation-panel";
import { SimulationControls } from "./simulation-controls";
import { SystemSummary } from "./system-summary";
import { ZoneCard } from "./zone-card";

function LoadingDashboard() {
  return (
    <main className="dashboard-shell">
      <DashboardHeader
        dataMode={null}
        activeScenarioId={null}
        scenarios={[]}
        connected={false}
        stale={false}
        updatedAt={null}
      />
      <section className="loading-panel panel" aria-live="polite">
        <div className="loading-orbit"><span /></div>
        <div><p className="section-kicker">Connecting securely</p><h2>Loading canonical farm state</h2><p>No values are shown until the backend responds.</p></div>
      </section>
    </main>
  );
}

function OfflineDashboard({ error, scenarios }: { error: string; scenarios: ReturnType<typeof useDashboardData>["scenarios"] }) {
  return (
    <main className="dashboard-shell">
      <DashboardHeader
        dataMode={null}
        activeScenarioId={null}
        scenarios={scenarios}
        connected={false}
        stale={false}
        updatedAt={null}
      />
      <section className="offline-panel panel" role="alert">
        <span className="offline-symbol">!</span>
        <div>
          <p className="section-kicker">Backend connection unavailable</p>
          <h2>Dashboard data is unavailable</h2>
          <p>{error}. Sensor, weather, TDS, power, irrigation, and data-mode values remain unknown—nothing has been substituted.</p>
        </div>
      </section>
      <section className="offline-truth-grid">
        {["Data mode", "Soil telemetry", "Weather", "Water-source TDS", "Irrigation preview", "Power telemetry"].map((label) => (
          <div key={label}><span>{label}</span><strong>—</strong><small>Unavailable</small></div>
        ))}
      </section>
    </main>
  );
}

export function Dashboard() {
  const dashboard = useDashboardData();
  const { snapshot } = dashboard;

  if (dashboard.isInitialLoading && !snapshot) return <LoadingDashboard />;
  if (!snapshot) return <OfflineDashboard error={dashboard.connectionError ?? "Backend is unavailable"} scenarios={dashboard.scenarios} />;

  const state = snapshot.state;
  const stale = dashboard.connectionError !== null;

  return (
    <main className="dashboard-shell">
      <DashboardHeader
        dataMode={state.data_mode}
        activeScenarioId={state.active_scenario_id}
        scenarios={dashboard.scenarios}
        connected={!stale}
        stale={stale}
        updatedAt={state.updated_at}
      />

      {stale && (
        <div className="connection-banner" role="status">
          Connection interrupted. Last known backend snapshot is shown; live polling will retry automatically.
        </div>
      )}

      <SystemSummary state={state} />

      <section className="zones-section" aria-labelledby="zones-title">
        <div className="section-title-row">
          <div><p className="section-kicker">Independent intelligence paths</p><h2 id="zones-title">Zone A / Zone B</h2></div>
          <p className="section-note">Soil → crop stage → weather → water need → water quality → scarcity allocation</p>
        </div>
        <div className="zone-grid">
          <ZoneCard
            zone={state.zones.A}
            irrigation={snapshot.irrigation.A}
            waterQuality={snapshot.waterQuality.A}
            allocation={snapshot.allocation.zones.A}
          />
          <ZoneCard
            zone={state.zones.B}
            irrigation={snapshot.irrigation.B}
            waterQuality={snapshot.waterQuality.B}
            allocation={snapshot.allocation.zones.B}
          />
        </div>
      </section>

      <AllocationOverview allocation={snapshot.allocation} />
      <ExplanationPanel snapshot={snapshot} />
      <SimulationControls
        scenarios={dashboard.scenarios}
        activeScenarioId={state.active_scenario_id}
        activeAction={dashboard.activeAction}
        actionError={dashboard.actionError}
        disabled={state.data_mode !== "simulation" || stale}
        onActivate={dashboard.activateScenario}
        onReset={dashboard.resetScenario}
      />

      <footer className="dashboard-footer">
        <span>VIVAYU Aqua · planning intelligence</span>
        <span>Controller, physical mix verification, and actuation are not connected</span>
      </footer>
    </main>
  );
}
