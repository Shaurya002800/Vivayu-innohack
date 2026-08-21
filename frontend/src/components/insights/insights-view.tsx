import { Icon } from "@/components/ui/icon";
import { formatNumber, formatPercent, titleCaseCode } from "@/lib/formatting";
import { irrigationFarmerLabel, strategyFarmerLabel } from "@/lib/presentation";
import type { DashboardSnapshot, ZoneId } from "@/types";

import { ZoneSelector } from "@/components/zones/zone-selector";

interface InsightsViewProps {
  snapshot: DashboardSnapshot;
  selectedZone: ZoneId;
  onSelectZone: (zoneId: ZoneId) => void;
}

function Reasons({ reasons, warnings }: { reasons: string[]; warnings: string[] }) {
  return (
    <div className="reason-copy">
      {reasons.length === 0 && warnings.length === 0 && <p>No explanation was supplied.</p>}
      {reasons.map((reason, index) => <p key={`reason-${index}`}><Icon name="check" />{reason}</p>)}
      {warnings.map((warning, index) => <p className="warning" key={`warning-${index}`}><Icon name="alert" />{warning}</p>)}
    </div>
  );
}

function Codes({ reasons, warnings }: { reasons: string[]; warnings: string[] }) {
  return (
    <div className="code-cloud">
      {[...reasons, ...warnings].map((code) => <code key={code}>{code}</code>)}
      {reasons.length === 0 && warnings.length === 0 && <span>None</span>}
    </div>
  );
}

export function InsightsView({ snapshot, selectedZone, onSelectZone }: InsightsViewProps) {
  const zone = snapshot.state.zones[selectedZone];
  const irrigation = snapshot.irrigation[selectedZone];
  const quality = snapshot.waterQuality[selectedZone];
  const allocation = snapshot.allocation.zones[selectedZone];
  const health = zone.vivayu_health;

  return (
    <div className="insights-view">
      <header className="view-heading">
        <div><span className="section-label">Explainable intelligence</span><h1>Understand every recommendation.</h1><p>Plain-language reasoning comes first. Model and policy codes stay available when an expert needs them.</p></div>
        <ZoneSelector snapshot={snapshot} selectedZone={selectedZone} onSelect={onSelectZone} compact />
      </header>

      <section className="decision-story" aria-label={`Decision path for Zone ${selectedZone}`}>
        <div className="story-step"><span><Icon name="drop" /></span><small>Soil</small><strong>{formatPercent(zone.telemetry.soil_moisture_pct, 1)}</strong></div>
        <Icon name="arrow" />
        <div className="story-step"><span><Icon name="seed" /></span><small>Crop stage</small><strong>{titleCaseCode(zone.crop_context?.growth_stage)}</strong></div>
        <Icon name="arrow" />
        <div className="story-step"><span><Icon name="weather" /></span><small>Weather</small><strong>{formatPercent(snapshot.state.weather.rain_probability_6h_pct)} rain</strong></div>
        <Icon name="arrow" />
        <div className="story-step story-outcome"><span><Icon name="insights" /></span><small>Recommendation</small><strong>{irrigationFarmerLabel(irrigation)}</strong></div>
      </section>

      <section className="insight-card-grid">
        <article className="insight-card">
          <div className="insight-number">01</div>
          <div className="panel-heading"><span>Irrigation need</span><small>Milestone 4</small></div>
          <h2>{irrigationFarmerLabel(irrigation)}</h2>
          <Reasons reasons={irrigation.reasons} warnings={irrigation.warnings} />
          <details><summary>Technical codes <Icon name="chevron" /></summary><Codes reasons={irrigation.reason_codes} warnings={irrigation.warning_codes} /></details>
        </article>

        <article className="insight-card">
          <div className="insight-number">02</div>
          <div className="panel-heading"><span>Water quality</span><small>Milestone 5</small></div>
          <h2>{strategyFarmerLabel(quality)}</h2>
          <Reasons reasons={quality.reasons} warnings={quality.warnings} />
          <details><summary>Technical codes <Icon name="chevron" /></summary><Codes reasons={quality.reason_codes} warnings={quality.warning_codes} /></details>
        </article>

        <article className="insight-card">
          <div className="insight-number">03</div>
          <div className="panel-heading"><span>Scarcity allocation</span><small>Milestone 6</small></div>
          <h2>{titleCaseCode(allocation.status)}</h2>
          <Reasons reasons={allocation.reasons} warnings={allocation.warnings} />
          <details><summary>Technical codes <Icon name="chevron" /></summary><Codes reasons={allocation.reason_codes} warnings={allocation.warning_codes} /></details>
        </article>
      </section>

      <section className="research-insight-card">
        <div className="research-heading">
          <span className="research-mark"><Icon name="leaf" /></span>
          <div><span className="section-label">Experimental plant-health signal</span><h2>Vivayu health · Zone {selectedZone}</h2></div>
          <span className="research-only-pill">Research only</span>
        </div>
        <div className="research-body">
          <div><small>Status</small><strong>{titleCaseCode(health.status)}</strong></div>
          <div><small>VOC pattern</small><strong>{health.pattern ?? "Unavailable"}</strong></div>
          <div><small>Risk</small><strong>{titleCaseCode(health.risk_level)}</strong></div>
          <div><small>Collection</small><strong>{health.readings_received}/{health.readings_required}</strong></div>
        </div>
        <p>{health.reason ?? health.research_score_note ?? "Compatible readings are processed independently for this zone."}</p>
        <div className="research-boundary-wide"><Icon name="shield" /> This research output never changes irrigation need, water strategy, allocation, or actuation.</div>
      </section>

      <section className="insight-support-grid">
        <article><Icon name="weather" /><span><small>Weather provider</small><strong>{snapshot.state.weather.provider ?? "Unavailable"}</strong><em>{snapshot.state.weather.status} · ET₀ {formatNumber(snapshot.state.weather.et0_6h_mm, 2, " mm")}</em></span></article>
        <article><Icon name="insights" /><span><small>Historical trends</small><strong>Not available yet</strong><em>No history endpoint exists; no chart has been invented.</em></span></article>
      </section>
    </div>
  );
}
