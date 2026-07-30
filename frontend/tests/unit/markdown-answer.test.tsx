import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownAnswer } from "@/components/chat/markdown-answer";

describe("MarkdownAnswer", () => {
  it("renders safe tables and activates only citations with metadata", () => {
    const onCitation = vi.fn();
    render(
      <MarkdownAnswer
        answer={"## Bulgular\n\n| Metric | Value |\n|---|---|\n| Gelir | ₺10 |\n\nVerified [Source 1], absent [Source 9]."}
        citationIndexes={new Set([1])}
        onCitation={onCitation}
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open source 1" }));
    expect(onCitation).toHaveBeenCalledWith(1);
    expect(screen.getByTitle("Citation metadata unavailable")).toBeInTheDocument();
  });

  it("does not execute raw HTML", () => {
    render(
      <MarkdownAnswer
        answer={'<script>alert("unsafe")</script><img src=x onerror=alert(1)>'}
        citationIndexes={new Set()}
        onCitation={() => undefined}
      />,
    );
    expect(document.querySelector("script")).not.toBeInTheDocument();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });
});
