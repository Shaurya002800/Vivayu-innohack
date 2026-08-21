import { Icon } from "@/components/ui/icon";
import { formatLitres, formatMl, formatNumber, formatRatio, titleCaseCode } from "@/lib/formatting";
import { strategyFarmerLabel } from "@/lib/presentation";
import type { DashboardSnapshot, ZoneId } from "@/types";

import { ZoneSelector } from "@/components/zones/zone-selector";

interface WaterViewProps {
  snapshot: DashboardSnapshot;
  selectedZone: ZoneId;
  onSelectZone: (zoneId: ZoneId) => void;
}

function ExplanationList({ values, empty }: { values: string[]; empty: string }) {
  if (values.length === 0) return <p className="empty-copy">{empty}</p>;
  return <ul className="plain-reason-list">{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul>;
}

export function WaterView({ snapshot, selectedZone, onSelectZone }: WaterViewProps) {
  const state = snapshot.state;
  const quality = snapshot.waterQuality[selectedZone];
  const zoneAllocation = snapshot.allocation.zones[selectedZone];
  const allocation = snapshot.allocation;
  const required = allocation.freshwater_required_for_full_service_ml;
  const availableMl = state.water.fresh.available_l === null ? null : state.water.fresh.available_l * 1000;
  const bankPercent = availableMl && availableMl > 0
    ? Math.min(100, (allocation.freshwater_remaining_ml ?? 0) / availableMl * 100)
    : 0;

  return (
    <div className="water-view">
      <header className="view-heading">
        <div><span className="section-label">Water intelligence</span><h1>See where every drop goes.</h1><p>Source quality, safe blending and scarcity allocation—presented as one connected plan.</p></div>
        <ZoneSelector snapshot={snapshot} selectedZone={selectedZone} onSelect={onSelectZone} compact />
      </header>

      <section className="water-flow-card">
        <div className="water-source source-fresh">
          <span className="source-icon"><Icon name="drop" /></span>
          <small>Fresh source</small>
          <strong>{formatLitres(state.water.fresh.available_l)}</strong>
          <em>{formatNumber(state.water.fresh.tds_ppm, 0, " ppm")}</em>
        </div>
        <div className="flow-line flow-left"><i /><Icon name="arrow" /></div>
        <div className="water-mix-node">
          <span>Safe plan for Zone {selectedZone}</span>
          <strong>{strategyFarmerLabel(quality)}</strong>
          <div className="mix-ring"><Icon name="water" /><small>{formatMl(zoneAllocation.deliverable_water_ml)}</small></div>
          <p><span>{formatMl(zoneAllocation.allocated_fresh_ml)} fresh</span><span>{formatMl(zoneAllocation.allocated_marginal_ml)} marginal</span></p>
        </div>
        <div className="flow-line flow-right"><Icon name="arrow" /><i /></div>
        <div className="water-source source-marginal">
          <span className="source-icon"><Icon name="water" /></span>
          <small>Marginal source</small>
          <strong>{formatLitres(state.water.marginal.available_l)}</strong>
          <em>{formatNumber(state.water.marginal.tds_ppm, 0, " ppm")}</em>
        </div>
      </section>

      <section className="water-plan-grid">
        <article className="blend-plan-card">
          <div className="panel-heading"><span><Icon name="shield" /> Safe blend</span><span className={`plain-status ${quality.safe ? "tone-stable" : "tone-critical"}`}>{quality.safe ? "Safe on paper" : "Not safe"}</span></div>
          <h2>{titleCaseCode(quality.strategy)}</h2>
          <p>{quality.reasons[0] ?? "No blend explanation is available."}</p>
          <div className="blend-bar-large" aria-label={`Fresh ${formatRatio(quality.fresh_fraction)}, marginal ${formatRatio(quality.marginal_fraction)}`}>
            <span className="fresh" style={{ width: `${(quality.fresh_fraction ?? 0) * 100}%` }} />
            <span className="marginal" style={{ width: `${(quality.marginal_fraction ?? 0) * 100}%` }} />
          </div>
          <div className="blend-legend"><span><i className="fresh" />Fresh <strong>{formatRatio(quality.fresh_fraction)}</strong></span><span><i className="marginal" />Marginal <strong>{formatRatio(quality.marginal_fraction)}</strong></span></div>
          <div className="tds-comparison">
            <div><small>Predicted TDS</small><strong>{formatNumber(quality.predicted_tds_ppm, 0, " ppm")}</strong></div>
            <Icon name="arrow" />
            <div><small>Safety target</small><strong>{formatNumber(quality.safety_target_tds_ppm, 0, " ppm")}</strong></div>
            <div className="measurement-pending"><small>Measured mix</small><strong>{formatNumber(quality.measured_tds_ppm, 0, " ppm")}</strong><em>Pending hardware</em></div>
          </div>
          <p className="planning-note"><Icon name="alert" /> Physical TDS verification is required before delivery.</p>
        </article>

        <article className="freshwater-bank-card">
          <div className="panel-heading"><span><Icon name="drop" /> Freshwater bank</span><small>{allocation.scarcity_active ? "Scarcity active" : "Enough for current plan"}</small></div>
          <div className="bank-hero"><strong>{formatMl(allocation.freshwater_remaining_ml)}</strong><span>remaining after planned allocation</span></div>
          <div className="bank-track"><span style={{ width: `${bankPercent}%` }} /></div>
          <div className="bank-summary"><span>Available {formatMl(availableMl)}</span><span>Needed {formatMl(required)}</span></div>
          <div className="allocation-zone-list">
            {(["A", "B"] as ZoneId[]).map((zoneId) => {
              const item = allocation.zones[zoneId];
              return (
                <button type="button" key={zoneId} className={selectedZone === zoneId ? "active" : ""} onClick={() => onSelectZone(zoneId)}>
                  <span>Zone {zoneId}<small>{titleCaseCode(item.status)}</small></span>
                  <strong>{formatMl(item.allocated_fresh_ml)}<small>fresh</small></strong>
                  <strong>{formatMl(item.deliverable_water_ml)}<small>total</small></strong>
                </button>
              );
            })}
          </div>
          {zoneAllocation.safe_ratio_preserved !== null && (
            <p className={`ratio-safety ${zoneAllocation.safe_ratio_preserved ? "safe" : "unsafe"}`}>
              <Icon name={zoneAllocation.safe_ratio_preserved ? "check" : "alert"} />
              {zoneAllocation.safe_ratio_preserved ? "Safe source ratio preserved under allocation" : "Safe source ratio is not preserved"}
            </p>
          )}
        </article>
      </section>

      <details className="technical-disclosure explanation-disclosure">
        <summary><span><Icon name="insights" /> Why this allocation?</span><Icon name="chevron" /></summary>
        <div className="explanation-columns">
          <div><h3>Farmer-readable reasons</h3><ExplanationList values={[...zoneAllocation.reasons, ...zoneAllocation.warnings]} empty="No additional reasons supplied." /></div>
          <div><h3>Technical decision codes</h3><div className="code-cloud">{[...zoneAllocation.reason_codes, ...zoneAllocation.warning_codes].map((code) => <code key={code}>{code}</code>)}</div></div>
        </div>
      </details>

      <p className="page-truth"><Icon name="shield" /> This is a read-only allocation preview. Source banks are not deducted and no command is sent.</p>
    </div>
  );
}
