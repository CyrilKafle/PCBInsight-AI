import type { Severity } from "./types";

// Shared severity ordering and colors, used by the board markers, the
// issues-by-category chart, and the issue browser's sort/filter. Kept in one
// place so the ranking and the palette can't drift between views.
export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#ef4444",
  high: "#f87171",
  medium: "#fb923c",
  low: "#facc15",
  info: "#9ca3af",
};
