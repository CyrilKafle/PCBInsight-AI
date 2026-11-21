import type { EngineeringScore, Issue } from "../types";
import { SEVERITY_COLORS, SEVERITY_ORDER } from "../severity";

const TOP_FINDINGS_LIMIT = 3;

function scoreColor(value: number | null): string {
  if (value === null) return "text-neutral-500 border-neutral-700";
  if (value >= 90) return "text-green-400 border-green-500";
  if (value >= 75) return "text-yellow-400 border-yellow-500";
  if (value >= 50) return "text-orange-400 border-orange-500";
  return "text-red-400 border-red-500";
}

// Same rule as top_findings() in backend/app/analysis/scoring.py: the findings
// at the highest severity present, higher confidence first, so the average
// below cannot hide them.
function topFindings(issues: Issue[]): { top: Issue[]; total: number } {
  if (issues.length === 0) return { top: [], total: 0 };
  const worst = SEVERITY_ORDER.find((sev) => issues.some((i) => i.severity === sev))!;
  const atWorst = issues
    .filter((i) => i.severity === worst)
    .sort((a, b) => b.confidence - a.confidence || a.id.localeCompare(b.id));
  return { top: atWorst.slice(0, TOP_FINDINGS_LIMIT), total: atWorst.length };
}

export function ScoreCards({ score, issues }: { score: EngineeringScore; issues: Issue[] }) {
  const evaluated = score.subscores.filter((s) => s.score !== null);
  const notEvaluated = score.subscores.filter((s) => s.score === null).map((s) => s.category);
  const { top, total } = topFindings(issues);
  const version = score.formula_version ?? 1;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
      {top.length > 0 && (
        <div
          className="mb-5 rounded-md border-l-4 bg-neutral-950/60 p-3 text-sm"
          style={{ borderColor: SEVERITY_COLORS[top[0].severity] }}
        >
          <p className="mb-1 font-semibold capitalize" style={{ color: SEVERITY_COLORS[top[0].severity] }}>
            Most severe: {total} {top[0].severity}
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-neutral-300">
            {top.map((issue) => (
              <li key={issue.id}>
                <code className="text-neutral-400">{issue.id}</code> {issue.summary}
              </li>
            ))}
          </ul>
          {total > top.length && (
            <p className="mt-1 text-neutral-500">
              and {total - top.length} more {top[0].severity}
            </p>
          )}
        </div>
      )}
      <div className="mb-6 flex items-center gap-6">
        <div
          className={`flex h-24 w-24 flex-shrink-0 flex-col items-center justify-center rounded-full border-4 ${scoreColor(score.overall)}`}
        >
          <span className="text-2xl font-bold">{score.overall}</span>
          <span className="text-xs text-neutral-500">/ 100</span>
        </div>
        <div>
          <h2 className="text-lg font-semibold text-neutral-100">Overall Engineering Score</h2>
          <p className="text-sm text-neutral-500">
            Mean of the {evaluated.length} evaluated subscores (formula v{version}).
            {notEvaluated.length > 0 && ` N/A (no checks yet): ${notEvaluated.join(", ")}.`}
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-7">
        {score.subscores.map((subscore) => (
          <div
            key={subscore.category}
            className={`rounded-lg border-2 p-3 text-center ${scoreColor(subscore.score)}`}
            title={subscore.score === null ? "Not evaluated: no checks feed this subscore" : undefined}
          >
            <div className="text-xl font-bold">{subscore.score ?? "N/A"}</div>
            <div className="mt-1 text-xs text-neutral-400">{subscore.category}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
