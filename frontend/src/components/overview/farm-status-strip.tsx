import { Icon, type IconName } from "@/components/ui/icon";
import { formatLitres, formatMl, formatPercent } from "@/lib/formatting";
import type { DashboardSnapshot } from "@/types";

interface StripItemProps {
  icon: IconName;
  label: string;
  value: string;
  detail: string;
}

function StripItem({ icon, label, value, detail }: StripItemProps) {
  return (
    <div className="status-strip-item">
      <span className="strip-icon"><Icon name={icon} /></span>
      <span><small>{label}</small><strong>{value}</strong><em>{detail}</em></span>
    </div>
  );
}

export function FarmStatusStrip({ snapshot }: { snapshot: DashboardSnapshot }) {
  const state = snapshot.state;
  return (
    <section className="farm-status-strip" aria-label="Farm status at a glance">
      <StripItem icon="drop" label="Freshwater" value={formatLitres(state.water.fresh.available_l)} detail="Available bank" />
      <StripItem icon="water" label="Marginal water" value={formatLitres(state.water.marginal.available_l)} detail="Available bank" />
      <StripItem icon="weather" label="Rain next 6h" value={formatPercent(state.weather.rain_probability_6h_pct)} detail={state.weather.status} />
      <StripItem icon="zones" label="Farm demand" value={formatMl(snapshot.allocation.total_requested_water_ml)} detail="Planning request" />
      <StripItem icon="shield" label="Controller" value={state.controller.status} detail={state.data_mode === "simulation" ? "No physical commands" : state.controller.ready ? "Ready" : "Not ready"} />
    </section>
  );
}
