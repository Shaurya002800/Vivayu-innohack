import { formatLitres, formatNumber, formatPercent } from "@/lib/formatting";
import type { SystemState } from "@/types";

import { StatusPill } from "./status-pill";

interface SummaryMetricProps {
  eyebrow: string;
  value: string;
  detail: string;
  accent?: "aqua" | "blue" | "amber" | "neutral";
  icon: React.ReactNode;
}

function SummaryMetric({ eyebrow, value, detail, accent = "neutral", icon }: SummaryMetricProps) {
  return (
    <article className={`summary-metric metric-${accent}`}>
      <div className="metric-icon" aria-hidden="true">{icon}</div>
      <div>
        <p>{eyebrow}</p>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

const DropIcon = () => (
  <svg viewBox="0 0 24 24"><path d="M12 3S6 9.4 6 14a6 6 0 0 0 12 0c0-4.6-6-11-6-11Z" /></svg>
);
const QualityIcon = () => (
  <svg viewBox="0 0 24 24"><path d="M4 7h16M7 12h10M9 17h6" /></svg>
);
const WeatherIcon = () => (
  <svg viewBox="0 0 24 24"><path d="M7 17h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 10.5 3.5 3.5 0 0 0 7 17Z" /><path d="m8 20-1 2m5-2-1 2m5-2-1 2" /></svg>
);
const LeafIcon = () => (
  <svg viewBox="0 0 24 24"><path d="M5 20c8 0 14-5 14-15C9 5 5 10 5 20Z" /><path d="M5 20c3-5 6-7 10-10" /></svg>
);
const PowerIcon = () => (
  <svg viewBox="0 0 24 24"><path d="M13 2 5 14h6l-1 8 9-13h-6V2Z" /></svg>
);

export function SystemSummary({ state }: { state: SystemState }) {
  const { fresh, marginal } = state.water;
  const weather = state.weather;
  const telemetryConnection = state.telemetry_connection;
  const telemetryValue = telemetryConnection.status === "CONNECTED"
    ? "Connected"
    : telemetryConnection.status === "DISABLED"
      ? "Simulation only"
      : telemetryConnection.status === "CONNECTING"
        ? "Connecting"
        : "Not connected";
  const telemetryDetail = telemetryConnection.status === "CONNECTED"
    ? `${telemetryConnection.packets_received.toLocaleString("en-IN")} valid inbound packets · controller separate`
    : telemetryConnection.status === "DISABLED"
      ? "Serial hardware is not opened in simulation"
      : telemetryConnection.reconnect_pending
        ? "Serial reconnect pending"
        : "Actuator controller remains unavailable";
  const controllerDetail = state.controller.communication_fault
    ?? (state.controller.last_ack_command_id
      ? `ACK ${state.controller.last_ack_status ?? "pending"} · ${state.controller.last_ack_command_id}`
      : "Waiting for genuine controller status");

  return (
    <section className="system-summary" aria-labelledby="system-overview-title">
      <div className="section-title-row">
        <div>
          <p className="section-kicker">Live intelligence snapshot</p>
          <h2 id="system-overview-title">Farm water overview</h2>
        </div>
        <div className="truth-label">
          <StatusPill label="Planning preview" tone="info" />
          <span>No irrigation start controls</span>
        </div>
      </div>

      <div className="summary-grid">
        <SummaryMetric
          eyebrow="Freshwater bank"
          value={formatLitres(fresh.available_l)}
          detail={`${formatNumber(fresh.tds_ppm, 0, " ppm")} source TDS`}
          accent="aqua"
          icon={<DropIcon />}
        />
        <SummaryMetric
          eyebrow="Marginal-water bank"
          value={formatLitres(marginal.available_l)}
          detail={`${formatNumber(marginal.tds_ppm, 0, " ppm")} source TDS`}
          accent="blue"
          icon={<QualityIcon />}
        />
        <SummaryMetric
          eyebrow="Rain · next 6 hours"
          value={formatPercent(weather.rain_probability_6h_pct)}
          detail={`${formatNumber(weather.rain_6h_mm, 1, " mm")} expected · ${weather.status}`}
          accent="blue"
          icon={<WeatherIcon />}
        />
        <SummaryMetric
          eyebrow="Reference ET₀ · 6 hours"
          value={formatNumber(weather.et0_6h_mm, 1, " mm")}
          detail={`${formatNumber(weather.temperature_max_6h_c, 1, "°C")} max temperature`}
          accent="amber"
          icon={<LeafIcon />}
        />
        <SummaryMetric
          eyebrow="Telemetry gateway"
          value={telemetryValue}
          detail={telemetryDetail}
          icon={<PowerIcon />}
        />
        <SummaryMetric
          eyebrow="Controller"
          value={state.controller.status}
          detail={controllerDetail}
          accent={state.controller.status === "IDLE" ? "aqua" : state.controller.execution_uncertain ? "amber" : "neutral"}
          icon={<PowerIcon />}
        />
        <SummaryMetric
          eyebrow="Power telemetry"
          value={state.power.connected ? formatPercent(state.power.battery_pct) : "Not connected"}
          detail={state.power.connected ? `${formatNumber(state.power.solar_power_w, 1, " W")} measured solar` : "No measured watts or battery state"}
          icon={<PowerIcon />}
        />
      </div>
    </section>
  );
}
