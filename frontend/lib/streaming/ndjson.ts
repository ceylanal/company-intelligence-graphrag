import type { StreamEvent } from "@/lib/types/api";

export interface ParseCallbacks {
  onEvent: (event: StreamEvent) => void;
  onMalformedLine?: (line: string) => void;
}

function isStreamEvent(value: unknown): value is StreamEvent {
  return Boolean(
    value &&
      typeof value === "object" &&
      "type" in value &&
      typeof (value as { type?: unknown }).type === "string",
  );
}

export async function parseNdjsonStream(
  stream: ReadableStream<Uint8Array>,
  callbacks: ParseCallbacks,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consumeLine = (rawLine: string) => {
    const line = rawLine.trim();
    if (!line) return;
    try {
      const parsed: unknown = JSON.parse(line);
      if (isStreamEvent(parsed)) callbacks.onEvent(parsed);
      else callbacks.onMalformedLine?.(line);
    } catch {
      callbacks.onMalformedLine?.(line);
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      lines.forEach(consumeLine);
      if (done) break;
    }
    if (buffer) consumeLine(buffer);
  } finally {
    reader.releaseLock();
  }
}
