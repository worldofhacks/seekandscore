import type {
  ApiCandidateReadModel,
  ApiOpportunityZoneEvidence,
  OpportunityZoneEvidence,
} from "@seekandscore/contracts";

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function sha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function tractGeoid(value: unknown): value is string {
  return typeof value === "string" && /^[0-9]{11}$/.test(value);
}

function dateOnly(value: unknown): value is string {
  return typeof value === "string" && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value);
}

function isoDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9]{4}-[0-9]{2}-[0-9]{2}T/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

export function isApiOpportunityZoneEvidence(
  value: unknown,
  legacyStatus: unknown,
): value is ApiOpportunityZoneEvidence {
  if (!value || typeof value !== "object") return false;
  const evidence = value as Partial<ApiOpportunityZoneEvidence>;
  const parcel = evidence.parcel_geometry;
  const designation = evidence.designation;
  const validClassification =
    evidence.classification === "inside" ||
    evidence.classification === "outside" ||
    evidence.classification === "boundary_review" ||
    evidence.classification === "unavailable";
  const validReason =
    evidence.reason_code === "matched_designated_tract" ||
    evidence.reason_code === "no_designated_tract_intersection" ||
    evidence.reason_code === "parcel_intersects_designation_boundary" ||
    evidence.reason_code === "parcel_geometry_repaired" ||
    evidence.reason_code === "designation_geometry_repaired" ||
    evidence.reason_code === "parcel_geometry_unavailable" ||
    evidence.reason_code === "designation_layer_unavailable" ||
    evidence.reason_code === "membership_snapshot_unavailable" ||
    evidence.reason_code === "display_not_approved";
  if (
    !validClassification ||
    !validReason ||
    (evidence.method !== null && evidence.method !== "postgis_strict_interior_v1") ||
    !nullableString(evidence.classified_at)
  ) {
    return false;
  }

  if (parcel !== null) {
    if (!parcel || typeof parcel !== "object") return false;
    if (
      !nonEmptyString(parcel.source_id) ||
      !nonEmptyString(parcel.source_record_id) ||
      !sha256(parcel.artifact_sha256) ||
      !isoDateTime(parcel.observed_at) ||
      typeof parcel.geometry_repaired !== "boolean" ||
      !nullableString(parcel.repair_method) ||
      (parcel.geometry_repaired && !nonEmptyString(parcel.repair_method)) ||
      (!parcel.geometry_repaired && parcel.repair_method !== null)
    ) {
      return false;
    }
  }

  if (designation !== null) {
    if (!designation || typeof designation !== "object") return false;
    if (
      designation.round_id !== "us-federal-qoz-2018" ||
      (designation.tract_geoid !== null && !tractGeoid(designation.tract_geoid)) ||
      !Array.isArray(designation.intersecting_tract_geoids) ||
      !designation.intersecting_tract_geoids.every(tractGeoid) ||
      new Set(designation.intersecting_tract_geoids).size !==
        designation.intersecting_tract_geoids.length ||
      designation.intersecting_tract_geoids.join("|") !==
        [...designation.intersecting_tract_geoids].sort().join("|") ||
      designation.census_vintage !== 2010 ||
      designation.designation_status !== "effective" ||
      !dateOnly(designation.effective_from) ||
      !dateOnly(designation.effective_to) ||
      designation.effective_from > designation.effective_to ||
      !nonEmptyString(designation.source_id) ||
      !sha256(designation.source_artifact_sha256) ||
      !nonEmptyString(designation.authority_uri) ||
      typeof designation.geometry_repaired !== "boolean" ||
      !nullableString(designation.repair_method) ||
      (designation.geometry_repaired && !nonEmptyString(designation.repair_method)) ||
      (!designation.geometry_repaired && designation.repair_method !== null)
    ) {
      return false;
    }
    try {
      const authority = new URL(designation.authority_uri);
      if (
        authority.protocol !== "https:" ||
        !authority.hostname ||
        authority.username ||
        authority.password
      ) {
        return false;
      }
    } catch {
      return false;
    }
  }

  if (evidence.classification === "inside") {
    return (
      legacyStatus === "effective" &&
      evidence.reason_code === "matched_designated_tract" &&
      evidence.method === "postgis_strict_interior_v1" &&
      isoDateTime(evidence.classified_at) &&
      parcel !== null &&
      !parcel.geometry_repaired &&
      designation !== null &&
      !designation.geometry_repaired &&
      tractGeoid(designation.tract_geoid) &&
      designation.intersecting_tract_geoids.length === 1 &&
      designation.intersecting_tract_geoids.includes(designation.tract_geoid)
    );
  }
  if (evidence.classification === "outside") {
    return (
      legacyStatus === "outside" &&
      evidence.reason_code === "no_designated_tract_intersection" &&
      evidence.method === "postgis_strict_interior_v1" &&
      isoDateTime(evidence.classified_at) &&
      parcel !== null &&
      !parcel.geometry_repaired &&
      designation !== null &&
      !designation.geometry_repaired &&
      designation.tract_geoid === null &&
      designation.intersecting_tract_geoids.length === 0
    );
  }
  if (evidence.classification === "boundary_review") {
    return (
      legacyStatus === "review" &&
      (evidence.reason_code === "parcel_intersects_designation_boundary" ||
        evidence.reason_code === "parcel_geometry_repaired" ||
        evidence.reason_code === "designation_geometry_repaired") &&
      evidence.method === "postgis_strict_interior_v1" &&
      isoDateTime(evidence.classified_at) &&
      parcel !== null &&
      designation !== null &&
      (evidence.reason_code !== "parcel_geometry_repaired" ||
        (parcel.geometry_repaired &&
          nonEmptyString(parcel.repair_method) &&
          !designation.geometry_repaired)) &&
      (evidence.reason_code !== "parcel_intersects_designation_boundary" ||
        (!parcel.geometry_repaired && !designation.geometry_repaired)) &&
      (evidence.reason_code !== "designation_geometry_repaired" ||
        (designation.geometry_repaired &&
          nonEmptyString(designation.repair_method))) &&
      designation.tract_geoid === null &&
      (evidence.reason_code === "parcel_geometry_repaired" ||
        designation.intersecting_tract_geoids.length > 0)
    );
  }
  return (
    legacyStatus === "review" &&
    evidence.method === null &&
    evidence.classified_at === null &&
    parcel === null &&
    designation === null &&
    (evidence.reason_code === "parcel_geometry_unavailable" ||
      evidence.reason_code === "designation_layer_unavailable" ||
      evidence.reason_code === "membership_snapshot_unavailable" ||
      evidence.reason_code === "display_not_approved")
  );
}

