"use client";

import { useState } from "react";

import { InsightsView } from "@/components/insights/insights-view";
import { OverviewView } from "@/components/overview/overview-view";
import { AppShell } from "@/components/shell/app-shell";
import { SystemView } from "@/components/system/system-view";
import { Icon } from "@/components/ui/icon";
import { WaterView } from "@/components/water/water-view";
import { ZoneView } from "@/components/zones/zone-view";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import type { ProductView } from "@/lib/presentation";
import type { DashboardContext, ZoneId } from "@/types";

function LoadingDashboard() {
  return (
    <div className="standalone-state">
      <div className="loading-brand"><Icon name="leaf" /></div>
      <span className="section-label">Connecting to VIVAYU Aqua</span>
      <h1>Preparing your farm overview</h1>
      <p>No sensor or planning value is shown until the backend responds.</p>
      <div className="loading-bar" aria-label="Loading"><span /></div>
    </div>
  );
}

function OfflineDashboard({ error }: { error: string }) {
  return (
    <div className="standalone-state offline-state" role="alert">
      <div className="loading-brand"><Icon name="alert" /></div>
      <span className="section-label">Backend unavailable</span>
      <h1>Farm data cannot be reached</h1>
      <p>{error}. Nothing has been substituted: soil, weather, TDS, power and recommendations remain unavailable.</p>
      <a href="http://localhost:8000/docs">Check backend API</a>
    </div>
  );
}

export function Dashboard() {
  const [dashboardContext, setDashboardContext] = useState<DashboardContext>("live");
  const dashboard = useDashboardData(dashboardContext);
  const [activeView, setActiveView] = useState<ProductView>("overview");
  const [selectedZone, setSelectedZone] = useState<ZoneId>("A");
  const { snapshot } = dashboard;

  if (dashboard.isInitialLoading && !snapshot) return <LoadingDashboard />;
  if (!snapshot) return <OfflineDashboard error={dashboard.connectionError ?? "Backend is unavailable"} />;

  const stale = dashboard.connectionError !== null;
  const activateScenario = async (scenarioId: string) => {
    const configureCurrentSimulation =
      dashboardContext === "live" && snapshot.state.data_mode === "simulation";
    const loaded = await dashboard.activateScenario(
      scenarioId,
      configureCurrentSimulation,
    );
    if (loaded && snapshot.state.data_mode === "hardware") setDashboardContext("demo");
  };
  const view = {
    overview: <OverviewView snapshot={snapshot} stale={stale} selectedZone={selectedZone} onSelectZone={setSelectedZone} onNavigate={setActiveView} />,
    zones: <ZoneView snapshot={snapshot} selectedZone={selectedZone} onSelectZone={setSelectedZone} />,
    water: <WaterView snapshot={snapshot} selectedZone={selectedZone} onSelectZone={setSelectedZone} />,
    insights: <InsightsView snapshot={snapshot} selectedZone={selectedZone} onSelectZone={setSelectedZone} />,
    system: (
      <SystemView
        snapshot={snapshot}
        stale={stale}
        scenarios={dashboard.scenarios}
        activeAction={dashboard.activeAction}
        actionError={dashboard.actionError}
        dashboardContext={dashboardContext}
        onActivateScenario={activateScenario}
        onResetScenario={async () => { await dashboard.resetScenario(); }}
        onEmergencyStop={async () => { await dashboard.emergencyStop(); }}
      />
    ),
  }[activeView];

  return (
    <AppShell
      activeView={activeView}
      onViewChange={setActiveView}
      dataMode={snapshot.state.data_mode}
      activeScenarioId={snapshot.state.active_scenario_id}
      scenarios={dashboard.scenarios}
      connected={!stale}
      stale={stale}
      updatedAt={snapshot.state.updated_at}
      dashboardContext={dashboardContext}
      onReturnLive={() => setDashboardContext("live")}
    >
      {view}
      <footer className="product-footer">
        <span>VIVAYU Aqua · farmer-first planning intelligence</span>
        <span>Irrigation start remains unavailable · STOP_ALL is the only command control</span>
      </footer>
    </AppShell>
  );
}
