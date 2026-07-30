import { describe, expect, it, vi } from "vitest";

import { parseNdjsonStream } from "@/lib/streaming/ndjson";

function stream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

describe("parseNdjsonStream", () => {
  it("parses events split across network chunks and ignores malformed lines", async () => {
    const onEvent = vi.fn();
    const onMalformedLine = vi.fn();
    await parseNdjsonStream(
      stream([
        '{"type":"accepted","run_id":"run_1",',
        '"request_id":"req_1","safety_action":"allow"}\nnot-json\n',
        '{"type":"answer_delta","delta":"Merhaba Şişecam"}\n',
      ]),
      { onEvent, onMalformedLine },
    );
    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent.mock.calls[1][0]).toEqual({ type: "answer_delta", delta: "Merhaba Şişecam" });
    expect(onMalformedLine).toHaveBeenCalledWith("not-json");
  });
});
