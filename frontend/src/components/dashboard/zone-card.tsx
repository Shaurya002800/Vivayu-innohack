import {
  clampPercent,
  formatMl,
  formatNumber,
  formatPercent,
  formatRatio,
  titleCaseCode,
} from "@/lib/formatting";
import type {
  IrrigationNeedResult,
  WaterQualityResult,
  ZoneState,
  ZoneWaterAllocation,
} from "@/types";

import { IrrigationPanel } from "./irrigation-panel";
import { StatusPill } from "./status-pill";
import { VivayuHealthCard } from "./vivayu-health-card";
import { WaterStrategy } from "./water-strategy";

interface ZoneCardProps {
  zone: ZoneState;
  irrigation: IrrigationNeedResult;
  waterQuality: WaterQualityResult;
  allocation: ZoneWaterAllocation;
}

export function ZoneCard({ zone, irrigation, waterQuality, allocation }: ZoneCardProps) {
  const moisture = zone.telemetry.soil_moisture_pct;
  const target = zone.config.irrigation_parameters.target_moisture_pct;
  const critical = zone.config.irrigation_parameters.critical_moisture_pct;
  const servicePercent = allocation.service_fraction === null ? null : allocation.service_fraction * 100;

  return (
    <article className={`zone-card zone-${zone.zone_id.toLowerCase()}`}>
      <header className="zone-card-header">
        <div className="zone-identity">
          <span className="zone-letter">{zone.zone_id}</span>
          <div>
            <p>Independent field zone</p>
            <h3>{zone.config.name}</h3>
          </div>
        </div>
        <StatusPill label={zone.online ? "Node online" : "Node offline"} tone={zone.online ? "positive" : "critical"} />
      </header>

      <section className="zone-context">
        <div>
          <span>Crop</span>
          <strong>{zone.crop_context?.crop_name ?? "Unavailable"}</strong>
          <small>{zone.config.crop_id ?? "No crop configured"}</small>
        </div>
        <div>
          <span>Growth stage</span>
          <strong>{titleCaseCode(zone.growth_stage)}</strong>
          <small>{zone.crop_context?.stage_source ? `${zone.crop_context.stage_source} estimate` : "Stage unavailable"}</small>
        </div>
        <div>
          <span>Days after sowing</span>
          <strong>{formatNumber(zone.days_after_sowing, 0)}</strong>
          <small>{zone.config.sowing_date ?? "Sowing date unavailable"}</small>
        </div>
      </section>

      <section className="moisture-panel">
        <div className="moisture-reading">
          <div>
            <span>Soil moisture</span>
            <strong>{formatPercent(moisture, 1)}</strong>
          </div>
          <div className="sensor-vitals">
            <span>{formatNumber(zone.telemetry.temperature_c, 1, "°C")}</span>
            <span>{formatPercent(zone.telemetry.humidity_pct, 0)} RH</span>
          </div>
        </div>
        <div className="moisture-track" aria-label={`Soil moisture ${formatPercent(moisture, 1)}`}>
          {moisture !== null && <span className="moisture-fill" style={{ width: `${clampPercent(moisture)}%` }} />}
          {target !== null && <i className="target-marker" style={{ left: `${clampPercent(target)}%` }} title={`Target ${target}%`} />}
          {critical !== null && <i className="critical-marker" style={{ left: `${clampPercent(critical)}%` }} title={`Critical ${critical}%`} />}
        </div>
        <div className="moisture-thresholds">
          <span>Critical <strong>{formatPercent(critical)}</strong></span>
          <span>Target <strong>{formatPercent(target)}</strong></span>
          <span>Telemetry <strong>{zone.telemetry_age_s === null ? "—" : `${formatNumber(zone.telemetry_age_s, 1)}s old`}</strong></span>
        </div>
      </section>

      <div className="zone-intelligence-grid">
        <IrrigationPanel result={irrigation} />
        <WaterStrategy result={waterQuality} />
      </div>

      <section className="zone-subpanel allocation-zone-panel">
        <div className="subpanel-heading">
          <div>
            <span className="step-label step-allocation">M6</span>
            <h4>Scarcity allocation</h4>
          </div>
          <StatusPill label={allocation.status} />
        </div>
        <div className="compact-metrics four-up">
          <div><span>Fresh allocated</span><strong>{formatMl(allocation.allocated_fresh_ml)}</strong></div>
          <div><span>Marginal allocated</span><strong>{formatMl(allocation.allocated_marginal_ml)}</strong></div>
          <div><span>Deliverable / request</span><strong>{formatMl(allocation.deliverable_water_ml)} <em>/ {formatMl(allocation.requested_water_ml)}</em></strong></div>
          <div><span>Service fraction</span><strong>{formatRatio(allocation.service_fraction)}</strong></div>
        </div>
        <div className="service-track" aria-label={`Service fraction ${formatPercent(servicePercent)}`}>
          <span style={{ width: `${clampPercent(servicePercent)}%` }} />
        </div>
      </section>

      <VivayuHealthCard health={zone.vivayu_health} />
    </article>
  );
}
