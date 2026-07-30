import { apiUrl } from "@/lib/api/config";
import { parseNdjsonStream } from "@/lib/streaming/ndjson";
import type { Company, ConversationTurn, StreamEvent } from "@/lib/types/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message);
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let detail = "";
  try {
    const payload = (await response.json()) as { detail?: string };
    detail = payload.detail ?? "";
  } catch {
    detail = "";
  }
  const messages: Record<number, string> = {
    401: "Authentication is required by the research service.",
    403: "This research request is not permitted.",
    408: "The research request timed out.",
    409: "This request conflicts with an existing research run.",
    413: "The question or conversation is too large.",
    422: detail.toLowerCase().includes("safety")
      ? "The request was declined by the safety policy."
      : "The research request is invalid.",
    429: "The research service is busy. Please wait and retry.",
    503: "The research service is temporarily unavailable.",
  };
  return new ApiError(
    response.status,
    messages[response.status] ?? "The research request could not be completed.",
    response.headers.get("x-request-id") ?? undefined,
  );
}

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch(apiUrl("/health/live"), {
    signal,
    cache: "no-store",
  });
  return response.ok;
}

export async function getCompanies(signal?: AbortSignal): Promise<Company[]> {
  const response = await fetch(apiUrl("/research/companies"), {
    signal,
    cache: "no-store",
  });
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as Company[];
}

export async function streamResearch(
  input: {
    query: string;
    history?: ConversationTurn[];
    idempotencyKey: string;
  },
  callbacks: {
    onEvent: (event: StreamEvent) => void;
    onMalformedLine: (line: string) => void;
  },
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl("/research/stream"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": input.idempotencyKey,
    },
    body: JSON.stringify({ query: input.query, history: input.history ?? [] }),
    signal,
  });
  if (!response.ok) throw await errorFromResponse(response);
  if (!response.body) throw new ApiError(502, "The research stream returned no response body.");
  await parseNdjsonStream(response.body, callbacks);
}
