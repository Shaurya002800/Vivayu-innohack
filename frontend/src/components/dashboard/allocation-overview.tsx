import { clampPercent, formatMl, formatRatio } from "@/lib/formatting";
import type { FreshwaterAllocationResult, ZoneId } from "@/types";

import { StatusPill } from "./status-pill";

function BankBar({ allocated, available, className }: { allocated: number; available: number | null; className: string }) {
  const percent = available === null || available === 0 ? null : (allocated / available) * 100;
  return (
    <div className={`bank-track ${className}`}>
      {percent !== null && <span style={{ width: `${clampPercent(percent)}%` }} />}
    </div>
  );
}

function ZoneService({ zoneId, result }: { zoneId: ZoneId; result: FreshwaterAllocationResult }) {
  const allocation = result.zones[zoneId];
  return (
    <div className="allocation-zone-row">
      <span className="allocation-zone-name">Zone {zoneId}</span>
      <div className="allocation-zone-track"><span style={{ width: `${clampPercent((allocation.service_fraction ?? 0) * 100)}%` }} /></div>
      <strong>{formatRatio(allocation.service_fraction)}</strong>
      <small>{formatMl(allocation.deliverable_water_ml)} / {formatMl(allocation.requested_water_ml)}</small>
    </div>
  );
}

export function AllocationOverview({ allocation }: { allocation: FreshwaterAllocationResult }) {
  return (
    <section className="allocation-overview panel" aria-labelledby="allocation-title">
      <div className="section-title-row compact-title-row">
        <div>
          <p className="section-kicker">Multi-zone resource planning</p>
          <h2 id="allocation-title">Freshwater allocation overview</h2>
        </div>
        <StatusPill
          label={allocation.scarcity_active === null ? "Availability unknown" : allocation.scarcity_active ? "Scarcity active" : "Capacity sufficient"}
          tone={allocation.scarcity_active === null ? "neutral" : allocation.scarcity_active ? "warning" : "positive"}
        />
      </div>

      <div className="allocation-layout">
        <div className="bank-stack">
          <div className="bank-row">
            <div className="bank-copy">
              <span>Freshwater</span>
              <strong>{formatMl(allocation.freshwater_allocated_ml)} allocated</strong>
              <small>{formatMl(allocation.freshwater_available_ml)} available · {formatMl(allocation.freshwater_required_for_full_service_ml)} required for full service</small>
            </div>
            <strong className="bank-remaining">{formatMl(allocation.freshwater_remaining_ml)}<small>remaining</small></strong>
            <BankBar allocated={allocation.freshwater_allocated_ml} available={allocation.freshwater_available_ml} className="fresh-bank" />
          </div>
          <div className="bank-row">
            <div className="bank-copy">
              <span>Marginal-quality water</span>
              <strong>{formatMl(allocation.marginal_allocated_ml)} allocated</strong>
              <small>{formatMl(allocation.marginal_available_ml)} available · {formatMl(allocation.marginal_required_for_full_service_ml)} required for full service</small>
            </div>
            <strong className="bank-remaining">{formatMl(allocation.marginal_remaining_ml)}<small>remaining</small></strong>
            <BankBar allocated={allocation.marginal_allocated_ml} available={allocation.marginal_available_ml} className="marginal-bank" />
          </div>
        </div>

        <div className="delivery-summary">
          <div className="delivery-total">
            <span>Total deliverable</span>
            <strong>{formatMl(allocation.total_deliverable_water_ml)}</strong>
            <small>of {formatMl(allocation.total_requested_water_ml)} requested</small>
          </div>
          <ZoneService zoneId="A" result={allocation} />
          <ZoneService zoneId="B" result={allocation} />
        </div>
      </div>
      <p className="preview-boundary">Read-only planning preview · source banks are not deducted · safe source ratios are preserved during partial delivery.</p>
    </section>
  );
}
