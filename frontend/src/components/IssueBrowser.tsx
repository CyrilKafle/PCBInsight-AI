import { useMemo, useState } from "react";
import type { Issue, Severity } from "../types";
import { IssueCard } from "./IssueCard";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function IssueBrowser({ issues }: { issues: Issue[] }) {
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");

  const categories = useMemo(() => Array.from(new Set(issues.map((issue) => issue.category))).sort(), [issues]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return issues
      .filter((issue) => categoryFilter === "all" || issue.category === categoryFilter)
      .filter((issue) => severityFilter === "all" || issue.severity === severityFilter)
      .filter((issue) => {
        if (!q) return true;
        return (
          issue.summary.toLowerCase().includes(q) ||
          issue.id.toLowerCase().includes(q) ||
          issue.refs.some((ref) => ref.toLowerCase().includes(q))
        );
      })
      .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));
  }, [issues, query, categoryFilter, severityFilter]);

  if (issues.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6 text-center text-neutral-400">
        No issues found by the deterministic check engine.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          placeholder="Search by refdes, net, ID, or keyword..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="min-w-[200px] flex-1 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-blue-500 focus:outline-none"
        />
        <select
          value={categoryFilter}
          onChange={(event) => setCategoryFilter(event.target.value)}
          className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100"
        >
          <option value="all">All categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={severityFilter}
          onChange={(event) => setSeverityFilter(event.target.value)}
          className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100"
        >
          <option value="all">All severities</option>
          {SEVERITY_ORDER.map((severity) => (
            <option key={severity} value={severity}>
              {severity}
            </option>
          ))}
        </select>
      </div>
      <p className="text-xs text-neutral-500">
        {filtered.length} of {issues.length} issue{issues.length === 1 ? "" : "s"}
      </p>
      <div className="space-y-2">
        {filtered.map((issue) => (
          <IssueCard key={issue.id} issue={issue} />
        ))}
      </div>
    </div>
  );
}
