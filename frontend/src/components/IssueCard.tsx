import { useEffect, useRef, useState } from "react";
import type { Issue } from "../types";
import { SeverityBadge } from "./SeverityBadge";

export function IssueCard({
  issue,
  selected = false,
  onSelect,
}: {
  issue: Issue;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // When this card becomes the selected one (e.g. its marker was clicked on
  // the board view), open it and bring it into view.
  useEffect(() => {
    if (selected) {
      setExpanded(true);
      ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [selected]);

  const open = expanded || selected;
  const hasLocation = issue.location != null;

  return (
    <div
      ref={ref}
      className={`rounded-lg border bg-neutral-900 ${selected ? "border-blue-500 ring-1 ring-blue-500" : "border-neutral-800"}`}
    >
      <button
        type="button"
        onClick={() => {
          setExpanded((value) => !value);
          onSelect?.(issue.id);
        }}
        className="flex w-full items-start gap-3 p-4 text-left"
      >
        <SeverityBadge severity={issue.severity} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <code className="text-xs text-neutral-500">{issue.id}</code>
            <span className="text-xs uppercase tracking-wide text-neutral-500">
              {issue.category.replace(/_/g, " ")}
            </span>
            {hasLocation && <span className="text-xs text-blue-400" title="Has a location on the board view">◎</span>}
          </div>
          <p className="mt-0.5 font-medium text-neutral-100">{issue.summary}</p>
        </div>
        <span className="flex-shrink-0 text-neutral-500">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-neutral-800 px-4 py-3 text-sm">
          <p className="text-neutral-300">
            <span className="font-semibold text-neutral-400">Why it matters: </span>
            {issue.explanation}
          </p>
          <p className="italic text-neutral-400">{issue.principle}</p>
          <p className="text-neutral-300">
            <span className="font-semibold text-neutral-400">Suggested fix: </span>
            {issue.suggested_fix}
          </p>
          {issue.refs.length > 0 && <p className="text-xs text-neutral-500">Refs: {issue.refs.join(", ")}</p>}
          <p className="text-xs text-neutral-500">Confidence: {Math.round(issue.confidence * 100)}%</p>
        </div>
      )}
    </div>
  );
}
