import { titleCaseCode, toneForStatus, type StatusTone } from "@/lib/formatting";

interface StatusPillProps {
  label: string | null | undefined;
  tone?: StatusTone;
  pulse?: boolean;
}

export function StatusPill({ label, tone, pulse = false }: StatusPillProps) {
  const resolvedTone = tone ?? toneForStatus(label);
  return (
    <span className={`status-pill status-${resolvedTone}`}>
      <span className={`status-dot${pulse ? " status-dot-pulse" : ""}`} aria-hidden="true" />
      {titleCaseCode(label)}
    </span>
  );
}
