import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiCandidatePage } from "@seekandscore/contracts";

import { loadTopQueueSnapshot, mapApiCandidatePage } from "./api";

const livePage: ApiCandidatePage = {
  items: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      display_name: "East Austin assessor parcel",
      locality: "Austin, TX",
      parcel_id: "TCAD-700001",
      candidate_kind: "parcel",
      parcel_count: 1,
      jurisdiction_id: "us-tx-travis",
      county_name: "Travis County",
      state_name: "Texas",
      timezone: "America/Chicago",
      strategy: "assessor",
      rank: 1,
      previous_rank: null,
      queue_state: "research",
      opportunity_score: 67.4,
      confidence: 0.72,
      acreage: 2.4,
      value_range: { low: 1_250_000, high: 1_250_000 },
      likely_basis: 0,
      thesis: "Deterministic assessor screening for research only.",
      opportunity_zone_status: "review",
      next_action: "Verify parcel geometry and Opportunity Zone overlay.",
      material_change: null,
      evidence: { source_count: 1, unresolved_conflict_count: 0, freshness: "current" },
      as_of: "2026-08-13T10:30:00Z",
      read_model_version: "live-candidate-v1",
      screening_only: true,
      source_observation: {
        source_id: "travis_tcad_parcels",
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
  next_cursor: null,
  total: 1,
  dataset_mode: "live",
  dataset_status: "current",
  read_model_version: "live-candidate-v1",
  retrieved_at: "2026-08-13T10:30:00Z",
  published_at: null,
  stale_after: "2026-09-27T10:30:00Z",
  partial: false,
  warnings: ["Opportunity Zone overlay is not yet verified."],
  sources: [
    {
      id: "travis_tcad_parcels",
      name: "Travis County TNR / TCAD parcel layer",
      status: "current",
      retrieved_at: "2026-08-13T10:30:00Z",
      record_count: 1,
    },
  ],
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("strict live candidate adapter", () => {
  it("maps verified live assessor records and keeps outreach blocked", () => {
    const snapshot = mapApiCandidatePage(livePage);

    expect(snapshot.provenance).toMatchObject({
      mode: "live",
      status: "current",
      retrievedAt: "2026-08-13T10:30:00Z",
      statusDetail: "Opportunity Zone overlay is not yet verified.",
    });
    expect(snapshot.candidates).toHaveLength(1);
    expect(snapshot.candidates[0]).toMatchObject({
      name: "East Austin assessor parcel",
      strategy: "Parcel screening",
      screeningOnly: true,
      sourceObservation: {
        sourceId: "travis_tcad_parcels",
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

  it("rejects a non-live dataset without mapping any candidate", () => {
    const snapshot = mapApiCandidatePage({
      ...livePage,
      dataset_mode: "test-provider",
      dataset_status: "current",
      items: [
        {
          ...livePage.items[0],
          display_name: "Fictional candidate that must never render",
          source_observation: undefined,
        },
      ],
    });

    expect(snapshot.candidates).toEqual([]);
    expect(snapshot.provenance).toMatchObject({
      mode: "unknown",
      status: "unavailable",
    });
    expect(JSON.stringify(snapshot)).not.toContain("Fictional candidate that must never render");
  });

  it("rejects records when a live response has an unsupported dataset status", () => {
    const snapshot = mapApiCandidatePage({
      ...livePage,
      dataset_status: "fallback",
      warnings: ["A substitute dataset was offered."],
      items: [
        {
          ...livePage.items[0],
          display_name: "Substituted record that must never render",
        },
      ],
    });

    expect(snapshot.candidates).toEqual([]);
    expect(snapshot.provenance.status).toBe("unavailable");
    expect(JSON.stringify(snapshot)).not.toContain("Substituted record that must never render");
    expect(JSON.stringify(snapshot)).not.toContain("A substitute dataset was offered.");
  });

  it("represents a private live shadow run as display-disabled with zero candidates", () => {
    const reason = "Live observations are for internal rights review; public display is disabled.";
    const snapshot = mapApiCandidatePage({
      ...livePage,
      items: [],
      total: 0,
      dataset_status: "fallback",
      retrieved_at: null,
      published_at: null,
      stale_after: null,
      sources: [],
      warnings: [reason],
    });

    expect(snapshot.candidates).toEqual([]);
    expect(snapshot.provenance).toMatchObject({
      mode: "live",
      status: "rights_disabled",
      statusDetail: reason,
      retrievedAt: null,
    });
  });

  it("returns an empty error snapshot when the live API is not configured", async () => {
    vi.stubEnv("API_BASE_URL", "");

    const snapshot = await loadTopQueueSnapshot();

    expect(snapshot.candidates).toEqual([]);
    expect(snapshot.provenance.status).toBe("error");
    expect(snapshot.provenance.statusDetail).toContain("not configured");
    expect(snapshot.asOf).toBeNull();
  });

  it("preserves a rights-disabled live page returned with HTTP 503", async () => {
    const reason = "Live observations are for internal rights review; public display is disabled.";
    const unavailablePage: ApiCandidatePage = {
      ...livePage,
      items: [],
      total: 0,
      dataset_status: "error",
      retrieved_at: null,
      published_at: null,
      stale_after: null,
      sources: [],
      warnings: [reason],
    };
    vi.stubEnv("API_BASE_URL", "https://api.example.test");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(unavailablePage), {
          status: 503,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const snapshot = await loadTopQueueSnapshot();

    expect(snapshot.candidates).toEqual([]);
    expect(snapshot.provenance).toMatchObject({
      mode: "live",
      status: "rights_disabled",
      statusDetail: reason,
    });
  });
});