export function candidateHasOpportunityZoneEvidence(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ApiCandidateReadModel>;
  return isApiOpportunityZoneEvidence(
    candidate.opportunity_zone_evidence,
    candidate.opportunity_zone_status,
  );
}

export function mapOpportunityZoneEvidence(
  candidate: ApiCandidateReadModel,
): OpportunityZoneEvidence {
  const evidence = candidate.opportunity_zone_evidence;
  const parcel = evidence.parcel_geometry;
  const designation = evidence.designation;
  return {
    classification: evidence.classification,
    reasonCode: evidence.reason_code,
    method: evidence.method,
    classifiedAt: evidence.classified_at,
    parcelGeometry: parcel
      ? {
          sourceId: parcel.source_id,
          sourceRecordId: parcel.source_record_id,
          artifactSha256: parcel.artifact_sha256,
          observedAt: parcel.observed_at,
          geometryRepaired: parcel.geometry_repaired,
          repairMethod: parcel.repair_method,
        }
      : null,
    designation: designation
      ? {
          roundId: designation.round_id,
          tractGeoid: designation.tract_geoid,
          intersectingTractGeoids: designation.intersecting_tract_geoids,
          censusVintage: designation.census_vintage,
          designationStatus: designation.designation_status,
          effectiveFrom: designation.effective_from,
          effectiveTo: designation.effective_to,
          sourceId: designation.source_id,
          sourceArtifactSha256: designation.source_artifact_sha256,
          authorityUri: designation.authority_uri,
          geometryRepaired: designation.geometry_repaired,
          repairMethod: designation.repair_method,
        }
      : null,
  };
}
