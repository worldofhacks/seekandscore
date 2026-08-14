import type {
  ApiCandidatePage,
  ApiCandidateReadModel,
  CandidateAppliedFilters,
  CandidateStrategy,
  CandidateSummary,
  DatasetHealthStatus,
  EvidenceDatum,
  TopQueueSnapshot,
} from "@seekandscore/contracts";

import {
  buildCandidateApiQuery,
  candidateFiltersFromQuery,
  parseCandidateQuery,
  type CandidateQuery,
} from "@/lib/candidate-query";
import {
  candidateHasOpportunityZoneEvidence,
  mapOpportunityZoneEvidence,
} from "@/lib/opportunity-zone";

const STRATEGIES: Record<string, CandidateStrategy> = {
  assemblage: "Land banking",
  infill: "Buildable land",
  "land-banking": "Land banking",
  "parcel-screening": "Parcel screening",
  assessor: "Parcel screening",
};

function datasetStatus(page: ApiCandidatePage): DatasetHealthStatus {
  if (page.partial) return "partial";
  if (
    page.dataset_status === "current" ||
    page.dataset_status === "stale" ||
    page.dataset_status === "partial" ||
    page.dataset_status === "error"
  ) {
    return page.dataset_status;
  }
  return "unknown";
}

function rightsDisplayDisabled(page: ApiCandidatePage): boolean {
  if (page.dataset_mode !== "live") return false;
  const warningText = (page.warnings ?? []).join(" ").toLocaleLowerCase();
  return (
    warningText.includes("display is disabled") ||
    warningText.includes("display rights") ||
    warningText.includes("rights review") ||
    warningText.includes("not approved for display")
  );
}

function sourceProvenance(page: ApiCandidatePage) {
  return (page.sources ?? []).map((source) => ({
    id: source.id,
    name: source.name,
    status: source.status,
    retrievedAt: source.retrieved_at ?? null,
    publishedAt: source.published_at ?? null,
    recordCount: source.record_count ?? null,
    detail: source.detail,
  }));
}

function isCandidatePage(value: unknown): value is ApiCandidatePage {
  if (!value || typeof value !== "object") return false;
  const page = value as Partial<ApiCandidatePage>;
  const applied = page.applied_filters;
  const nullableString = (candidate: unknown) =>
    candidate === null || typeof candidate === "string";
  const nullableNonNegativeNumber = (candidate: unknown) =>
    candidate === null ||
    (typeof candidate === "number" &&
      Number.isFinite(candidate) &&
      candidate >= 0);
  const validCity =
    applied?.city === null ||
    applied?.city === "DEL VALLE" ||
    applied?.city === "MANOR";
  const validRange =
    applied?.min_acres === null ||
    applied?.max_acres === null ||
    (typeof applied?.min_acres === "number" &&
      typeof applied?.max_acres === "number" &&
      applied.min_acres <= applied.max_acres);
  return (
    Array.isArray(page.items) &&
    page.items.every(candidateHasOpportunityZoneEvidence) &&
    typeof page.dataset_mode === "string" &&
    typeof page.read_model_version === "string" &&
    Number.isInteger(page.total) &&
    Number.isInteger(page.cohort_total) &&
    (page.total ?? -1) >= 0 &&
    (page.cohort_total ?? -1) >= 0 &&
    (page.total ?? 0) <= (page.cohort_total ?? -1) &&
    page.items.length <= (page.total ?? -1) &&
    Boolean(applied) &&
    typeof applied === "object" &&
    nullableString(applied?.q) &&
    (applied?.q?.length ?? 0) <= 100 &&
    validCity &&
    nullableNonNegativeNumber(applied?.min_acres) &&
    nullableNonNegativeNumber(applied?.max_acres) &&
    validRange &&
    (page.next_cursor === null || typeof page.next_cursor === "string")
  );
}

function appliedFilters(page: ApiCandidatePage): CandidateAppliedFilters {
  return {
    q: page.applied_filters.q,
    city: page.applied_filters.city,
    minAcres: page.applied_filters.min_acres,
    maxAcres: page.applied_filters.max_acres,
  };
}

