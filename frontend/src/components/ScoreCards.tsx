import type { EngineeringScore } from "../types";

function scoreColor(value: number): string {
  if (value >= 90) return "text-green-400 border-green-500";
  if (value >= 75) return "text-yellow-400 border-yellow-500";
  if (value >= 50) return "text-orange-400 border-orange-500";
  return "text-red-400 border-red-500";
}

export function ScoreCards({ score }: { score: EngineeringScore }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
      <div className="mb-6 flex items-center gap-6">
        <div
          className={`flex h-24 w-24 flex-shrink-0 flex-col items-center justify-center rounded-full border-4 ${scoreColor(score.overall)}`}
        >
          <span className="text-2xl font-bold">{score.overall}</span>
          <span className="text-xs text-neutral-500">/ 100</span>
        </div>
        <div>
          <h2 className="text-lg font-semibold text-neutral-100">Overall Engineering Score</h2>
          <p className="text-sm text-neutral-500">Transparent, severity-weighted deduction score</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-7">
        {score.subscores.map((subscore) => (
          <div key={subscore.category} className={`rounded-lg border-2 p-3 text-center ${scoreColor(subscore.score)}`}>
            <div className="text-xl font-bold">{subscore.score}</div>
            <div className="mt-1 text-xs text-neutral-400">{subscore.category}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
