import { describe, expect, it } from "vitest";

import type { ApiCandidatePage } from "@seekandscore/contracts";

import { mapApiCandidatePage } from "./api";

const page: ApiCandidatePage = {
  items: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      display_name: "Synthetic API parcel",
      locality: "Austin, TX",
      parcel_id: "TX-453-SYN-API-001",
      candidate_kind: "parcel",
      parcel_count: 1,
      jurisdiction_id: "us-tx-453",
      county_name: "Travis County",
      state_name: "Texas",
      timezone: "America/Chicago",
      strategy: "infill",
      rank: 1,
      previous_rank: 3,
      queue_state: "ready",
      opportunity_score: 87.4,
      confidence: 0.82,
      acreage: 2.4,
      value_range: { low: 980000, high: 1260000 },
      likely_basis: 795000,
      thesis: "Synthetic contract test.",
      opportunity_zone_status: "effective",
      next_action: "Verify access.",
      material_change: "Evidence refreshed.",
      evidence: { source_count: 5, unresolved_conflict_count: 0, freshness: "current" },
      as_of: "2026-08-12T12:00:00Z",
      synthetic: true,
      read_model_version: "synthetic-candidate-v1",
    },
  ],
  next_cursor: null,
  total: 1,
  dataset_mode: "synthetic",
  read_model_version: "synthetic-candidate-v1",
};

describe("API candidate adapter", () => {
  it("maps the FastAPI wire model into the operator contract and keeps outreach blocked", () => {
    const snapshot = mapApiCandidatePage(page);
    expect(snapshot.timeZone).toBe("America/Chicago");
    expect(snapshot.provenance).toMatchObject({
      mode: "synthetic",
      status: "synthetic",
      isFallback: false,
      retrievedAt: null,
    });
    expect(snapshot.asOf).toBe("2026-08-12T12:00:00Z");
    expect(snapshot.candidates).toHaveLength(1);
    expect(snapshot.candidates[0]).toMatchObject({
      name: "Synthetic API parcel",
      strategy: "Buildable land",
      overallScore: 87.4,
      outreachGate: { status: "blocked" },
    });
    expect(snapshot.candidates[0].evidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "Fixture evidence status",
          source: "5 synthetic fixture observations",
        }),
      ]),
    );
  });

  it("maps live assessor provenance without presenting source values as acquisition basis", () => {
    const livePage: ApiCandidatePage = {
      ...page,
      dataset_mode: "live",
      dataset_status: "current",
      retrieved_at: "2026-08-13T10:30:00Z",
      published_at: "2026-08-01T05:00:00Z",
      stale_after: "2026-09-15T05:00:00Z",
      partial: false,
      warnings: ["Opportunity Zone overlay is not yet verified."],
      sources: [
        {
          id: "travis-tcad-arcgis",
          name: "Travis County TNR/TCAD parcel layer",
          status: "current",
          retrieved_at: "2026-08-13T10:30:00Z",
          published_at: "2026-08-01T05:00:00Z",
          record_count: 1,
        },
      ],
      items: [
        {
          ...page.items[0],
          synthetic: false,
          strategy: "assessor",
          screening_only: true,
          opportunity_zone_status: "review",
          source_observation: {
            source_id: "travis-tcad-arcgis",
            source_record_id: "OBJECTID-42",
            artifact_sha256: "a".repeat(64),
            retrieved_at: "2026-08-13T10:30:00Z",
            fields: {
              appraised_value_cents: 125_000_000,
              land_value_cents: 90_000_000,
              acreage: 2.4,
            },
          },
        },
      ],
    };

    const snapshot = mapApiCandidatePage(livePage);

    expect(snapshot.isSynthetic).toBe(false);
    expect(snapshot.provenance).toMatchObject({
      mode: "live",
      status: "current",
      retrievedAt: "2026-08-13T10:30:00Z",
      publishedAt: "2026-08-01T05:00:00Z",
      sources: [{ id: "travis-tcad-arcgis", status: "current" }],
    });
    expect(snapshot.candidates[0]).toMatchObject({
      strategy: "Parcel screening",
      screeningOnly: true,
      sourceObservation: {
        sourceId: "travis-tcad-arcgis",
        fields: { appraisedValueCents: 125_000_000 },
      },
      outreachGate: {
        status: "blocked",
        blockers: expect.arrayContaining([
          "Owner and authorized-representative data are not present",
        ]),
      },
    });
    expect(snapshot.candidates[0].evidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "Assessor value observation",
          detail: expect.stringContaining("not a platform valuation, offer, or acquisition basis"),
        }),
      ]),
    );
  });

  it("accepts legacy flat source observations and labels live-mode fallback as synthetic", () => {
    const snapshot = mapApiCandidatePage({
      ...page,
      dataset_mode: "live",
      dataset_status: "fallback",
      warnings: ["Live projection is unavailable; synthetic records were served."],
      items: [
        {
          ...page.items[0],
          screening_only: true,
          source_observation: {
            source_id: "travis-tcad-arcgis",
            source_record_id: "OBJECTID-84",
            artifact_sha256: "b".repeat(64),
            retrieved_at: "2026-08-13T11:00:00Z",
            assessed_value_cents: 98_000_000,
          },
        },
      ],
    });

    expect(snapshot.provenance).toMatchObject({
      mode: "synthetic",
      status: "fallback",
      isFallback: true,
      fallbackReason: "Live projection is unavailable; synthetic records were served.",
    });
    expect(snapshot.candidates[0].sourceObservation?.fields.assessedValueCents).toBe(
      98_000_000,
    );
  });

  it("preserves absent timestamps instead of inventing epoch or retrieval dates", () => {
    const snapshot = mapApiCandidatePage({
      ...page,
      items: [],
      total: 0,
      dataset_status: "error",
      retrieved_at: null,
      sources: [
        {
          id: "private-shadow-source",
          name: "Private shadow source",
          status: "unavailable",
          retrieved_at: null,
        },
      ],
    });

    expect(snapshot.asOf).toBeNull();
    expect(snapshot.provenance.retrievedAt).toBeNull();
    expect(snapshot.provenance.sources[0].retrievedAt).toBeNull();
  });
});
