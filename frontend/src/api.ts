import type { Board, EngineeringScore, Issue, ReviewResponse } from "./types";

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function submitReview(files: File[], includeAiReview: boolean): Promise<ReviewResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file, file.name);
  }
  formData.append("include_ai_review", String(includeAiReview));

  const response = await fetch("/api/review", { method: "POST", body: formData });
  return unwrap<ReviewResponse>(response);
}

export async function askQuestion(
  board: Board,
  issues: Issue[],
  score: EngineeringScore,
  question: string,
): Promise<string> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ board, issues, score, question }),
  });
  const { answer } = await unwrap<{ answer: string }>(response);
  return answer;
}
