import { formatMl, formatNumber, formatPercent, titleCaseCode } from "@/lib/formatting";
import type { IrrigationNeedResult } from "@/types";

import { StatusPill } from "./status-pill";

export function IrrigationPanel({ result }: { result: IrrigationNeedResult }) {
  return (
    <section className="zone-subpanel">
      <div className="subpanel-heading">
        <div>
          <span className="step-label">M4</span>
          <h4>Irrigation need</h4>
        </div>
        <StatusPill label={result.status} />
      </div>
      <div className="compact-metrics three-up">
        <div>
          <span>Prototype request</span>
          <strong>{formatMl(result.requested_water_ml)}</strong>
        </div>
        <div>
          <span>Urgency</span>
          <strong>{titleCaseCode(result.urgency)}</strong>
        </div>
        <div>
          <span>Score</span>
          <strong>{formatPercent(result.urgency_score === null ? null : result.urgency_score * 100)}</strong>
        </div>
      </div>
      <div className="urgency-track" aria-label={`Urgency score ${formatNumber(result.urgency_score, 2)}`}>
        <span style={{ width: `${Math.max(0, Math.min(100, (result.urgency_score ?? 0) * 100))}%` }} />
      </div>
    </section>
  );
}
