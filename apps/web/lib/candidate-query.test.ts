import { describe, expect, it } from "vitest";

import {
  CANDIDATE_PAGE_SIZE,
  buildCandidateApiQuery,
  buildCandidateExplorerHref,
  hasCandidateFilters,
  parseCandidateQuery,
} from "./candidate-query";

describe("candidate cohort query", () => {
  it("parses a single bounded-page query without retaining blank values", () => {
    expect(
      parseCandidateQuery({
        q: "  parcel 42 ",
        city: ["MANOR", "DEL VALLE"],
        min_acres: "1.5",
        max_acres: "12",
        cursor: "opaque-page-token",
      }),
    ).toEqual({
      q: "parcel 42",
      city: "MANOR",
      minAcres: 1.5,
      maxAcres: 12,
      cursor: "opaque-page-token",
    });

    expect(parseCandidateQuery({ q: " ", min_acres: "not-a-number" })).toEqual({
      q: null,
      city: null,
      minAcres: null,
      maxAcres: null,
      cursor: null,
    });
  });

  it("maps camel-case view filters to the exact snake-case API query", () => {
    const query = buildCandidateApiQuery({
      q: "FM 973",
      city: "DEL VALLE",
      minAcres: 2,
      maxAcres: 20.5,
      cursor: "eyJvZmZzZXQiOjUwfQ",
    });
    const params = new URLSearchParams(query);

    expect(params.get("limit")).toBe(String(CANDIDATE_PAGE_SIZE));
    expect(params.get("q")).toBe("FM 973");
    expect(params.get("city")).toBe("DEL VALLE");
    expect(params.get("min_acres")).toBe("2");
    expect(params.get("max_acres")).toBe("20.5");
    expect(params.get("cursor")).toBe("eyJvZmZzZXQiOjUwfQ");
    expect(params.has("minAcres")).toBe(false);
  });

  it("builds a next-page URL from canonical applied filters", () => {
    const href = buildCandidateExplorerHref(
      { q: "parcel & road", city: "MANOR", minAcres: null, maxAcres: 8 },
      "opaque+/cursor",
    );
    const params = new URL(href, "https://console.test").searchParams;

    expect(params.get("q")).toBe("parcel & road");
    expect(params.get("city")).toBe("MANOR");
    expect(params.get("max_acres")).toBe("8");
    expect(params.get("cursor")).toBe("opaque+/cursor");
    expect(hasCandidateFilters({ q: null, city: null, minAcres: null, maxAcres: null })).toBe(false);
  });
});
