import { Icon, type IconName } from "@/components/ui/icon";
import type { ProductView } from "@/lib/presentation";

const items: { id: ProductView; label: string; icon: IconName }[] = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "zones", label: "Zones", icon: "zones" },
  { id: "water", label: "Water", icon: "water" },
  { id: "insights", label: "Insights", icon: "insights" },
  { id: "system", label: "System", icon: "system" },
];

interface ProductNavigationProps {
  activeView: ProductView;
  onChange: (view: ProductView) => void;
  mobile?: boolean;
}

export function ProductNavigation({ activeView, onChange, mobile = false }: ProductNavigationProps) {
  return (
    <nav className={mobile ? "mobile-navigation" : "product-navigation"} aria-label="Main product sections">
      {items.map((item) => (
        <button
          type="button"
          key={item.id}
          className={activeView === item.id ? "active" : ""}
          aria-current={activeView === item.id ? "page" : undefined}
          onClick={() => onChange(item.id)}
        >
          <Icon name={item.icon} />
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
