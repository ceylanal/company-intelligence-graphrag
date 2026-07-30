import { describe, expect, it } from "vitest";

import { apiUrl, getApiBaseUrl } from "@/lib/api/config";

describe("browser API configuration", () => {
  it("uses the same-origin BFF route for every backend path", () => {
    expect(getApiBaseUrl()).toBe("/api");
    expect(apiUrl("health/live")).toBe("/api/health/live");
    expect(apiUrl("/research/stream")).toBe("/api/research/stream");
  });
});
