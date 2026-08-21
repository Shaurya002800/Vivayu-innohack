import { formatPercent } from "@/lib/formatting";
import { irrigationFarmerLabel, irrigationTone, zoneDisplayName } from "@/lib/presentation";
import type { DashboardSnapshot, ZoneId } from "@/types";

interface ZoneSelectorProps {
  snapshot: DashboardSnapshot;
  selectedZone: ZoneId;
  onSelect: (zoneId: ZoneId) => void;
  compact?: boolean;
}

export function ZoneSelector({ snapshot, selectedZone, onSelect, compact = false }: ZoneSelectorProps) {
  return (
    <div className={`zone-selector${compact ? " compact" : ""}`} role="tablist" aria-label="Choose a farm zone">
      {(["A", "B"] as ZoneId[]).map((zoneId) => {
        const zone = snapshot.state.zones[zoneId];
        const irrigation = snapshot.irrigation[zoneId];
        const active = selectedZone === zoneId;
        return (
          <button
            type="button"
            role="tab"
            aria-selected={active}
            className={`zone-selector-button tone-${irrigationTone(irrigation)}${active ? " active" : ""}`}
            key={zoneId}
            onClick={() => onSelect(zoneId)}
          >
            <span className="zone-selector-letter">{zoneId}</span>
            <span>
              <strong>{zoneDisplayName(zone)}</strong>
              {!compact && <small>{zone.crop_context?.crop_name ?? "Crop unavailable"}</small>}
            </span>
            <span className="zone-selector-state">
              <strong>{formatPercent(zone.telemetry.soil_moisture_pct, 1)}</strong>
              {!compact && <small>{irrigationFarmerLabel(irrigation)}</small>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
