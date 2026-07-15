import { useMemo } from "react";
import { SEVERITY_COLORS, SEVERITY_ORDER } from "../severity";
import type { Issue, Severity } from "../types";

// Issue count per category, each bar segmented by severity. Answers "where are
// the problems concentrated?" at a glance -- counts only, no new judgement.
export function IssueCategoryChart({ issues }: { issues: Issue[] }) {
  const { rows, max } = useMemo(() => {
    const byCategory = new Map<string, Record<Severity, number>>();
    for (const issue of issues) {
      const counts =
        byCategory.get(issue.category) ??
        ({ critical: 0, high: 0, medium: 0, low: 0, info: 0 } as Record<Severity, number>);
      counts[issue.severity] += 1;
      byCategory.set(issue.category, counts);
    }
    const rows = Array.from(byCategory.entries())
      .map(([category, counts]) => ({
        category,
        counts,
        total: SEVERITY_ORDER.reduce((sum, sev) => sum + counts[sev], 0),
      }))
      .sort((a, b) => b.total - a.total);
    return { rows, max: Math.max(1, ...rows.map((row) => row.total)) };
  }, [issues]);

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6 text-center text-sm text-neutral-500">
        No issues to chart — the board is clean.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">Issues by category</h3>
      <div className="mt-4 space-y-2">
        {rows.map((row) => (
          <div key={row.category} className="flex items-center gap-3">
            <span className="w-32 flex-shrink-0 truncate text-xs text-neutral-400" title={row.category}>
              {row.category.replace(/_/g, " ")}
            </span>
            <div className="flex h-5 flex-1 overflow-hidden rounded bg-neutral-950">
              {SEVERITY_ORDER.map((severity) =>
                row.counts[severity] > 0 ? (
                  <div
                    key={severity}
                    style={{ width: `${(row.counts[severity] / max) * 100}%`, backgroundColor: SEVERITY_COLORS[severity] }}
                    title={`${row.counts[severity]} ${severity}`}
                  />
                ) : null,
              )}
            </div>
            <span className="w-6 flex-shrink-0 text-right text-xs text-neutral-400">{row.total}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-3 text-[10px] text-neutral-500">
        {SEVERITY_ORDER.map((severity) => (
          <span key={severity} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: SEVERITY_COLORS[severity] }} />
            {severity}
          </span>
        ))}
      </div>
    </div>
  );
}
