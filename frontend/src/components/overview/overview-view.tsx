import { Icon } from "@/components/ui/icon";
import { formatLitres, formatPercent } from "@/lib/formatting";
import {
  attentionZoneCount,
  farmCondition,
  type ProductView,
} from "@/lib/presentation";
import type { DashboardSnapshot, ZoneId } from "@/types";

import { FarmStatusStrip } from "./farm-status-strip";
import { FarmVisual } from "./farm-visual";

interface OverviewViewProps {
  snapshot: DashboardSnapshot;
  stale: boolean;
  selectedZone: ZoneId;
  onSelectZone: (zoneId: ZoneId) => void;
  onNavigate: (view: ProductView) => void;
}

export function OverviewView({
  snapshot,
  stale,
  selectedZone,
  onSelectZone,
  onNavigate,
}: OverviewViewProps) {
  const condition = farmCondition(snapshot, stale);
  const state = snapshot.state;
  const attention = attentionZoneCount(snapshot);
  const selectZone = (zoneId: ZoneId) => {
    onSelectZone(zoneId);
    onNavigate("zones");
  };

  return (
    <div className="overview-view">
      <section className={`farm-hero condition-${condition.tone}`} aria-labelledby="farm-condition-title">
        <div className="hero-message">
          <span className="hero-eyebrow"><Icon name={condition.tone === "stable" ? "check" : "alert"} />{condition.eyebrow}</span>
          <h1 id="farm-condition-title">{condition.headline}</h1>
          <p>{condition.explanation}</p>
          {condition.view === "overview" ? (
            <div className="no-action-state"><Icon name="shield" /> No action needed</div>
          ) : (
            <button
              type="button"
              className="hero-action"
              onClick={() => {
                onSelectZone(condition.zoneId);
                onNavigate(condition.view);
              }}
            >
              {condition.action}<Icon name="arrow" />
            </button>
          )}
          <span className="planning-truth">Planning intelligence only · no irrigation started</span>
        </div>

        <FarmVisual snapshot={snapshot} selectedZone={selectedZone} onSelectZone={selectZone} />

        <aside className="hero-snapshot" aria-label="Key farm indicators">
          <div className="hero-metric hero-metric-water">
            <span><Icon name="drop" /> Water available</span>
            <strong>{formatLitres(state.water.fresh.available_l)}</strong>
            <small>Fresh · {formatLitres(state.water.marginal.available_l)} marginal</small>
          </div>
          <div className="hero-metric">
            <span><Icon name="weather" /> Next 6 hours</span>
            <strong>{formatPercent(state.weather.rain_probability_6h_pct)}</strong>
            <small>Chance of rain · {state.weather.status}</small>
          </div>
          <div className={`hero-metric${attention > 0 ? " metric-attention" : ""}`}>
            <span><Icon name={attention > 0 ? "alert" : "check"} /> Fields</span>
            <strong>{attention}</strong>
            <small>{attention === 1 ? "zone needs attention" : attention === 0 ? "zones need no action" : "zones need attention"}</small>
          </div>
          <div className="hero-system-line">
            <span className={`system-dot ${stale ? "offline" : ""}`} />
            <span><strong>{state.data_mode === "simulation" ? "Simulation" : state.controller.status}</strong><small>{stale ? "Last known snapshot" : "Backend connected"}</small></span>
            <button type="button" onClick={() => onNavigate("system")}>Details</button>
          </div>
        </aside>
      </section>

      <FarmStatusStrip snapshot={snapshot} />

      <section className="overview-followup">
        <div>
          <span className="section-label">Today’s farm plan</span>
          <h2>Complex decisions, translated clearly.</h2>
        </div>
        <p>
          Open a field for its moisture and irrigation recommendation, or inspect the water page to see how freshwater is being preserved.
        </p>
        <div className="overview-shortcuts">
          <button type="button" onClick={() => onNavigate("zones")}><Icon name="zones" /><span><strong>Inspect fields</strong><small>One zone at a time</small></span><Icon name="arrow" /></button>
          <button type="button" onClick={() => onNavigate("water")}><Icon name="water" /><span><strong>View water plan</strong><small>Sources, blend and scarcity</small></span><Icon name="arrow" /></button>
        </div>
      </section>
    </div>
  );
}
