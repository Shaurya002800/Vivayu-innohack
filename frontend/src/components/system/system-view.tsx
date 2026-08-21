import { EmergencyStopControl } from "@/components/dashboard/emergency-stop-control";
import { SimulationControls } from "@/components/dashboard/simulation-controls";
import { Icon } from "@/components/ui/icon";
import { formatNumber, formatPercent, formatUpdatedAt, titleCaseCode } from "@/lib/formatting";
import type { DashboardContext, DashboardSnapshot, SimulationScenarioSummary, ZoneId } from "@/types";

interface SystemViewProps {
  snapshot: DashboardSnapshot;
  stale: boolean;
  scenarios: SimulationScenarioSummary[];
  activeAction: string | null;
  actionError: string | null;
  dashboardContext: DashboardContext;
  onActivateScenario: (scenarioId: string) => Promise<void>;
  onResetScenario: () => Promise<void>;
  onEmergencyStop: () => Promise<void>;
}

function TruthRow({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: string }) {
  return (
    <div className="truth-row">
      <span className={`truth-dot tone-${tone}`} />
      <span><small>{label}</small><strong>{value}</strong><em>{detail}</em></span>
    </div>
  );
}

export function SystemView({
  snapshot,
  stale,
  scenarios,
  activeAction,
  actionError,
  dashboardContext,
  onActivateScenario,
  onResetScenario,
  onEmergencyStop,
}: SystemViewProps) {
  const state = snapshot.state;
  const serial = state.telemetry_connection;
  const controller = state.controller;

  return (
    <div className="system-view">
      <header className="view-heading">
        <div><span className="section-label">System & provenance</span><h1>Know what is real, simulated, or unavailable.</h1><p>Connections, sensor freshness, power, controller safety and demo tools live here.</p></div>
        <div className={`system-mode-hero mode-${dashboardContext === "demo" ? "demo" : state.data_mode}`}><span /><div><small>Current data mode</small><strong>{dashboardContext === "demo" ? "Demo · Simulated" : state.data_mode === "hardware" ? "Live hardware" : "Simulation"}</strong></div></div>
      </header>

      <section className="system-truth-grid">
        <article className="system-truth-card">
          <div className="panel-heading"><span><Icon name="signal" /> Data gateway</span></div>
          <TruthRow label="Backend" value={stale ? "Last known snapshot" : "Connected"} detail={formatUpdatedAt(state.updated_at)} tone={stale ? "critical" : "stable"} />
          <TruthRow label="Serial adapter" value={titleCaseCode(serial.status)} detail={serial.enabled ? `${serial.baud_rate.toLocaleString("en-IN")} baud` : "Disabled by configuration"} tone={serial.status === "CONNECTED" ? "stable" : "neutral"} />
          <TruthRow label="Packets" value={`${serial.packets_received} accepted`} detail={`${serial.packets_rejected} rejected`} />
        </article>

        <article className="system-truth-card">
          <div className="panel-heading"><span><Icon name="shield" /> Controller safety</span></div>
          <TruthRow label="Controller" value={titleCaseCode(controller.status)} detail={controller.connected ? controller.ready ? "Connected and ready" : "Connected, not ready" : "Not connected"} tone={controller.ready ? "stable" : "neutral"} />
          <TruthRow label="Reported state" value={titleCaseCode(controller.reported_state)} detail={controller.emergency_stop ? "Emergency stop reported" : "No emergency stop reported"} tone={controller.emergency_stop ? "critical" : "stable"} />
          <TruthRow label="Command certainty" value={controller.execution_uncertain ? "Uncertain" : "No uncertainty reported"} detail={controller.communication_fault ?? "No communication fault"} tone={controller.execution_uncertain ? "critical" : "stable"} />
        </article>

        <article className="system-truth-card">
          <div className="panel-heading"><span><Icon name="power" /> Power</span></div>
          <TruthRow label="Power telemetry" value={state.power.connected ? "Connected" : "Unavailable"} detail="No fallback values" tone={state.power.connected ? "stable" : "neutral"} />
          <TruthRow label="Battery" value={formatPercent(state.power.battery_pct, 1)} detail={formatNumber(state.power.battery_voltage_v, 2, " V")} />
          <TruthRow label="Solar" value={formatNumber(state.power.solar_power_w, 1, " W")} detail={formatNumber(state.power.load_current_a, 2, " A load")} />
        </article>

        <article className="system-truth-card">
          <div className="panel-heading"><span><Icon name="weather" /> Weather</span></div>
          <TruthRow label="Forecast" value={titleCaseCode(state.weather.status)} detail={state.weather.provider ?? "Provider unavailable"} tone={state.weather.stale ? "attention" : state.weather.status === "OFFLINE" ? "critical" : "stable"} />
          <TruthRow label="Provider status" value={titleCaseCode(state.weather.provider_status)} detail={state.weather.error ?? "No provider error"} />
          <TruthRow label="Forecast age" value={formatNumber(state.weather.age_s, 0, " s")} detail={state.weather.stale ? "Stale" : "Within freshness window"} />
        </article>
      </section>

      <section className="sensor-provenance-card">
        <div className="section-title-row compact-title-row"><div><span className="section-label">Independent field nodes</span><h2>Sensor provenance</h2></div><p>Missing channels remain unavailable.</p></div>
        <div className="sensor-table" role="table" aria-label="Zone sensor status">
          <div className="sensor-table-row header" role="row"><span>Zone</span><span>Node ID</span><span>Source</span><span>Soil</span><span>Temperature</span><span>Humidity</span><span>Pressure</span><span>Age</span><span>Status</span></div>
          {(["A", "B"] as ZoneId[]).map((zoneId) => {
            const zone = state.zones[zoneId];
            return (
              <div className="sensor-table-row" role="row" key={zoneId}>
                <strong>Zone {zoneId}</strong>
                <span>{zone.telemetry.node_id ?? "Unavailable"}</span>
                <span>{zone.hardware_metadata.source}</span>
                <span>{formatPercent(zone.telemetry.soil_moisture_pct, 1)}</span>
                <span>{formatNumber(zone.telemetry.temperature_c, 1, " °C")}</span>
                <span>{formatPercent(zone.telemetry.humidity_pct, 0)}</span>
                <span>{formatNumber(zone.telemetry.pressure_pa === null ? null : zone.telemetry.pressure_pa / 100, 1, " hPa")}</span>
                <span>{formatNumber(zone.telemetry_age_s, 1, " s")}</span>
                <span className={`node-status ${zone.online ? "live" : "stale"}`}>{zone.online ? state.data_mode === "hardware" ? "LIVE" : "SIMULATED" : "STALE"}</span>
              </div>
            );
          })}
        </div>
      </section>

      {state.data_mode === "hardware" && (
        <section className="hardware-debug-card">
          <div className="section-title-row compact-title-row"><div><span className="section-label">Advanced hardware debugging</span><h2>Field-node calibration</h2></div><p>Configured references are shown only when supplied through environment settings.</p></div>
          <div className="hardware-debug-grid">
            {(["A", "B"] as ZoneId[]).map((zoneId) => {
              const zone = state.zones[zoneId];
              const meta = zone.hardware_metadata;
              const bmeConnected = zone.telemetry.temperature_c !== null || zone.telemetry.humidity_pct !== null || zone.telemetry.pressure_pa !== null;
              return (
                <article key={zoneId}>
                  <div className="panel-heading"><span>Zone {zoneId} · {zone.telemetry.node_id ?? "waiting for node"}</span><small>{zone.online ? "LIVE" : "OFFLINE"}</small></div>
                  <div className="debug-values">
                    <TruthRow label="Raw soil ADC" value={formatNumber(zone.telemetry.soil_moisture_raw)} detail={`Calibrated ${formatPercent(zone.telemetry.soil_moisture_pct, 1)}`} />
                    <TruthRow label="Dry / wet reference" value={`${formatNumber(meta.soil_dry_raw)} / ${formatNumber(meta.soil_wet_raw)}`} detail={meta.soil_adc_pin === null ? "ADC pin not configured" : `GPIO ${meta.soil_adc_pin}`} />
                    <TruthRow label="BME280 channels" value={bmeConnected ? "CONNECTED" : "UNAVAILABLE"} detail={meta.bme280_i2c_address ?? "I²C address not configured"} tone={bmeConnected ? "stable" : "neutral"} />
                    <TruthRow label="I²C pins" value={`${formatNumber(meta.i2c_sda_pin)} / ${formatNumber(meta.i2c_scl_pin)}`} detail="SDA / SCL" />
                    <TruthRow label="Packet rate" value={meta.packet_interval_s === null ? "Waiting for two packets" : `~${formatNumber(meta.packet_interval_s, 2, " s")}`} detail={`${meta.packets_received} packets for this zone`} />
                    <TruthRow label="Last valid packet" value={formatNumber(zone.telemetry_age_s, 1, " s ago")} detail={zone.online ? "Within stale threshold" : "Node stale or offline"} tone={zone.online ? "stable" : "attention"} />
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {state.data_mode === "hardware" && (
        <>
          <EmergencyStopControl
            controller={controller}
            disabled={stale}
            active={activeAction === "emergency-stop"}
            error={activeAction === "emergency-stop" ? null : actionError}
            onStop={() => void onEmergencyStop()}
          />
          <div className="demo-lab-boundary">
            <div className="demo-lab-heading"><span><Icon name="alert" /></span><div><small>Separate workspace</small><h2>Demo / Simulation Lab</h2><p>Opening a scenario creates a simulated dashboard preview. Current hardware packets remain untouched.</p></div></div>
            <SimulationControls
              scenarios={scenarios}
              activeScenarioId={null}
              activeAction={activeAction}
              actionError={actionError}
              disabled={stale}
              onActivate={onActivateScenario}
              onReset={onResetScenario}
            />
          </div>
        </>
      )}

      {state.data_mode === "simulation" && (
        <SimulationControls
          scenarios={scenarios}
          activeScenarioId={state.active_scenario_id}
          activeAction={activeAction}
          actionError={actionError}
          disabled={stale}
          onActivate={onActivateScenario}
          onReset={onResetScenario}
        />
      )}

      <details className="technical-disclosure command-disclosure">
        <summary><span><Icon name="insights" /> Recent controller commands</span><Icon name="chevron" /></summary>
        <div className="command-history">
          {controller.command_history.length === 0 && <p>No controller commands have been recorded.</p>}
          {controller.command_history.slice(-5).reverse().map((record) => (
            <div key={record.command.command_id}><code>{record.command.action}</code><span>{record.command.command_id}</span><strong>{titleCaseCode(record.status)}</strong></div>
          ))}
        </div>
      </details>
    </div>
  );
}