function emptyLiveSnapshot(
  reason: string,
  status: Extract<DatasetHealthStatus, "error" | "rights_disabled" | "unavailable">,
  page?: ApiCandidatePage,
  preserveLiveProvenance = false,
  query?: CandidateQuery,
): TopQueueSnapshot {
  const isLiveResponse = page?.dataset_mode === "live";
  const livePage = isLiveResponse ? page : undefined;
  return {
    id: page ? `api-${page.read_model_version}-empty` : "live-api-unavailable",
    label: "Verified live candidates",
    region: "Central Texas",
    timeZone: "America/Chicago",
    asOf: preserveLiveProvenance ? (livePage?.retrieved_at ?? null) : null,
    modelVersion: "Live candidate contract · no publishable dataset",
    provenance: {
      mode: isLiveResponse ? "live" : "unknown",
      status,
      retrievedAt:
        preserveLiveProvenance ? (livePage?.retrieved_at ?? null) : null,
      publishedAt:
        preserveLiveProvenance ? (livePage?.published_at ?? null) : null,
      staleAfter:
        preserveLiveProvenance ? (livePage?.stale_after ?? null) : null,
      statusDetail: reason,
      sources: preserveLiveProvenance && livePage ? sourceProvenance(livePage) : [],
      warnings:
        preserveLiveProvenance && livePage && status !== "unavailable"
          ? (livePage.warnings ?? []).filter((warning) => warning !== reason)
          : [],
    },
    cohort: {
      cohortTotal: 0,
      filteredTotal: 0,
      nextCursor: null,
      appliedFilters:
        isLiveResponse && livePage
          ? appliedFilters(livePage)
          : candidateFiltersFromQuery(query),
    },
    candidates: [],
  };
}

function sourceObservationFor(candidate: ApiCandidateReadModel) {
  const source = candidate.source_observation;
  if (!source) return undefined;
  const fields = source.fields ?? source;

  return {
    sourceId: source.source_id,
    sourceRecordId: source.source_record_id,
    artifactSha256: source.artifact_sha256,
    retrievedAt: source.retrieved_at,
    fields: {
      marketValueCents: fields.market_value_cents,
      appraisedValueCents: fields.appraised_value_cents,
      assessedValueCents: fields.assessed_value_cents,
      landValueCents: fields.land_value_cents,
      improvementValueCents: fields.improvement_value_cents,
      acreage: "acreage" in fields ? fields.acreage : undefined,
    },
  };
}

function opportunityZoneEvidenceDatum(candidate: ApiCandidateReadModel): EvidenceDatum {
  const opportunityZone = mapOpportunityZoneEvidence(candidate);
  const labels = {
    inside: "Inside designated tract",
    outside: "Outside designated tracts",
    boundary_review: "Boundary review required",
    unavailable: "Geographic result unavailable",
  } as const;
  const details = {
    inside:
      "Parcel geometry is strictly inside one 2018 designated tract. This geographic result does not establish tax qualification.",
    outside:
      "Parcel geometry does not intersect a 2018 designated tract in this evidence snapshot. This geographic result does not establish tax qualification.",
    boundary_review:
      opportunityZone.reasonCode === "designation_geometry_repaired"
        ? "The designation geometry required repair; no inside or outside conclusion is represented until human review."
        : opportunityZone.reasonCode === "parcel_geometry_repaired"
          ? "The parcel geometry required repair; no inside or outside conclusion is represented until human review."
          : "Parcel geometry intersects a designation boundary; no inside or outside conclusion is represented.",
    unavailable:
      "The platform has no complete evidence snapshot for this geographic classification and does not infer a result.",
  } as const;
  return {
    id: `${candidate.id}-opportunity-zone`,
    label: "2018 Opportunity Zone geography",
    value: labels[opportunityZone.classification],
    status:
      opportunityZone.classification === "inside" ||
      opportunityZone.classification === "outside"
        ? "verified"
        : opportunityZone.classification === "boundary_review"
          ? "conflicting"
          : "unknown",
    source:
      opportunityZone.designation?.sourceId ??
      opportunityZone.parcelGeometry?.sourceId ??
      "No complete overlay evidence",
    observedAt: opportunityZone.classifiedAt ?? candidate.as_of,
    detail: details[opportunityZone.classification],
  };
}

function observationValue(candidate: ApiCandidateReadModel): string | null {
  const source = candidate.source_observation;
  if (!source) return null;
  const fields = source.fields ?? source;
  const observed: Array<[string, number]> = [];
  if (fields.appraised_value_cents !== undefined) {
    observed.push(["Appraised", fields.appraised_value_cents]);
  }
  if (fields.assessed_value_cents !== undefined) {
    observed.push(["Assessed", fields.assessed_value_cents]);
  }
  if (fields.market_value_cents !== undefined) {
    observed.push(["Market", fields.market_value_cents]);
  }
  if (fields.land_value_cents !== undefined) {
    observed.push(["Land", fields.land_value_cents]);
  }
  if (!observed.length) return null;
  return observed
    .map(([label, cents]) => `${label} $${(cents / 100).toLocaleString("en-US")}`)
    .join(" · ");
}

