import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { TopQueueSnapshot } from "@seekandscore/contracts";

import { topQueueSnapshot } from "@/lib/candidates";

import { OperatorConsole } from "./operator-console";

describe("operator data provenance", () => {
  it("exposes fallback mode, source timestamps, and warnings in accessible markup", () => {
    const snapshot: TopQueueSnapshot = {
      ...topQueueSnapshot,
      provenance: {
        ...topQueueSnapshot.provenance,
        status: "fallback",
        isFallback: true,
        fallbackReason: "The live candidate API timed out.",
        warnings: [
          "The live candidate API timed out.",
          "This is not a live investment queue.",
        ],
      },
    };

    const markup = renderToStaticMarkup(<OperatorConsole snapshot={snapshot} />);

    expect(markup).toContain("Live data unavailable — showing a synthetic fallback");
    expect(markup).toContain("Synthetic fallback");
    expect(markup).toContain("The live candidate API timed out.");
    expect(markup).toContain('id="data-provenance-heading"');
    expect(markup).toContain("Source provenance");
    expect(markup).toContain("This is not a live investment queue.");
    expect(markup).toContain("dateTime=");
    expect(markup).toContain("Synthetic candidates for product validation");
    expect(markup).toContain("Synthetic fixtures");
    expect(markup).not.toContain("Best opportunities, right now");
  });

  it("labels assessor values and screening scores as research-only observations", () => {
    const candidate = {
      ...topQueueSnapshot.candidates[0],
      strategy: "Parcel screening" as const,
      screeningOnly: true,
      sourceObservation: {
        sourceId: "travis-tcad-arcgis",
        sourceRecordId: "OBJECTID-42",
        artifactSha256: "a".repeat(64),
        retrievedAt: "2026-08-13T10:30:00Z",
        fields: { appraisedValueCents: 125_000_000 },
      },
    };
    const snapshot: TopQueueSnapshot = {
      ...topQueueSnapshot,
      isSynthetic: false,
      candidates: [candidate],
      provenance: {
        mode: "live",
        status: "current",
        retrievedAt: "2026-08-13T10:30:00Z",
        publishedAt: "2026-08-01T05:00:00Z",
        staleAfter: "2026-09-15T05:00:00Z",
        isFallback: false,
        fallbackReason: null,
        warnings: [],
        sources: [
          {
            id: "travis-tcad-arcgis",
            name: "Travis County TNR/TCAD parcel layer",
            status: "current",
            retrievedAt: "2026-08-13T10:30:00Z",
            publishedAt: "2026-08-01T05:00:00Z",
            recordCount: 1,
          },
        ],
      },
    };

    const markup = renderToStaticMarkup(<OperatorConsole snapshot={snapshot} />);

    expect(markup).toContain("Source-backed parcels for research");
    expect(markup).toContain("Research-only screen");
    expect(markup).toContain("Appraised value observation");
    expect(markup).toContain("Assessor observation · not an offer");
    expect(markup).toContain('aria-label="Screening score 91.8 out of 100"');
    expect(markup).toContain("Opportunity Zone status");
    expect(markup).toContain("Outreach");
  });

  it("renders an explicit non-actionable error state when no dataset is served", () => {
    const snapshot: TopQueueSnapshot = {
      ...topQueueSnapshot,
      isSynthetic: false,
      asOf: null,
      candidates: [],
      provenance: {
        mode: "live",
        status: "error",
        retrievedAt: null,
        publishedAt: null,
        staleAfter: null,
        isFallback: false,
        fallbackReason: null,
        sources: [],
        warnings: ["The official parcel source could not be read."],
      },
    };

    const markup = renderToStaticMarkup(<OperatorConsole snapshot={snapshot} />);

    expect(markup).toContain("Candidate data is unavailable");
    expect(markup).toContain("The requested dataset is unavailable");
    expect(markup).toContain("No candidate or outreach action is available");
    expect(markup).toContain("Review new changes");
    expect(markup).toContain("disabled=\"\"");
    expect(markup).toContain("Snapshot time unavailable");
    expect(markup).toContain("Not supplied");
    expect(markup).not.toContain("1970");
  });
});
