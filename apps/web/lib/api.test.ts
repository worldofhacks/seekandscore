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
    expect(snapshot.candidates).toHaveLength(1);
    expect(snapshot.candidates[0]).toMatchObject({
      name: "Synthetic API parcel",
      strategy: "Buildable land",
      overallScore: 87.4,
      outreachGate: { status: "blocked" },
    });
  });
});
