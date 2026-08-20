import { formatMl, formatNumber, formatRatio } from "@/lib/formatting";
import type { WaterQualityResult } from "@/types";

import { StatusPill } from "./status-pill";

export function WaterStrategy({ result }: { result: WaterQualityResult }) {
  const hasRatio = result.fresh_fraction !== null && result.marginal_fraction !== null;
  const freshWidth = (result.fresh_fraction ?? 0) * 100;

  return (
    <section className="zone-subpanel">
      <div className="subpanel-heading">
        <div>
          <span className="step-label step-water">M5</span>
          <h4>Water-quality strategy</h4>
        </div>
        <StatusPill label={result.strategy} />
      </div>

      <div className="source-ratio" aria-label="Required safe water-source ratio">
        {hasRatio ? (
          <>
            <span className="ratio-fresh" style={{ width: `${freshWidth}%` }} />
            <span className="ratio-marginal" style={{ width: `${100 - freshWidth}%` }} />
          </>
        ) : (
          <span className="ratio-unavailable" />
        )}
      </div>
      <div className="ratio-legend">
        <span><i className="fresh-swatch" /> Fresh {formatRatio(result.fresh_fraction)}</span>
        <span><i className="marginal-swatch" /> Marginal {formatRatio(result.marginal_fraction)}</span>
      </div>

      <div className="compact-metrics three-up">
        <div>
          <span>Fresh required</span>
          <strong>{formatMl(result.fresh_ml)}</strong>
        </div>
        <div>
          <span>Marginal required</span>
          <strong>{formatMl(result.marginal_ml)}</strong>
        </div>
        <div>
          <span>Predicted TDS</span>
          <strong>{formatNumber(result.predicted_tds_ppm, 0, " ppm")}</strong>
        </div>
      </div>
      <div className="hardware-truth-row">
        <span>Measured mix TDS</span>
        <strong>Pending hardware</strong>
      </div>
    </section>
  );
}