function evidenceFor(candidate: ApiCandidateReadModel): EvidenceDatum[] {
  const conflictStatus =
    candidate.evidence.unresolved_conflict_count > 0 ? "conflicting" : "verified";
  const sourceObservation = candidate.source_observation;
  const observedValue = observationValue(candidate);
  const sourceLabel = sourceObservation?.source_id ?? `${candidate.county_name} parcel source`;
  const isLiveScreen = candidate.screening_only ?? Boolean(sourceObservation);

  const evidence: EvidenceDatum[] = [
    {
      id: `${candidate.id}-identity`,
      label: "Parcel identity",
      value: candidate.parcel_id,
      status: conflictStatus,
      source: sourceLabel,
      observedAt: candidate.as_of,
      detail: "Official source observation; field and legal verification remain required.",
    },
    {
      id: `${candidate.id}-freshness`,
      label: "Evidence freshness",
      value: candidate.evidence.freshness,
      status: candidate.evidence.freshness === "current" ? "verified" : "unknown",
      source: `${candidate.evidence.source_count} source observation${candidate.evidence.source_count === 1 ? "" : "s"}`,
      observedAt: candidate.as_of,
      detail: "Freshness is evaluated against the configured source cadence.",
    },
    opportunityZoneEvidenceDatum(candidate),
  ];

  evidence.splice(1, 0, {
    id: `${candidate.id}-value`,
    label: isLiveScreen ? "Assessor value observation" : "Source value observation",
    value: observedValue ?? "Not supplied",
    status: observedValue ? conflictStatus : "unknown",
    source: sourceLabel,
    observedAt: sourceObservation?.retrieved_at ?? candidate.as_of,
    detail: observedValue
      ? "Published assessor values are source observations, not a platform valuation, offer, or acquisition basis."
      : "No verified source value was supplied; the console does not substitute an estimate.",
  });

  return evidence;
}

function opportunityZoneRisk(candidate: ApiCandidateReadModel) {
  const evidence = candidate.opportunity_zone_evidence;
  if (evidence.classification === "inside") {
    return {
      id: `${candidate.id}-opportunity-zone`,
      label: "Tax qualification is not established",
      detail:
        "The spatial match is geographic screening evidence only; entity, fund, business, timing, and other tax requirements remain outside this platform.",
      severity: "watch" as const,
    };
  }
  if (evidence.classification === "outside") {
    return {
      id: `${candidate.id}-opportunity-zone`,
      label: "Outside 2018 designated geography",
      detail:
        "The parcel is outside designated tracts in the versioned snapshot; later boundary or source changes are not inferred.",
      severity: "watch" as const,
    };
  }
  if (evidence.classification === "boundary_review") {
    const repairedGeometry = evidence.reason_code === "parcel_geometry_repaired";
    const repairedDesignation =
      evidence.reason_code === "designation_geometry_repaired";
    return {
      id: `${candidate.id}-opportunity-zone`,
      label: repairedDesignation
        ? "Repaired designation geometry requires review"
        : repairedGeometry
          ? "Repaired parcel geometry requires review"
          : "Opportunity Zone boundary review required",
      detail: repairedDesignation
        ? "The source designation geometry required repair. Human review is required; the platform reports neither inside nor outside."
        : repairedGeometry
          ? "The source parcel geometry required repair. Human review is required; the platform reports neither inside nor outside."
          : "The parcel intersects a designation boundary. A survey-grade human review is required; the platform reports neither inside nor outside.",
      severity: "elevated" as const,
    };
  }
  return {
    id: `${candidate.id}-opportunity-zone`,
    label: "Opportunity Zone geography unavailable",
    detail:
      "A complete parcel-to-designation evidence snapshot is unavailable, so no geographic classification is represented.",
    severity: "elevated" as const,
  };
}

