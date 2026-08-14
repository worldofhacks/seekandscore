import { describe, expect, it } from "vitest";

import type {
  ApiCandidateReadModel,
  ApiOpportunityZoneEvidence,
} from "@seekandscore/contracts";

import {
  isApiOpportunityZoneEvidence,
  mapOpportunityZoneEvidence,
} from "./opportunity-zone";
import { opportunityZoneDisplay } from "./presentation";

function insideEvidence(): ApiOpportunityZoneEvidence {
  return {
    classification: "inside",
    reason_code: "matched_designated_tract",
    method: "postgis_strict_interior_v1",
    classified_at: "2026-08-14T09:00:00Z",
    parcel_geometry: {
      source_id: "travis_tcad_parcel_geometry",
      source_record_id: "OBJECTID-42",
      artifact_sha256: "a".repeat(64),
      observed_at: "2026-08-13T10:30:00Z",
      geometry_repaired: false,
      repair_method: null,
    },
    designation: {
      round_id: "us-federal-qoz-2018",
      tract_geoid: "48453001754",
      intersecting_tract_geoids: ["48453001754"],
      census_vintage: 2010,
      designation_status: "effective",
      effective_from: "2018-01-01",
      effective_to: "2028-12-31",
      source_id: "federal_qoz_2018_designations",
      source_artifact_sha256: "b".repeat(64),
      authority_uri: "https://www.cdfifund.gov/opportunity-zones",
      geometry_repaired: false,
      repair_method: null,
    },
  };
}

function candidate(evidence: ApiOpportunityZoneEvidence): ApiCandidateReadModel {
  const legacy =
    evidence.classification === "inside"
      ? "effective"
      : evidence.classification === "outside"
        ? "outside"
        : "review";
  return {
    id: "11111111-1111-4111-8111-111111111111",
    opportunity_zone_status: legacy,
    opportunity_zone_evidence: evidence,
  } as ApiCandidateReadModel;
}

