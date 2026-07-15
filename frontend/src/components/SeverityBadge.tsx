import type { Severity } from "../types";

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: "bg-red-900 text-red-200",
  high: "bg-red-800/70 text-red-200",
  medium: "bg-orange-800/70 text-orange-200",
  low: "bg-yellow-800/60 text-yellow-200",
  info: "bg-neutral-700 text-neutral-300",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${SEVERITY_STYLES[severity]}`}
    >
      {severity}
    </span>
  );
}
