import { Icon } from "@/components/ui/icon";
import {
  formatMl,
  formatNumber,
  formatPercent,
  formatRatio,
  titleCaseCode,
} from "@/lib/formatting";
import {
  irrigationFarmerLabel,
  irrigationTone,
  strategyFarmerLabel,
} from "@/lib/presentation";
import type { DashboardSnapshot, ZoneId } from "@/types";
import type { CSSProperties } from "react";

import { ZoneSelector } from "./zone-selector";

interface ZoneViewProps {
  snapshot: DashboardSnapshot;
  selectedZone: ZoneId;
  onSelectZone: (zoneId: ZoneId) => void;
}

function Reading({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="reading-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export function ZoneView({ snapshot, selectedZone, onSelectZone }: ZoneViewProps) {
  const zone = snapshot.state.zones[selectedZone];
  const irrigation = snapshot.irrigation[selectedZone];
  const quality = snapshot.waterQuality[selectedZone];
  const allocation = snapshot.allocation.zones[selectedZone];
  const health = zone.vivayu_health;
  const moisture = zone.telemetry.soil_moisture_pct;
  const moistureValue = moisture === null ? 0 : Math.min(100, Math.max(0, moisture));
  const tone = irrigationTone(irrigation);
  const isHardware = snapshot.state.data_mode === "hardware";
  const sourceLabel = isHardware
    ? zone.online
      ? `LIVE · ${zone.telemetry.node_id ?? `Field Node ${selectedZone}`}`
      : `NODE OFFLINE · last packet ${formatNumber(zone.telemetry_age_s, 1, " s ago")}`
    : "SIMULATED DATA";

  return (
    <div className="zone-view">
      <header className="view-heading">
        <div>
          <span className="section-label">Field workspace</span>
          <h1>One field. One clear plan.</h1>
          <p>Switch between zones without mixing their telemetry, crop context, or decisions.</p>
        </div>
        <ZoneSelector snapshot={snapshot} selectedZone={selectedZone} onSelect={onSelectZone} compact />
      </header>

      <ZoneSelector snapshot={snapshot} selectedZone={selectedZone} onSelect={onSelectZone} />

      <div className={`sensor-source-banner ${isHardware ? zone.online ? "live" : "stale" : "simulated"}`}>
        <span className="source-pulse" />
        <strong>{sourceLabel}</strong>
        <span>{isHardware ? "Physical field telemetry" : "Demo scenario telemetry"}</span>
      </div>

      <section className="zone-focus-grid">
        <article className={`moisture-card tone-${tone}`}>
          <div className="panel-heading">
            <span><Icon name="drop" /> Soil moisture</span>
            <small>{zone.online ? isHardware ? "Live hardware" : "Simulated" : "Last known reading"}</small>
          </div>
          <div
            className="moisture-gauge"
            style={{ "--moisture": `${moistureValue * 3.6}deg` } as CSSProperties}
            aria-label={`Soil moisture ${formatPercent(moisture, 1)}`}
          >
            <div><strong>{formatPercent(moisture, 1)}</strong><span>{zone.online ? "Current" : "Last reading"}</span></div>
          </div>
          <div className="moisture-thresholds">
            <span><i className="critical" /> Critical {formatPercent(irrigation.critical_moisture_pct, 1)}</span>
            <span><i className="target" /> Target {formatPercent(irrigation.target_moisture_pct, 1)}</span>
          </div>
          <div className="zone-primary-message">
            <strong>{irrigationFarmerLabel(irrigation)}</strong>
            <p>{irrigation.reasons[0] ?? "The backend has not supplied a recommendation explanation."}</p>
          </div>
        </article>

        <div className="zone-plan-stack">
          <article className="zone-plan-card irrigation-plan-card">
            <div className="panel-heading">
              <span><Icon name="water" /> Irrigation plan</span>
              <span className={`plain-status tone-${tone}`}>{titleCaseCode(irrigation.urgency)} priority</span>
            </div>
            <div className="plan-hero-line">
              <div><small>Requested</small><strong>{formatMl(irrigation.requested_water_ml)}</strong></div>
              <Icon name="arrow" />
              <div><small>Safe delivery</small><strong>{formatMl(allocation.deliverable_water_ml)}</strong></div>
            </div>
            <div className="coverage-track" aria-label={`Service coverage ${formatRatio(allocation.service_fraction)}`}>
              <span style={{ width: `${Math.max(0, Math.min(100, (allocation.service_fraction ?? 0) * 100))}%` }} />
            </div>
            <div className="coverage-caption"><span>Planned coverage</span><strong>{formatRatio(allocation.service_fraction)}</strong></div>
            <p className="planning-note"><Icon name="shield" /> Planning preview only. No pump has been started.</p>
          </article>

          <article className="zone-plan-card water-plan-card">
            <div className="panel-heading"><span><Icon name="drop" /> Water plan</span><small>{quality.safe ? "Within configured limit" : "Needs attention"}</small></div>
            <h2>{strategyFarmerLabel(quality)}</h2>
            <div className="blend-mini">
              <div><span className="fresh" style={{ width: `${(quality.fresh_fraction ?? 0) * 100}%` }} /><span className="marginal" style={{ width: `${(quality.marginal_fraction ?? 0) * 100}%` }} /></div>
              <p><span>Fresh {formatMl(allocation.allocated_fresh_ml)}</span><span>Marginal {formatMl(allocation.allocated_marginal_ml)}</span></p>
            </div>
            <div className="compact-readings">
              <Reading label="Predicted blend" value={formatNumber(quality.predicted_tds_ppm, 0, " ppm")} />
              <Reading label="Measured blend" value={formatNumber(quality.measured_tds_ppm, 0, " ppm")} note="Pending hardware" />
            </div>
          </article>
        </div>
      </section>

      <section className="zone-support-grid">
        <article className="support-card">
          <div className="panel-heading"><span><Icon name="seed" /> Crop & growth</span></div>
          <div className="support-card-feature"><strong>{zone.crop_context?.crop_name ?? "Unavailable"}</strong><span>{titleCaseCode(zone.crop_context?.growth_stage)}</span></div>
          <Reading label="Days after sowing" value={formatNumber(zone.crop_context?.days_after_sowing)} />
          <Reading label="Stage sensitivity" value={titleCaseCode(zone.crop_context?.water_stress_sensitivity)} />
          <Reading label="Stage source" value={titleCaseCode(zone.crop_context?.stage_source)} />
        </article>

        <article className="support-card environment-card">
          <div className="panel-heading"><span><Icon name="weather" /> Field environment</span><small>{zone.online ? "Current packet" : "Last packet"}</small></div>
          <div className="environment-readings">
            <div><Icon name="thermometer" /><small>Temperature</small><strong>{formatNumber(zone.telemetry.temperature_c, 1, " °C")}</strong></div>
            <div><Icon name="humidity" /><small>Humidity</small><strong>{formatPercent(zone.telemetry.humidity_pct, 1)}</strong></div>
            <div><Icon name="weather" /><small>Pressure</small><strong>{formatNumber(zone.telemetry.pressure_pa === null ? null : zone.telemetry.pressure_pa / 100, 1, " hPa")}</strong></div>
          </div>
          <p className="environment-weather-note">Forecast: {formatPercent(snapshot.state.weather.rain_probability_6h_pct)} rain · ET₀ {formatNumber(snapshot.state.weather.et0_6h_mm, 2, " mm")}</p>
        </article>

        <article className="support-card health-card-simple">
          <div className="panel-heading"><span><Icon name="leaf" /> Vivayu health</span><small>Research only</small></div>
          <div className="support-card-feature"><strong>{titleCaseCode(health.status)}</strong><span>{health.pattern ?? "Pattern unavailable"}</span></div>
          {health.status === "COLLECTING" && (
            <div className="collection-progress"><span style={{ width: `${Math.min(100, (health.readings_received / Math.max(1, health.readings_required)) * 100)}%` }} /></div>
          )}
          <p>{health.reason ?? `${health.readings_received}/${health.readings_required} compatible readings collected.`}</p>
          <span className="research-boundary">Never used to trigger irrigation</span>
        </article>
      </section>

      <details className="technical-disclosure">
        <summary><span><Icon name="insights" /> Technical zone data</span><Icon name="chevron" /></summary>
        <div className="technical-grid">
          <Reading label="Node ID" value={zone.telemetry.node_id ?? "—"} />
          <Reading label="Raw soil signal" value={formatNumber(zone.telemetry.soil_moisture_raw)} />
          <Reading label="Pressure" value={formatNumber(zone.telemetry.pressure_pa, 0, " Pa")} />
          <Reading label="Gas resistance" value={formatNumber(zone.telemetry.gas_resistance_ohm, 0, " Ω")} />
          <Reading label="Battery" value={formatPercent(zone.telemetry.battery_pct, 1)} />
          <Reading label="Signal" value={formatNumber(zone.telemetry.signal_rssi_dbm, 0, " dBm")} />
          <Reading label="Telemetry age" value={formatNumber(zone.telemetry_age_s, 1, " s")} />
          <Reading label="Packet interval" value={formatNumber(zone.hardware_metadata.packet_interval_s, 2, " s")} />
          <Reading label="Allocation status" value={titleCaseCode(allocation.status)} />
        </div>
      </details>
    </div>
  );
}
