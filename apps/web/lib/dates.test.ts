import { describe, expect, it } from "vitest";

import { formatAsOf, formatObserved } from "./dates";

describe("operator timestamp formatting", () => {
  it("uses the region timezone instead of the server or browser timezone", () => {
    const observedAt = "2026-08-12T12:00:00Z";

    expect(formatAsOf(observedAt, "America/Chicago")).toBe(
      "Aug 12, 2026, 7:00 AM CDT",
    );
    expect(formatObserved(observedAt, "America/Chicago")).toBe("Aug 12, 2026");
  });
});