describe("Opportunity Zone evidence contract", () => {
  it("accepts inside, outside, boundary-review, and unavailable semantics", () => {
    const inside = insideEvidence();
    const outside: ApiOpportunityZoneEvidence = {
      ...inside,
      classification: "outside",
      reason_code: "no_designated_tract_intersection",
      designation: {
        ...inside.designation!,
        tract_geoid: null,
        intersecting_tract_geoids: [],
      },
    };
    const boundary: ApiOpportunityZoneEvidence = {
      ...inside,
      classification: "boundary_review",
      reason_code: "parcel_intersects_designation_boundary",
      designation: {
        ...inside.designation!,
        tract_geoid: null,
        intersecting_tract_geoids: ["48453001754", "48453001755"],
      },
    };
    const unavailable: ApiOpportunityZoneEvidence = {
      classification: "unavailable",
      reason_code: "membership_snapshot_unavailable",
      method: null,
      classified_at: null,
      parcel_geometry: null,
      designation: null,
    };

    expect(isApiOpportunityZoneEvidence(inside, "effective")).toBe(true);
    expect(isApiOpportunityZoneEvidence(outside, "outside")).toBe(true);
    expect(isApiOpportunityZoneEvidence(boundary, "review")).toBe(true);
    expect(isApiOpportunityZoneEvidence(unavailable, "review")).toBe(true);

    expect(opportunityZoneDisplay(mapOpportunityZoneEvidence(candidate(inside))).label).toBe(
      "Inside a 2018 designated tract",
    );
    expect(opportunityZoneDisplay(mapOpportunityZoneEvidence(candidate(outside))).label).toBe(
      "Outside 2018 designated tracts",
    );
    expect(opportunityZoneDisplay(mapOpportunityZoneEvidence(candidate(boundary))).label).toBe(
      "Designation boundary review required",
    );
    expect(
      opportunityZoneDisplay(mapOpportunityZoneEvidence(candidate(unavailable))).shortLabel,
    ).toBe("Unavailable");
  });

  it("requires a display-gated unavailable result to disclose no lineage", () => {
    const gated: ApiOpportunityZoneEvidence = {
      classification: "unavailable",
      reason_code: "display_not_approved",
      method: null,
      classified_at: null,
      parcel_geometry: null,
      designation: null,
    };
    expect(isApiOpportunityZoneEvidence(gated, "review")).toBe(true);
    expect(opportunityZoneDisplay(mapOpportunityZoneEvidence(candidate(gated)))).toMatchObject({
      label: "Reference display not approved",
      shortLabel: "Display gated",
    });

    expect(
      isApiOpportunityZoneEvidence(
        { ...gated, designation: insideEvidence().designation },
        "review",
      ),
    ).toBe(false);
  });

  it("rejects status mismatches and incomplete source lineage", () => {
    const inside = insideEvidence();
    expect(isApiOpportunityZoneEvidence(inside, "review")).toBe(false);
    expect(
      isApiOpportunityZoneEvidence(
        {
          ...inside,
          parcel_geometry: { ...inside.parcel_geometry!, artifact_sha256: "not-a-hash" },
        },
        "effective",
      ),
    ).toBe(false);
    expect(
      isApiOpportunityZoneEvidence(
        {
          ...inside,
          classification: "boundary_review",
          reason_code: "parcel_intersects_designation_boundary",
          designation: {
            ...inside.designation!,
            tract_geoid: null,
            intersecting_tract_geoids: [],
          },
        },
        "review",
      ),
    ).toBe(false);
  });

  it("forces repaired parcel geometry into human review even with no intersection", () => {
    const inside = insideEvidence();
    const repaired: ApiOpportunityZoneEvidence = {
      ...inside,
      classification: "boundary_review",
      reason_code: "parcel_geometry_repaired",
      parcel_geometry: {
        ...inside.parcel_geometry!,
        geometry_repaired: true,
        repair_method: "postgis_st_makevalid_v1",
      },
      designation: {
        ...inside.designation!,
        tract_geoid: null,
        intersecting_tract_geoids: [],
      },
    };

    expect(isApiOpportunityZoneEvidence(repaired, "review")).toBe(true);
    expect(opportunityZoneDisplay(mapOpportunityZoneEvidence(candidate(repaired)))).toMatchObject({
      label: "Repaired parcel geometry requires review",
      shortLabel: "Boundary review",
    });
    expect(
      isApiOpportunityZoneEvidence(
        {
          ...repaired,
          parcel_geometry: {
            ...repaired.parcel_geometry!,
            geometry_repaired: false,
            repair_method: null,
          },
        },
        "review",
      ),
    ).toBe(false);
  });

  it("forces repaired designation geometry into human review with no coordinate leakage", () => {
    const inside = insideEvidence();
    const repairedDesignation: ApiOpportunityZoneEvidence = {
      ...inside,
      classification: "boundary_review",
      reason_code: "designation_geometry_repaired",
      designation: {
        ...inside.designation!,
        tract_geoid: null,
        intersecting_tract_geoids: ["48453001754"],
        geometry_repaired: true,
        repair_method: "postgis_st_makevalid_collection_extract_v1",
      },
    };

    expect(isApiOpportunityZoneEvidence(repairedDesignation, "review")).toBe(true);
    const mapped = mapOpportunityZoneEvidence(candidate(repairedDesignation));
    expect(opportunityZoneDisplay(mapped)).toMatchObject({
      label: "Repaired designation geometry requires review",
      shortLabel: "Boundary review",
    });
    expect(mapped.designation).toMatchObject({
      geometryRepaired: true,
      repairMethod: "postgis_st_makevalid_collection_extract_v1",
    });
    expect(JSON.stringify(mapped).toLowerCase()).not.toMatch(/coordinates|geojson/);

    const bothRepaired: ApiOpportunityZoneEvidence = {
      ...repairedDesignation,
      parcel_geometry: {
        ...repairedDesignation.parcel_geometry!,
        geometry_repaired: true,
        repair_method: "postgis_st_makevalid_v1",
      },
    };
    expect(isApiOpportunityZoneEvidence(bothRepaired, "review")).toBe(true);
    expect(
      isApiOpportunityZoneEvidence(
        { ...bothRepaired, reason_code: "parcel_geometry_repaired" },
        "review",
      ),
    ).toBe(false);

    expect(
      isApiOpportunityZoneEvidence(
        {
          ...repairedDesignation,
          designation: {
            ...repairedDesignation.designation!,
            repair_method: null,
          },
        },
        "review",
      ),
    ).toBe(false);
    expect(
      isApiOpportunityZoneEvidence(
        {
          ...repairedDesignation,
          designation: {
            ...repairedDesignation.designation!,
            intersecting_tract_geoids: [],
          },
        },
        "review",
      ),
    ).toBe(false);
    expect(
      isApiOpportunityZoneEvidence(
        {
          ...inside,
          designation: {
            ...inside.designation!,
            geometry_repaired: true,
            repair_method: "postgis_st_makevalid_collection_extract_v1",
          },
        },
        "effective",
      ),
    ).toBe(false);
  });
});
