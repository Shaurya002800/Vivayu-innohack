import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "overview"
  | "zones"
  | "water"
  | "insights"
  | "system"
  | "leaf"
  | "drop"
  | "weather"
  | "alert"
  | "check"
  | "arrow"
  | "signal"
  | "power"
  | "thermometer"
  | "humidity"
  | "seed"
  | "shield"
  | "chevron"
  | "menu";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
}

export function Icon({ name, ...props }: IconProps) {
const paths: Record<IconName, ReactNode> = {
    overview: <><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></>,
    zones: <><path d="M4 6 10 3l6 3-6 3-6-3Z" /><path d="m10 9 6-3 4 2-10 5L4 10" /><path d="m10 13 10-5v7l-10 5-6-3v-7" /></>,
    water: <path d="M12 3S6.5 9.2 6.5 14a5.5 5.5 0 0 0 11 0C17.5 9.2 12 3 12 3Z" />,
    insights: <><path d="M5 19V9m5 10V5m5 14v-7m4 7V8" /><path d="m4 7 6-4 5 6 5-4" /></>,
    system: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H3v-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.5V3h4v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    leaf: <><path d="M5 20c8 0 14-5 14-15C9 5 5 10 5 20Z" /><path d="M5 20c3-5 6-7 10-10" /></>,
    drop: <path d="M12 3S6 9.4 6 14a6 6 0 0 0 12 0c0-4.6-6-11-6-11Z" />,
    weather: <><path d="M7 18h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 11.5 3.5 3.5 0 0 0 7 18Z" /><path d="m8 21-1 1m5-1-1 1m5-1-1 1" /></>,
    alert: <><path d="M12 3 2.8 20h18.4L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    arrow: <><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></>,
    signal: <><path d="M5 12.6a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0" /><circle cx="12" cy="20" r="1" /></>,
    power: <><path d="M12 2v9" /><path d="M7 5.5a8 8 0 1 0 10 0" /></>,
    thermometer: <><path d="M10 14.8V5a2 2 0 0 1 4 0v9.8a4 4 0 1 1-4 0Z" /><path d="M12 10v7" /></>,
    humidity: <path d="M12 3S7 9 7 13a5 5 0 0 0 10 0c0-4-5-10-5-10Z" />,
    seed: <><path d="M12 21V10" /><path d="M12 13c-5 0-7-3-7-7 5 0 7 3 7 7Zm0 3c5 0 7-3 7-7-5 0-7 3-7 7Z" /></>,
    shield: <><path d="M12 3 5 6v5c0 4.5 2.8 8 7 10 4.2-2 7-5.5 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-5" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
