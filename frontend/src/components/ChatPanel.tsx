import { useRef, useState } from "react";
import { askQuestion } from "../api";
import type { ReviewResponse } from "../types";

// One turn in the conversation. History lives here in component state for the
// current browser session only -- the backend chat endpoint is stateless and
// answers each question against the board digest, not the thread.
interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  isError?: boolean;
}

const SUGGESTIONS = [
  "What is the most severe issue on this board?",
  "Summarize the power and ground findings.",
  "Which issues should I fix before sending this to fab?",
];

export function ChatPanel({ result }: { result: ReviewResponse }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || pending) return;

    setDraft("");
    setTurns((prev) => [...prev, { role: "user", text: trimmed }]);
    setPending(true);
    try {
      const answer = await askQuestion(result.board, result.issues, result.score, trimmed);
      setTurns((prev) => [...prev, { role: "assistant", text: answer }]);
    } catch (err) {
      // Fail gracefully inside the thread (e.g. no ANTHROPIC_API_KEY -> 502)
      // so the rest of the dashboard keeps working.
      const message = err instanceof Error ? err.message : "The chat request failed.";
      setTurns((prev) => [...prev, { role: "assistant", text: message, isError: true }]);
    } finally {
      setPending(false);
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
      });
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900">
      <div className="border-b border-neutral-800 px-6 py-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">Ask about this board</h3>
        <p className="mt-1 text-xs text-neutral-500">
          Grounded in the deterministic findings for {result.board.name}. Requires ANTHROPIC_API_KEY on the backend.
        </p>
      </div>

      <div ref={scrollRef} className="max-h-96 space-y-3 overflow-y-auto px-6 py-4">
        {turns.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-neutral-500">Try a question:</p>
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => send(suggestion)}
                disabled={pending}
                className="block w-full rounded-md border border-neutral-800 bg-neutral-950 px-3 py-2 text-left text-sm text-neutral-300 hover:border-neutral-700 disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : (
          turns.map((turn, index) => (
            <div key={index} className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm " +
                  (turn.role === "user"
                    ? "bg-blue-600 text-white"
                    : turn.isError
                      ? "border border-red-900 bg-red-950/50 text-red-300"
                      : "bg-neutral-800 text-neutral-200")
                }
              >
                {turn.text}
              </div>
            </div>
          ))
        )}
        {pending && <p className="text-sm text-neutral-500">Thinking...</p>}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          send(draft);
        }}
        className="flex gap-2 border-t border-neutral-800 px-6 py-4"
      >
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask a question about this board..."
          disabled={pending}
          className="flex-1 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={pending || !draft.trim()}
          className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
