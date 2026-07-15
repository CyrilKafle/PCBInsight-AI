import { useState } from "react";
import { submitReview } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { IssueBrowser } from "./components/IssueBrowser";
import { ScoreCards } from "./components/ScoreCards";
import { UploadZone } from "./components/UploadZone";
import type { ReviewResponse } from "./types";

type Status = "idle" | "loading" | "error";

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [includeAiReview, setIncludeAiReview] = useState(false);

  async function handleFiles(files: File[]) {
    setStatus("loading");
    setError(null);
    try {
      const response = await submitReview(files, includeAiReview);
      setResult(response);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setStatus("error");
    }
  }

  function reset() {
    setResult(null);
    setError(null);
    setStatus("idle");
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-4">
        <h1 className="text-lg font-semibold">PCBInsight AI</h1>
        <p className="text-sm text-neutral-500">Automated KiCad PCB design review</p>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {!result && (
          <>
            <UploadZone onFilesSelected={handleFiles} disabled={status === "loading"} />
            <label className="flex items-center gap-2 text-sm text-neutral-400">
              <input
                type="checkbox"
                checked={includeAiReview}
                onChange={(event) => setIncludeAiReview(event.target.checked)}
                className="rounded border-neutral-600 bg-neutral-900"
              />
              Also generate a Claude narrative review (requires ANTHROPIC_API_KEY, costs an API call)
            </label>
            {status === "loading" && <p className="text-neutral-400">Analyzing board...</p>}
            {status === "error" && error && (
              <p className="rounded-md border border-red-900 bg-red-950/50 p-3 text-sm text-red-300">{error}</p>
            )}
          </>
        )}

        {result && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">{result.board.name}</h2>
              <button
                type="button"
                onClick={reset}
                className="rounded-md bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700"
              >
                Analyze another board
              </button>
            </div>
            <ScoreCards score={result.score} />
            {result.ai_review && (
              <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-400">AI Review</h3>
                <p className="whitespace-pre-wrap text-sm text-neutral-200">{result.ai_review}</p>
              </div>
            )}
            <IssueBrowser issues={result.issues} />
            <ChatPanel result={result} />
          </>
        )}
      </main>
    </div>
  );
}
