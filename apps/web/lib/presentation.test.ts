import { describe, expect, it } from "vitest";

import type { CandidateSummary } from "@seekandscore/contracts";

import { candidateScoreLabel, candidateValueDisplay } from "./presentation";

function liveCandidate(overrides: Partial<CandidateSummary> = {}): CandidateSummary {
  return {
    id: "candidate-1",
    rank: 1,
    previousRank: null,
    name: "Travis County assessor parcel",
    locality: "Austin, TX",
    county: "Travis",
    parcelId: "TCAD-700001",
    acreage: 2.4,
    strategy: "Parcel screening",
    queueState: "research",
    overallScore: 67.4,
    confidence: 0.72,
    valueRange: { low: 0, high: 0 },
    likelyBasis: 0,
    thesis: "Live assessor screening for research only.",
    nextAction: "Verify parcel geometry.",
    newSinceLastReview: true,
    materialChange: null,
    risks: [],
    evidence: [],
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

describe("live candidate presentation", () => {
  it("never presents an assessor observation as an offer range or basis", () => {
    const candidate = liveCandidate({
      sourceObservation: {
        sourceId: "travis_tcad_parcels",
        sourceRecordId: "42",
        artifactSha256: "a".repeat(64),
        retrievedAt: "2026-08-13T10:00:00Z",
        fields: { appraisedValueCents: 125_000_000 },
      },
    });

    expect(candidateValueDisplay(candidate)).toEqual({
      label: "Appraised value observation",
      value: "$1.25M",
      subline: "Assessor observation · not an offer",
      observed: true,
    });
    expect(candidateScoreLabel(candidate)).toBe("Screening score");
  });

  it("does not substitute a modeled range when no verified source value exists", () => {
    expect(candidateValueDisplay(liveCandidate())).toEqual({
      label: "Source value observation",
      value: "Not supplied",
      subline: "No verified source value",
      observed: false,
    });
  });

  it("labels assessed values as observations", () => {
    const candidate = liveCandidate({
      sourceObservation: {
        sourceId: "travis_tcad_parcels",
        sourceRecordId: "84",
        artifactSha256: "b".repeat(64),
        retrievedAt: "2026-08-13T11:00:00Z",
        fields: { assessedValueCents: 98_000_000 },
      },
    });

    expect(candidateValueDisplay(candidate)).toMatchObject({
      label: "Assessed value observation",
      value: "$980K",
      observed: true,
    });
  });
});
