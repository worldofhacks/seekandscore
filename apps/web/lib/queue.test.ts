import { describe, expect, it } from "vitest";

import type { CandidateSummary } from "@seekandscore/contracts";

import { filterCandidates, formatMoneyCompact, rankMovement } from "./queue";

function liveCandidate(overrides: Partial<CandidateSummary> = {}): CandidateSummary {
  return {
    id: "candidate-1",
    rank: 1,
    previousRank: 3,
    name: "Travis County assessor parcel",
    locality: "Austin, TX",
    county: "Travis",
    parcelId: "TCAD-700001",
    acreage: 2.4,
    strategy: "Parcel screening",
    queueState: "research",
    overallScore: 67.4,
    confidence: 0.72,
    valueRange: { low: 1_250_000, high: 1_250_000 },
    likelyBasis: 0,
    thesis: "Live assessor screening for research only.",
    nextAction: "Verify parcel geometry.",
    newSinceLastReview: false,
    materialChange: null,
    risks: [],
    evidence: [],
    jurisdictionId: "us-tx-travis",
    opportunityZone: {
      classification: "unavailable",
      reasonCode: "membership_snapshot_unavailable",
      method: null,
      classifiedAt: null,
      parcelGeometry: null,
      designation: null,
    },
    screeningOnly: true,
    outreachGate: {
      status: "blocked",
      reviewedChecks: 0,
      totalChecks: 5,
      blockers: ["Outbound channels are disabled"],
    },
    ...overrides,
  };
}

describe("live candidate queue helpers", () => {
  it("reports positive rank movement when a candidate rises", () => {
    expect(rankMovement({ rank: 1, previousRank: 3 })).toBe(2);
    expect(rankMovement({ rank: 4, previousRank: null })).toBeNull();
  });

  it("filters live candidates by state and searchable fields", () => {
    const candidates = [
      liveCandidate(),
      liveCandidate({
        id: "candidate-2",
        rank: 2,
        previousRank: null,
        name: "Caldwell County assessor parcel",
        county: "Caldwell",
        parcelId: "TCAD-700002",
        newSinceLastReview: true,
      }),
    ];

    expect(filterCandidates(candidates, "new", "")).toHaveLength(1);
    expect(filterCandidates(candidates, "all", "Caldwell")).toHaveLength(1);
    expect(filterCandidates(candidates, "all", "does-not-exist")).toEqual([]);
  });

  it("formats source observation values compactly", () => {
    expect(formatMoneyCompact(980000)).toBe("$980K");
    expect(formatMoneyCompact(1_260_000)).toContain("$1.26M");
  });
});