function mapCandidate(candidate: ApiCandidateReadModel): CandidateSummary {
  const evidence = evidenceFor(candidate);
  const needsIdentityReview = candidate.evidence.unresolved_conflict_count > 0;
  const sourceObservation = sourceObservationFor(candidate);
  const screeningOnly = candidate.screening_only ?? Boolean(sourceObservation);

  const summary: CandidateSummary = {
    id: candidate.id,
    rank: candidate.rank,
    previousRank: candidate.previous_rank,
    name: candidate.display_name,
    locality: candidate.locality,
    county: candidate.county_name.replace(/ County$/, ""),
    jurisdictionId: candidate.jurisdiction_id,
    parcelId: candidate.parcel_id,
    acreage: candidate.acreage,
    strategy: screeningOnly
      ? "Parcel screening"
      : (STRATEGIES[candidate.strategy] ?? "Land banking"),
    queueState: candidate.queue_state,
    overallScore: candidate.opportunity_score,
    confidence: candidate.confidence,
    valueRange: candidate.value_range,
    likelyBasis: candidate.likely_basis,
    thesis: candidate.thesis,
    nextAction: candidate.next_action,
    newSinceLastReview: candidate.previous_rank === null,
    materialChange: candidate.material_change,
    evidence,
    opportunityZone: mapOpportunityZoneEvidence(candidate),
    screeningOnly,
    sourceObservation,
    risks: [
      {
        id: `${candidate.id}-conflicts`,
        label: needsIdentityReview ? "Evidence conflicts unresolved" : "Field verification pending",
        detail: needsIdentityReview
          ? `${candidate.evidence.unresolved_conflict_count} source conflict${candidate.evidence.unresolved_conflict_count === 1 ? "" : "s"} require review.`
          : "Source observations are not a substitute for field or professional verification.",
        severity: needsIdentityReview ? "elevated" : "watch",
      },
      {
        id: `${candidate.id}-title`,
        label: "Title review not complete",
        detail: "No title, survey, legal, tax, or environmental conclusion is represented.",
        severity: "watch",
      },
      opportunityZoneRisk(candidate),
    ],
    outreachGate: {
      status: "blocked",
      reviewedChecks: needsIdentityReview ? 1 : 2,
      totalChecks: 5,
      blockers: [
        ...(screeningOnly
          ? ["Owner and authorized-representative data are not present"]
          : needsIdentityReview
            ? ["Responsible-party identity needs review"]
            : []),
        "No approved contact-point source",
        "Texas acquisition policy is not activated",
        "All outbound channels are disabled",
      ],
    },
  };

  if (screeningOnly && sourceObservation) {
    summary.thesis = `${candidate.thesis} Assessor values are shown only as source observations.`;
  }

  return summary;
}

export function mapApiCandidatePage(
  page: ApiCandidatePage,
  query: CandidateQuery = parseCandidateQuery({}),
): TopQueueSnapshot {
  if (!isCandidatePage(page)) {
    return emptyLiveSnapshot(
      "The live candidate API returned an incompatible cohort or evidence contract.",
      "unavailable",
      undefined,
      false,
      query,
    );
  }
  if (page.dataset_mode !== "live") {
    return emptyLiveSnapshot(
      "The candidate API did not return a verified live dataset. No records were displayed.",
      "unavailable",
      page,
      false,
      query,
    );
  }

  if (rightsDisplayDisabled(page)) {
    return emptyLiveSnapshot(
      page.warnings?.[0] ?? "Live source observations are not approved for public display.",
      "rights_disabled",
      page,
      true,
      query,
    );
  }

  const status = datasetStatus(page);
  if (status !== "current" && status !== "stale" && status !== "partial") {
    return emptyLiveSnapshot(
      status === "error"
        ? (page.warnings?.[0] ?? "The live candidate dataset reported an error.")
        : "The live candidate API did not report a publishable dataset status. No records were displayed.",
      status === "error" ? "error" : "unavailable",
      page,
      true,
      query,
    );
  }

  const first = page.items[0];
  return {
    id: `api-${page.read_model_version}-${query.cursor ?? page.items[0]?.id ?? "first"}`,
    label: "Approved live cohort",
    region: "Central Texas",
    timeZone: first?.timezone ?? "UTC",
    asOf: first?.as_of ?? page.retrieved_at ?? null,
    modelVersion: `${page.read_model_version} · API contract`,
    provenance: {
      mode: "live",
      status,
      retrievedAt: page.retrieved_at ?? null,
      publishedAt: page.published_at ?? null,
      staleAfter: page.stale_after ?? null,
      statusDetail: page.warnings?.[0] ?? null,
      sources: sourceProvenance(page),
      warnings: page.warnings ?? [],
    },
    cohort: {
      cohortTotal: page.cohort_total,
      filteredTotal: page.total,
      nextCursor: page.next_cursor,
      appliedFilters: appliedFilters(page),
    },
    candidates: page.items.map(mapCandidate),
  };
}

export async function loadTopQueueSnapshot(
  query: CandidateQuery = parseCandidateQuery({}),
): Promise<TopQueueSnapshot> {
  const baseUrl = process.env.API_BASE_URL;
  if (!baseUrl) {
    return emptyLiveSnapshot(
      "The live candidate API is not configured.",
      "error",
      undefined,
      false,
      query,
    );
  }

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/candidates?${buildCandidateApiQuery(query)}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(3_000),
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      if (isCandidatePage(body)) return mapApiCandidatePage(body, query);
      return emptyLiveSnapshot(
        `The live candidate API returned HTTP ${response.status}.`,
        "error",
        undefined,
        false,
        query,
      );
    }
    if (!isCandidatePage(body)) {
      return emptyLiveSnapshot(
        "The live candidate API returned an incompatible cohort or evidence contract.",
        "error",
        undefined,
        false,
        query,
      );
    }
    return mapApiCandidatePage(body, query);
  } catch {
    return emptyLiveSnapshot(
      "The live candidate API was unavailable or timed out.",
      "error",
      undefined,
      false,
      query,
    );
  }
}
