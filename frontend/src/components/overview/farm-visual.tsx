import { Icon } from "@/components/ui/icon";
import { formatPercent } from "@/lib/formatting";
import { irrigationFarmerLabel, irrigationTone, zoneDisplayName } from "@/lib/presentation";
import type { DashboardSnapshot, ZoneId } from "@/types";

interface FarmVisualProps {
  snapshot: DashboardSnapshot;
  selectedZone: ZoneId;
  onSelectZone: (zoneId: ZoneId) => void;
}

export function FarmVisual({ snapshot, selectedZone, onSelectZone }: FarmVisualProps) {
  return (
    <div className="farm-visual" aria-label="Interactive two-zone farm overview">
      <div className="farm-visual-sun" aria-hidden="true" />
      <div className="farm-water-line" aria-hidden="true">
        <span /><span /><span />
      </div>
      {(["A", "B"] as ZoneId[]).map((zoneId) => {
        const zone = snapshot.state.zones[zoneId];
        const irrigation = snapshot.irrigation[zoneId];
        const tone = irrigationTone(irrigation);
        return (
          <button
            type="button"
            key={zoneId}
            className={`field-plot field-${zoneId.toLowerCase()} tone-${tone}${selectedZone === zoneId ? " selected" : ""}`}
            onClick={() => onSelectZone(zoneId)}
            aria-label={`${zoneDisplayName(zone)}, moisture ${formatPercent(zone.telemetry.soil_moisture_pct, 1)}, ${irrigationFarmerLabel(irrigation)}`}
          >
            <span className="field-grid" aria-hidden="true" />
            <span className="field-copy">
              <small>Zone {zoneId}</small>
              <strong>{zone.crop_context?.crop_name ?? "Crop unavailable"}</strong>
              <em>{formatPercent(zone.telemetry.soil_moisture_pct, 1)} moisture</em>
            </span>
            <span className="field-state">
              <Icon name={tone === "stable" ? "check" : "alert"} />
              {irrigationFarmerLabel(irrigation)}
            </span>
          </button>
        );
      })}
      <div className="farm-pump" aria-hidden="true"><Icon name="drop" /></div>
      <span className="farm-visual-label">Tap a field to inspect it</span>
    </div>
  );
}
