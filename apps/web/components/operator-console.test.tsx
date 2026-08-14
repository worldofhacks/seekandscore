import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CandidateSummary, TopQueueSnapshot } from "@seekandscore/contracts";

import { AppShell } from "./app-shell";
import { OperatorConsole } from "./operator-console";

function liveCandidate(): CandidateSummary {
  return {
    id: "candidate-1",
    rank: 1,
    previousRank: null,
    name: "East Austin assessor parcel",
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
    nextAction: "Verify parcel geometry and Opportunity Zone overlay.",
    newSinceLastReview: true,
    materialChange: null,
    risks: [
      {
        id: "risk-1",
        label: "Opportunity Zone status unverified",
        detail: "A versioned spatial overlay has not completed.",
        severity: "watch",
      },
    ],
    evidence: [
      {
        id: "evidence-1",
        label: "Assessor value observation",
        value: "Appraised $1,250,000",
        status: "verified",
        source: "travis_tcad_parcels",
        observedAt: "2026-08-13T10:30:00Z",
      },
    ],
    screeningOnly: true,
    sourceObservation: {
      sourceId: "travis_tcad_parcels",
      sourceRecordId: "OBJECTID-42",
      artifactSha256: "a".repeat(64),
      retrievedAt: "2026-08-13T10:30:00Z",
      fields: { appraisedValueCents: 125_000_000 },
    },
    outreachGate: {
      status: "blocked",
      reviewedChecks: 0,
      totalChecks: 5,
      blockers: [
        "Owner and authorized-representative data are not present",
        "All outbound channels are disabled",
      ],
    },
  };
}

function snapshotWithLiveCandidate(): TopQueueSnapshot {
  return {
    id: "live-snapshot",
    label: "Approved live cohort",
    region: "Central Texas",
    timeZone: "America/Chicago",
    asOf: "2026-08-13T10:30:00Z",
    modelVersion: "live-candidate-v1 · API contract",
    provenance: {
      mode: "live",
      status: "current",
      retrievedAt: "2026-08-13T10:30:00Z",
      publishedAt: null,
      staleAfter: "2026-09-27T10:30:00Z",
      statusDetail: null,
      warnings: [],
      sources: [
        {
          id: "travis_tcad_parcels",
          name: "Travis County TNR / TCAD parcel layer",
          status: "current",
          retrievedAt: "2026-08-13T10:30:00Z",
          publishedAt: null,
          recordCount: 1,
        },
      ],
    },
    cohort: {
      cohortTotal: 953,
      filteredTotal: 127,
      nextCursor: "eyJvZmZzZXQiOjUwfQ",
      appliedFilters: {
        q: "FM 973",
        city: "DEL VALLE",
        minAcres: 2,
        maxAcres: 20,
      },
    },
    candidates: [liveCandidate()],
  };
}

function emptySnapshot(
  status: "error" | "rights_disabled" | "unavailable",
): TopQueueSnapshot {
  const rightsDisabled = status === "rights_disabled";
  return {
    id: `empty-${status}`,
    label: "Verified live candidates",
    region: "Central Texas",
    timeZone: "America/Chicago",
    asOf: null,
    modelVersion: "Live candidate contract · no publishable dataset",
    provenance: {
      mode: rightsDisabled ? "live" : "unknown",
      status,
      retrievedAt: null,
      publishedAt: null,
      staleAfter: null,
      statusDetail: rightsDisabled
        ? "Live observations are for internal rights review; public display is disabled."
        : "The live candidate API was unavailable or timed out.",
      sources: [],
      warnings: [],
    },
    cohort: {
      cohortTotal: 0,
      filteredTotal: 0,
      nextCursor: null,
      appliedFilters: {
        q: null,
        city: null,
        minAcres: null,
        maxAcres: null,
      },
    },
    candidates: [],
  };
}

