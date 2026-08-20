import { compactCode, formatPercent, titleCaseCode } from "@/lib/formatting";
import type { VivayuHealthState } from "@/types";

import { StatusPill } from "./status-pill";

export function VivayuHealthCard({ health }: { health: VivayuHealthState }) {
  const progress = Math.min(100, (health.readings_received / health.readings_required) * 100);

  return (
    <section className="vivayu-panel">
      <div className="subpanel-heading">
        <div>
          <span className="step-label step-vivayu">M7</span>
          <h4>Vivayu research health</h4>
        </div>
        <div className="vivayu-badges">
          <span className="research-badge">Research only</span>
          <StatusPill label={health.status} />
        </div>
      </div>

      {health.status === "COLLECTING" && (
        <div className="vivayu-state-body">
          <div className="collection-copy">
            <strong>Collecting {health.readings_received}/{health.readings_required}</strong>
            <span>Compatible readings in isolated zone window</span>
          </div>
          <div className="collection-track"><span style={{ width: `${progress}%` }} /></div>
        </div>
      )}

      {health.status === "READY" && (
        <div className="compact-metrics vivayu-ready-grid">
          <div><span>VOC pattern</span><strong>{compactCode(health.pattern)}</strong></div>
          <div><span>Risk</span><strong>{titleCaseCode(health.risk_level)}</strong></div>
          <div><span>Research score</span><strong>{formatPercent(health.research_score === null ? null : health.research_score * 100, 1)}</strong></div>
          <div><span>Separation confidence</span><strong>{formatPercent(health.confidence_pct, 1)}</strong></div>
        </div>
      )}

      {(health.status === "UNAVAILABLE" || health.status === "ERROR") && (
        <div className="unavailable-message">
          <strong>{health.status === "ERROR" ? "Research model error" : "Compatible signal unavailable"}</strong>
          <span>{health.reason ?? "No compatible research signal is available."}</span>
        </div>
      )}

      <p className="research-disclaimer">
        Legacy VOC-pattern signal only. It is not a diagnosis and never controls irrigation.
      </p>
    </section>
  );
}
