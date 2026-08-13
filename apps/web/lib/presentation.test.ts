import { describe, expect, it } from "vitest";

import type { CandidateSummary } from "@seekandscore/contracts";

import { topQueueSnapshot } from "./candidates";
import { candidateScoreLabel, candidateValueDisplay } from "./presentation";

describe("candidate presentation", () => {
  it("never presents an assessor observation as an offer range or basis", () => {
    const candidate: CandidateSummary = {
      ...topQueueSnapshot.candidates[0],
      strategy: "Parcel screening",
      screeningOnly: true,
      sourceObservation: {
        sourceId: "travis-tcad-arcgis",
        sourceRecordId: "42",
        artifactSha256: "a".repeat(64),
        retrievedAt: "2026-08-13T10:00:00Z",
        fields: { appraisedValueCents: 125_000_000 },
      },
    };

    expect(candidateValueDisplay(candidate)).toEqual({
      label: "Appraised value observation",
      value: "$1.25M",
      subline: "Assessor observation · not an offer",
      observed: true,
    });
    expect(candidateScoreLabel(candidate)).toBe("Screening score");
  });

  it("keeps scenario language for modeled synthetic candidates", () => {
    const display = candidateValueDisplay(topQueueSnapshot.candidates[0]);
    expect(display.observed).toBe(false);
    expect(display.label).toBe("Value range");
    expect(display.subline).toContain("Scenario basis");
  });

  it("labels assessed values as observations", () => {
    const candidate: CandidateSummary = {
      ...topQueueSnapshot.candidates[0],
      screeningOnly: true,
      sourceObservation: {
        sourceId: "travis-tcad-arcgis",
        sourceRecordId: "84",
        artifactSha256: "b".repeat(64),
        retrievedAt: "2026-08-13T11:00:00Z",
        fields: { assessedValueCents: 98_000_000 },
      },
    };

    expect(candidateValueDisplay(candidate)).toMatchObject({
      label: "Assessed value observation",
      value: "$980K",
      observed: true,
    });
  });
});