describe("strict live operator console", () => {
  it("labels assessor values and screening scores as research-only observations", () => {
    const snapshot = snapshotWithLiveCandidate();
    const markup = renderToStaticMarkup(<OperatorConsole snapshot={snapshot} />);

    expect(markup).toContain("Source-backed parcels for research");
    expect(markup).toContain("Research-only screen");
    expect(markup).toContain("Appraised value observation");
    expect(markup).toContain("Assessor observation · not an offer");
    expect(markup).toContain('aria-label="Screening score 67.4 out of 100"');
    expect(markup).toContain("Opportunity Zone status");
    expect(markup).toContain("Research");
    expect(markup).toContain("Contact prep");
    expect(markup).toContain("Loading saved research");
    expect(markup).toContain("Approved live cohort");
    expect(markup).toContain("1 shown of filtered 127 / cohort 953");
    expect(markup).toContain('aria-label="Filter approved live cohort"');
    expect(markup).toContain('name="q"');
    expect(markup).toContain('name="city"');
    expect(markup).toContain('name="min_acres"');
    expect(markup).toContain('name="max_acres"');
    expect(markup).toContain('aria-label="Candidate cohort pages"');
    expect(markup).toContain("Next page");
    expect(markup).not.toContain("Export");
  });

  it("keeps a valid zero-result search inside the approved cohort explorer", () => {
    const snapshot: TopQueueSnapshot = {
      ...snapshotWithLiveCandidate(),
      candidates: [],
      cohort: {
        cohortTotal: 953,
        filteredTotal: 0,
        nextCursor: null,
        appliedFilters: {
          q: "no matching parcel",
          city: "MANOR",
          minAcres: null,
          maxAcres: null,
        },
      },
    };
    const markup = renderToStaticMarkup(<OperatorConsole snapshot={snapshot} />);

    expect(markup).toContain("Source-backed parcels for research");
    expect(markup).toContain("No parcels match these cohort filters");
    expect(markup).toContain("0 shown of filtered 0 / cohort 953");
    expect(markup).toContain('value="no matching parcel"');
    expect(markup).toContain("Clear filters");
    expect(markup).toContain("End of filtered cohort");
    expect(markup).not.toContain("Live candidate data could not be loaded");
  });

  it("renders an explicit zero-record error state when live data is unavailable", () => {
    const snapshot = emptySnapshot("error");
    const markup = renderToStaticMarkup(<OperatorConsole snapshot={snapshot} />);

    expect(markup).toContain("No verified live candidates");
    expect(markup).toContain("Live candidate data could not be loaded");
    expect(markup).toContain("Published candidates");
    expect(markup).toContain("Snapshot time unavailable");
    expect(markup).toContain("Review new changes");
    expect(markup).toContain("disabled=\"\"");
    expect(markup).not.toContain("1970");
    expect(markup).not.toContain("East Austin assessor parcel");
  });

  it("explains the private live rights gate without exposing property records", () => {
    const snapshot = emptySnapshot("rights_disabled");
    const markup = renderToStaticMarkup(
      <AppShell snapshot={snapshot}>
        <OperatorConsole snapshot={snapshot} />
      </AppShell>,
    );

    expect(markup).toContain("Live source records are withheld from this console");
    expect(markup).toContain("Live source display is disabled");
    expect(markup).toContain("Private source · display disabled");
    expect(markup).toContain("Published candidates");
    expect(markup).toContain(">0<");
    expect(markup).not.toContain("East Austin assessor parcel");
    expect(markup).not.toContain("953 approved live records");
    expect(markup).toContain("No property records are being displayed");
  });

  it("uses the full cohort total in the shell instead of the current page length", () => {
    const snapshot = snapshotWithLiveCandidate();
    const markup = renderToStaticMarkup(
      <AppShell snapshot={snapshot}>
        <OperatorConsole snapshot={snapshot} />
      </AppShell>,
    );

    expect(markup).toContain("953 approved live records");
    expect(markup).not.toContain("1 publishable live record");
  });
});
