import { compactCode } from "@/lib/formatting";
import type { DashboardSnapshot, ZoneId } from "@/types";

interface ExplanationGroupProps {
  label: string;
  codes: string[];
  reasons: string[];
  warnings?: string[];
}

function ExplanationGroup({ label, codes, reasons, warnings = [] }: ExplanationGroupProps) {
  return (
    <div className="explanation-group">
      <h4>{label}</h4>
      <ul className="reason-list">
        {reasons.map((reason, index) => (
          <li key={`${codes[index] ?? label}-${index}`}>
            <span className="reason-index">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <code>{compactCode(codes[index])}</code>
              <p>{reason}</p>
            </div>
          </li>
        ))}
      </ul>
      {warnings.map((warning, index) => (
        <p className="backend-warning" key={`${warning}-${index}`}>{warning}</p>
      ))}
    </div>
  );
}

function ZoneExplanations({ zoneId, snapshot }: { zoneId: ZoneId; snapshot: DashboardSnapshot }) {
  const irrigation = snapshot.irrigation[zoneId];
  const quality = snapshot.waterQuality[zoneId];
  const allocation = snapshot.allocation.zones[zoneId];

  return (
    <article className="zone-explanations">
      <header>
        <span className="zone-letter small-letter">{zoneId}</span>
        <div><p>Decision trace</p><h3>Zone {zoneId} explainability</h3></div>
      </header>
      <ExplanationGroup
        label="Why irrigation is or is not needed"
        codes={irrigation.reason_codes}
        reasons={irrigation.reasons}
        warnings={irrigation.warnings}
      />
      <ExplanationGroup
        label="Why this water strategy"
        codes={quality.reason_codes}
        reasons={quality.reasons}
        warnings={quality.warnings}
      />
      <ExplanationGroup
        label="Why this allocation"
        codes={allocation.reason_codes}
        reasons={allocation.reasons}
        warnings={allocation.warnings}
      />
    </article>
  );
}

export function ExplanationPanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  return (
    <section className="explanation-panel panel" aria-labelledby="explain-title">
      <div className="section-title-row compact-title-row">
        <div>
          <p className="section-kicker">Backend-authored reasons only</p>
          <h2 id="explain-title">Why the system planned this</h2>
        </div>
        <span className="machine-readable-badge">Machine-readable + human-readable</span>
      </div>
      <div className="explanation-grid">
        <ZoneExplanations zoneId="A" snapshot={snapshot} />
        <ZoneExplanations zoneId="B" snapshot={snapshot} />
      </div>
      <div className="global-explanation">
        <strong>Global allocation rationale</strong>
        <div>
          {snapshot.allocation.reasons.map((reason, index) => (
            <span key={`${snapshot.allocation.reason_codes[index]}-${index}`}>{reason}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
